import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from models import get_db, User, UserRole, ROLE_HIERARCHY

logger = logging.getLogger(__name__)

SECRET_KEY = "finance-dashboard-super-secret-key-change-in-production-2024"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

bearer_scheme = HTTPBearer(auto_error=False)

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        logger.warning("Password verification encountered an unexpected error")
        return False


def create_access_token(
    user_id: int,
    role: UserRole,
    expires_delta: Optional[timedelta] = None,
) -> str:
    issued_at = datetime.now(timezone.utc)
    expiry = expires_delta if expires_delta else timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "exp": issued_at + expiry,
        "iat": issued_at,
        "type": "access",
    }
    logger.info(f"Access token issued for user_id={user_id}, role={role.value}")
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    missing_claims = {"sub", "role"} - payload.keys()
    if missing_claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token is missing required claims: {missing_claims}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)

    try:
        user_id = int(payload["sub"])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token contains invalid user identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found. Token may be stale.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact administrator.",
        )

    request.state.current_user = user
    return user


def require_role(min_role: UserRole):
    required_level = ROLE_HIERARCHY[min_role]

    def role_gate(current_user: User = Depends(get_current_user)) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        if user_level < required_level:
            logger.warning(
                f"Access denied: user_id={current_user.id} "
                f"role={current_user.role.value} required={min_role.value}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. "
                    f"Required: {min_role.value}, "
                    f"Your role: {current_user.role.value}."
                ),
            )
        return current_user

    role_gate.__name__ = f"require_{min_role.value}"
    return role_gate


def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        return (
            db.query(User)
            .filter(User.id == user_id, User.is_active == True)
            .first()
        )
    except Exception:
        return None


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        return None
    logger.info(f"Successful authentication for user_id={user.id}")
    return user