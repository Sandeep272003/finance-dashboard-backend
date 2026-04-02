import logging
from datetime import date, datetime
from typing import Optional, Tuple, List, Dict, Any

from sqlalchemy import func, and_, or_, case
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from models import (
    User, FinancialRecord, UserRole, RecordType,
    UserCreate, RecordCreate, RecordUpdate, UpdateRoleRequest,
)
from auth import hash_password

logger = logging.getLogger(__name__)


def calculate_total_pages(total_items: int, page_size: int) -> int:
    return (total_items + page_size - 1) // page_size if total_items > 0 else 0


def paginate(query, page: int, page_size: int):
    return query.offset((page - 1) * page_size).limit(page_size)


def apply_record_filters(
    query,
    record_type: Optional[RecordType] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    include_deleted: bool = False,
):
    constraints = []
    if not include_deleted:
        constraints.append(FinancialRecord.is_deleted == False)
    if record_type is not None:
        constraints.append(FinancialRecord.type == record_type)
    if category is not None:
        constraints.append(FinancialRecord.category == category.strip().title())
    if date_from is not None:
        constraints.append(FinancialRecord.record_date >= date_from)
    if date_to is not None:
        constraints.append(FinancialRecord.record_date <= date_to)
    if search is not None:
        pattern = f"%{search.strip()}%"
        constraints.append(
            or_(
                FinancialRecord.description.ilike(pattern),
                FinancialRecord.category.ilike(pattern),
            )
        )
    return query.filter(and_(*constraints)) if constraints else query


class UserService:

    @staticmethod
    def create_user(db: Session, user_data: UserCreate) -> User:
        if db.query(User).filter(User.email == user_data.email).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A user with email '{user_data.email}' already exists.",
            )
        user = User(
            email=user_data.email,
            name=user_data.name,
            password_hash=hash_password(user_data.password),
            role=user_data.role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"User created: id={user.id}, email={user.email}, role={user.role.value}")
        return user

    @staticmethod
    def fetch_user_by_id(db: Session, user_id: int) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found.",
            )
        return user

    @staticmethod
    def list_all_users(db: Session, page: int, page_size: int) -> Tuple[List[User], int]:
        base = db.query(User).order_by(User.created_at.desc())
        total = base.count()
        users = paginate(base, page, page_size).all()
        return users, total

    @staticmethod
    def change_user_role(
        db: Session, user_id: int, update_data: UpdateRoleRequest, actor: User
    ) -> User:
        target = UserService.fetch_user_by_id(db, user_id)
        if target.id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot change your own role.",
            )
        previous_role = target.role.value
        target.role = update_data.role
        target.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(target)
        logger.info(
            f"Role changed: user_id={user_id} {previous_role}->{update_data.role.value} by admin_id={actor.id}"
        )
        return target

    @staticmethod
    def toggle_user_active_status(db: Session, user_id: int, actor: User) -> User:
        target = UserService.fetch_user_by_id(db, user_id)
        if target.id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate your own account.",
            )
        target.is_active = not target.is_active
        target.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(target)
        state = "active" if target.is_active else "inactive"
        logger.info(f"User status toggled: user_id={user_id} -> {state} by admin_id={actor.id}")
        return target


