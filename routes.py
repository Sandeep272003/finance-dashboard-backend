import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

from models import (
    get_db, User, UserRole, RecordType,
    LoginRequest, UserCreate, UserResponse, UserListResponse,
    UpdateRoleRequest, RecordCreate, RecordUpdate, RecordResponse,
    RecordListResponse, DashboardSummary, CategoryBreakdown,
    TrendResponse, RecentActivity, ErrorResponse,
)
from auth import authenticate_user, create_access_token, ACCESS_TOKEN_EXPIRE_HOURS, get_current_user, require_role
from services import UserService, RecordService, DashboardService

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/api/users", tags=["User Management"])
records_router = APIRouter(prefix="/api/records", tags=["Financial Records"])
dashboard_router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Analytics"])


@auth_router.post("/login", responses={401: {"model": ErrorResponse}})
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, login_data.email, login_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user.id, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        },
    }


@auth_router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return UserService.create_user(db, user_data)


@auth_router.get("/me", response_model=UserResponse, responses={401: {"model": ErrorResponse}})
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@users_router.get("", response_model=UserListResponse, responses={403: {"model": ErrorResponse}})
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    users, total = UserService.list_all_users(db, page, page_size)
    return {"users": users, "total": total, "page": page, "page_size": page_size}


@users_router.get("/{user_id}", response_model=UserResponse, responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}})
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return UserService.fetch_user_by_id(db, user_id)


@users_router.put(
    "/{user_id}/role",
    response_model=UserResponse,
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_user_role(
    user_id: int,
    update_data: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return UserService.change_user_role(db, user_id, update_data, current_user)


@users_router.patch(
    "/{user_id}/status",
    responses={404: {"model": ErrorResponse}, 400: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def toggle_user_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    user = UserService.toggle_user_active_status(db, user_id, current_user)
    return {
        "message": f"User '{user.email}' is now {'active' if user.is_active else 'inactive'}.",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_active": user.is_active,
            "role": user.role.value,
        },
    }


@records_router.post(
    "",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_record(
    record_data: RecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST)),
):
    return RecordService.create_record(db, record_data, current_user.id)


@records_router.get("", response_model=RecordListResponse, responses={403: {"model": ErrorResponse}})
async def list_records(
    type: Optional[RecordType] = Query(None),
    category: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST)),
):
    if include_deleted and current_user.role != UserRole.ADMIN:
        include_deleted = False
    records, total, total_pages = RecordService.list_records(
        db, type, category, date_from, date_to, search, page, page_size, include_deleted
    )
    return {
        "records": records,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@records_router.get(
    "/{record_id}",
    response_model=RecordResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST)),
):
    return RecordService.fetch_record_by_id(db, record_id)


@records_router.put(
    "/{record_id}",
    response_model=RecordResponse,
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def update_record(
    record_id: int,
    update_data: RecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return RecordService.modify_record(db, record_id, update_data)


@records_router.delete(
    "/{record_id}",
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 400: {"model": ErrorResponse}},
)
async def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    record = RecordService.soft_delete_record(db, record_id)
    return {"message": f"Record {record_id} has been deleted.", "record_id": record.id, "deleted": True}


@dashboard_router.get("/summary", response_model=DashboardSummary, responses={403: {"model": ErrorResponse}})
async def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DashboardService.compute_summary(db)


@dashboard_router.get("/categories", response_model=CategoryBreakdown, responses={403: {"model": ErrorResponse}})
async def get_category_breakdown(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"categories": DashboardService.compute_category_breakdown(db)}


@dashboard_router.get("/recent", response_model=RecentActivity, responses={403: {"model": ErrorResponse}})
async def get_recent_activity(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records, total = DashboardService.fetch_recent_activity(db, limit)
    return {"records": records, "total": total}


@dashboard_router.get("/trends", response_model=TrendResponse, responses={403: {"model": ErrorResponse}})
async def get_trends(
    period_type: str = Query("monthly", pattern="^(monthly|weekly)$"),
    months: int = Query(12, ge=1, le=36),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ANALYST)),
):
    return {"trends": DashboardService.compute_trends(db, period_type, months), "period_type": period_type}