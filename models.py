import enum
from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    Text, Date, DateTime, Enum, ForeignKey, Index, CheckConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from fastapi import Depends

DATABASE_URL = "sqlite:///./finance_dashboard.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class UserRole(str, enum.Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"


class RecordType(str, enum.Enum):
    INCOME = "income"
    EXPENSE = "expense"


ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.VIEWER: 1,
    UserRole.ANALYST: 2,
    UserRole.ADMIN: 3,
}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    records = relationship(
        "FinancialRecord",
        back_populates="user",
        lazy="select",
        order_by="FinancialRecord.record_date.desc()",
    )

    __table_args__ = (
        CheckConstraint("length(email) > 0", name="ck_user_email_nonempty"),
        CheckConstraint("length(name) > 0", name="ck_user_name_nonempty"),
    )

    @property
    def role_level(self) -> int:
        return ROLE_HIERARCHY[self.role]


class FinancialRecord(Base):
    __tablename__ = "financial_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    type = Column(Enum(RecordType), nullable=False)
    category = Column(String(100), nullable=False)
    record_date = Column(Date, nullable=False)
    description = Column(Text, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="records")

    __table_args__ = (
        Index("idx_record_date_type", "record_date", "type"),
        Index("idx_record_category", "category"),
        Index("idx_record_user_date", "user_id", "record_date"),
        Index("idx_record_active", "is_deleted", "record_date"),
        CheckConstraint("amount > 0", name="ck_record_amount_positive"),
    )

    @property
    def signed_amount(self) -> float:
        return self.amount if self.type == RecordType.INCOME else -self.amount


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"


class UserCreate(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    role: UserRole = Field(default=UserRole.VIEWER)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Must be a valid email address")
        return v

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int


class UpdateRoleRequest(BaseModel):
    role: UserRole


class RecordCreate(BaseModel):
    amount: float = Field(..., gt=0)
    type: RecordType
    category: str = Field(..., min_length=1, max_length=100)
    record_date: date
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator("category")
    @classmethod
    def title_case_category(cls, v: str) -> str:
        return v.strip().title()

    @field_validator("amount")
    @classmethod
    def precision_amount(cls, v: float) -> float:
        return round(v, 2)


class RecordUpdate(BaseModel):
    amount: Optional[float] = Field(None, gt=0)
    type: Optional[RecordType] = None
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    record_date: Optional[date] = None
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator("category")
    @classmethod
    def title_case_category(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().title() if v is not None else v

    @field_validator("amount")
    @classmethod
    def precision_amount(cls, v: Optional[float]) -> Optional[float]:
        return round(v, 2) if v is not None else v


class RecordResponse(BaseModel):
    id: int
    user_id: int
    amount: float
    type: RecordType
    category: str
    record_date: date
    description: Optional[str] = None
    is_deleted: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class RecordListResponse(BaseModel):
    records: List[RecordResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DashboardSummary(BaseModel):
    total_income: float = 0.0
    total_expenses: float = 0.0
    net_balance: float = 0.0
    total_records: int = 0


class CategoryTotal(BaseModel):
    category: str
    total: float
    count: int
    type: RecordType


class CategoryBreakdown(BaseModel):
    categories: List[CategoryTotal] = Field(default_factory=list)


class TrendPoint(BaseModel):
    period: str
    income: float = 0.0
    expenses: float = 0.0
    net: float = 0.0


class TrendResponse(BaseModel):
    trends: List[TrendPoint] = Field(default_factory=list)
    period_type: str


class RecentActivity(BaseModel):
    records: List[RecordResponse] = Field(default_factory=list)
    total: int = 0


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int