"""
Healthcare Management System — FastAPI application entry point.

Architecture aligned with full-stack-fastapi-template:
  - All routes under /api/v1 prefix
  - CORS driven by settings (supports whitelist)
  - Swagger UI available at /docs, ReDoc at /redoc
  - DB tables created at startup (dev mode; use Alembic for production)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
import redis.asyncio as redis
from fastapi_limiter import FastAPILimiter

from app.config import settings
from app.db import Base, engine

# ── Import all models so SQLAlchemy Base knows about them ────────────────────
import app.models  # noqa: F401

# ── Import routers ────────────────────────────────────────────────────────────
from app.routers.auth import router as auth_router
from app.routers.department import router as department_router
from app.routers.patient import router as patient_router
from app.routers.doctor import router as doctor_router
from app.routers.appointment import router as appointment_router
from app.routers.medical_record import router as medical_record_router
from app.routers.inventory import router as inventory_router
from app.routers.billing import router as billing_router
from app.routers.notification import router as notification_router
from app.routers.audit import router as audit_router
from app.routers.websocket import router as websocket_router


# ── Unique operationId generator (same as template) ──────────────────────────
def custom_generate_unique_id(route: APIRoute) -> str:
    """Generate clean operationIds for OpenAPI clients / code-gen."""
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev: auto-create tables. Production → use Alembic migrations instead.
    Base.metadata.create_all(bind=engine)

    # Auto-seed the first superuser (ADMIN) if it doesn't exist
    from app.db import SessionLocal
    from app.models.account import Account
    from app.security import get_password_hash
    
    with SessionLocal() as db:
        admin_email = settings.FIRST_SUPERUSER
        if not db.query(Account).filter(Account.email == admin_email).first():
            admin_account = Account(
                email=admin_email,
                full_name="Super Admin",
                password_hash=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                role="ADMIN",
                is_active=True,
                email_verified=True,
            )
            db.add(admin_account)
            db.commit()
            print(f"Created FIRST_SUPERUSER: {admin_email}")

    # Initialize Redis for Rate Limiting
    try:
        redis_connection = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
        # Test connection
        await redis_connection.ping()
        await FastAPILimiter.init(redis_connection)
        print("Redis connected successfully.")
    except Exception as e:
        print(f"WARNING: Could not connect to Redis at {settings.REDIS_URL}. Rate limiting will not work.")
        redis_connection = None

    yield
    # Shutdown logic
    if redis_connection:
        await redis_connection.close()



# ── App factory ───────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    generate_unique_id_function=custom_generate_unique_id,
    swagger_ui_parameters={"persistAuthorization": True},
)


# ── CORS middleware ───────────────────────────────────────────────────────────
# In production, set BACKEND_CORS_ORIGINS in .env to restrict allowed origins.
cors_origins = settings.all_cors_origins or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API v1 router prefix ──────────────────────────────────────────────────────
PREFIX = settings.API_V1_STR

from app.routers.order import router as order_router
from app.routers.report import router as report_router

# Workflow Order: Auth -> Setup -> Clinical -> Patient -> Appointment -> Billing -> Records -> System
app.include_router(auth_router,           prefix=PREFIX)
app.include_router(department_router,     prefix=PREFIX)
app.include_router(doctor_router,         prefix=PREFIX)
app.include_router(patient_router,        prefix=PREFIX)
app.include_router(appointment_router,    prefix=PREFIX)
app.include_router(billing_router,        prefix=PREFIX)
app.include_router(medical_record_router, prefix=PREFIX)
app.include_router(inventory_router,      prefix=PREFIX)
app.include_router(notification_router,   prefix=PREFIX)
app.include_router(audit_router,          prefix=PREFIX)
app.include_router(order_router,          prefix=PREFIX)
app.include_router(report_router,         prefix=PREFIX)
app.include_router(websocket_router,      prefix=PREFIX)



# ── Health check ─────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"], include_in_schema=False)
def health_check():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
    }