class RecordService:

    @staticmethod
    def create_record(db: Session, record_data: RecordCreate, user_id: int) -> FinancialRecord:
        record = FinancialRecord(
            user_id=user_id,
            amount=record_data.amount,
            type=record_data.type,
            category=record_data.category,
            record_date=record_data.record_date,
            description=record_data.description,
            is_deleted=False,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info(
            f"Record created: id={record.id} amount={record.amount} type={record.type.value} user_id={user_id}"
        )
        return record

    @staticmethod
    def fetch_record_by_id(db: Session, record_id: int, include_deleted: bool = False) -> FinancialRecord:
        query = db.query(FinancialRecord).filter(FinancialRecord.id == record_id)
        if not include_deleted:
            query = query.filter(FinancialRecord.is_deleted == False)
        record = query.first()
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Financial record with id {record_id} not found.",
            )
        return record

    @staticmethod
    def list_records(
        db: Session,
        record_type: Optional[RecordType] = None,
        category: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        include_deleted: bool = False,
    ) -> Tuple[List[FinancialRecord], int, int]:
        query = db.query(FinancialRecord).order_by(
            FinancialRecord.record_date.desc(),
            FinancialRecord.id.desc(),
        )
        query = apply_record_filters(query, record_type, category, date_from, date_to, search, include_deleted)
        total = query.count()
        total_pages = calculate_total_pages(total, page_size)
        records = paginate(query, page, page_size).all()
        return records, total, total_pages

    @staticmethod
    def modify_record(db: Session, record_id: int, update_data: RecordUpdate) -> FinancialRecord:
        record = RecordService.fetch_record_by_id(db, record_id)
        changed_fields = update_data.model_dump(exclude_unset=True)
        if not changed_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields provided for update.",
            )
        for field_name, value in changed_fields.items():
            setattr(record, field_name, value)
        record.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(record)
        logger.info(f"Record updated: id={record_id} fields={list(changed_fields.keys())}")
        return record

    @staticmethod
    def soft_delete_record(db: Session, record_id: int) -> FinancialRecord:
        record = RecordService.fetch_record_by_id(db, record_id, include_deleted=True)
        if record.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Record {record_id} is already deleted.",
            )
        record.is_deleted = True
        record.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(record)
        logger.info(f"Record soft-deleted: id={record_id}")
        return record


class DashboardService:

    @staticmethod
    def _active_base(db: Session):
        return db.query(FinancialRecord).filter(FinancialRecord.is_deleted == False)

    @staticmethod
    def compute_summary(db: Session) -> Dict[str, Any]:
        base = DashboardService._active_base(db)
        income_total = float(
            base.filter(FinancialRecord.type == RecordType.INCOME)
            .with_entities(func.coalesce(func.sum(FinancialRecord.amount), 0))
            .scalar()
        )
        expense_total = float(
            base.filter(FinancialRecord.type == RecordType.EXPENSE)
            .with_entities(func.coalesce(func.sum(FinancialRecord.amount), 0))
            .scalar()
        )
        record_count = base.count()
        return {
            "total_income": round(income_total, 2),
            "total_expenses": round(expense_total, 2),
            "net_balance": round(income_total - expense_total, 2),
            "total_records": record_count,
        }

    @staticmethod
    def compute_category_breakdown(db: Session) -> List[Dict[str, Any]]:
        rows = (
            DashboardService._active_base(db)
            .with_entities(
                FinancialRecord.category,
                FinancialRecord.type,
                func.sum(FinancialRecord.amount).label("total"),
                func.count(FinancialRecord.id).label("count"),
            )
            .group_by(FinancialRecord.category, FinancialRecord.type)
            .order_by(func.sum(FinancialRecord.amount).desc())
            .all()
        )
        return [
            {
                "category": row.category,
                "total": round(float(row.total), 2),
                "count": row.count,
                "type": row.type.value,
            }
            for row in rows
        ]

    @staticmethod
    def fetch_recent_activity(db: Session, limit: int = 10) -> Tuple[List[FinancialRecord], int]:
        base = DashboardService._active_base(db)
        total = base.count()
        records = (
            base.order_by(FinancialRecord.created_at.desc(), FinancialRecord.id.desc())
            .limit(min(limit, 100))
            .all()
        )
        return records, total

    @staticmethod
    def compute_trends(
        db: Session, period_type: str = "monthly", periods: int = 12
    ) -> List[Dict[str, Any]]:
        base = DashboardService._active_base(db)
        period_label = (
            func.strftime("%Y-W%W", FinancialRecord.record_date)
            if period_type == "weekly"
            else func.strftime("%Y-%m", FinancialRecord.record_date)
        ).label("period")

        income_expr = case(
            (FinancialRecord.type == RecordType.INCOME, FinancialRecord.amount),
            else_=0,
        )
        expense_expr = case(
            (FinancialRecord.type == RecordType.EXPENSE, FinancialRecord.amount),
            else_=0,
        )

        rows = (
            base.with_entities(
                period_label,
                func.sum(income_expr).label("income"),
                func.sum(expense_expr).label("expenses"),
            )
            .group_by(period_label)
            .order_by(period_label.desc())
            .limit(periods)
            .all()
        )

        trends = [
            {
                "period": row.period,
                "income": round(float(row.income or 0), 2),
                "expenses": round(float(row.expenses or 0), 2),
                "net": round(float((row.income or 0) - (row.expenses or 0)), 2),
            }
            for row in rows
        ]
        trends.reverse()
        return trends