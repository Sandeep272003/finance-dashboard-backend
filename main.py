import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text

from models import Base, engine, SessionLocal, User, UserRole
from auth import hash_password, ACCESS_TOKEN_EXPIRE_HOURS

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, handlers=[logging.StreamHandler(sys.stdout)])
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("finance_app")

SEED_ADMIN_EMAIL = "admin@finance.com"
SEED_ADMIN_PASSWORD = "admin123"
SEED_ADMIN_NAME = "System Administrator"


def ensure_admin_exists():
    db = SessionLocal()
    try:
        if db.query(User).filter(User.role == UserRole.ADMIN).first():
            logger.info("Admin user already exists")
            return
        admin = User(
            email=SEED_ADMIN_EMAIL,
            name=SEED_ADMIN_NAME,
            password_hash=hash_password(SEED_ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        logger.info(f"Default admin seeded: {SEED_ADMIN_EMAIL} / {SEED_ADMIN_PASSWORD}")
    except Exception as exc:
        logger.error(f"Admin seed failed: {exc}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("Finance Dashboard Backend — Starting")
    Base.metadata.create_all(bind=engine)
    ensure_admin_exists()
    logger.info(f"Token expiry: {ACCESS_TOKEN_EXPIRE_HOURS}h | DB: SQLite")
    logger.info(f"Docs: http://localhost:8000/docs")
    logger.info(f"Admin: {SEED_ADMIN_EMAIL} / {SEED_ADMIN_PASSWORD}")
    logger.info("=" * 60)
    yield
    logger.info("Finance Dashboard Backend — Shutting down")
    engine.dispose()


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000
        identity = "anonymous"
        if hasattr(request.state, "current_user"):
            u = request.state.current_user
            identity = f"{u.email}({u.role.value})"
        log_fn = logger.error if response.status_code >= 500 else (
            logger.warning if response.status_code >= 400 else logger.info
        )
        log_fn(f"{request.method:7s} {request.url.path} -> {response.status_code} [{elapsed_ms:.1f}ms] {identity}")
        return response


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    formatted = [
        {
            "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
            "message": err.get("msg", "Validation error"),
            "type": err.get("type", "value_error"),
        }
        for err in exc.errors()
    ]
    logger.warning(f"Validation error on {request.method} {request.url.path}: {formatted}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "detail": "One or more fields failed validation.",
            "status_code": 422,
            "errors": formatted,
        },
    )


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later.",
            "status_code": 500,
        },
    )


app = FastAPI(
    title="Finance Dashboard API",
    description="Backend for a finance dashboard system with role-based access control, financial record management, and analytics.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestTimingMiddleware)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(Exception, unhandled_handler)

from routes import auth_router, users_router, records_router, dashboard_router

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(records_router)
app.include_router(dashboard_router)


@app.get("/health", tags=["System"])
async def health_check():
    db_status = "connected"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_status = "disconnected"
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "version": "1.0.0",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, log_level="info", access_log=False, lifespan="on")
