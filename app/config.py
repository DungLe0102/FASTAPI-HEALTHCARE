"""
Application settings — merged với full-stack-fastapi-template.
Thêm email / SMTP settings, FIRST_SUPERUSER (ADMIN seed), giữ lại
VietQR và các cài đặt gốc của dự án.
"""
import secrets
import warnings
from typing import Annotated, Any, Literal

from pydantic import AnyUrl, BeforeValidator, EmailStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


def _parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # ── API ────────────────────────────────────────────
    API_V1_STR: str = "/api/v1"
    APP_NAME: str = "Healthcare Management System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    # ── JWT / Auth ─────────────────────────────────────
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8   # 8 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # ── Database ───────────────────────────────────────
    DATABASE_URL: str = "postgresql://postgres:1234@localhost:5432/healthcare"

    # ── Redis ──────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    @computed_field  # type: ignore[prop-decorator]
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # ── CORS ───────────────────────────────────────────
    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(_parse_cors)
    ] = []
    FRONTEND_HOST: str = "http://localhost:5173"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        origins = [str(o).rstrip("/") for o in self.BACKEND_CORS_ORIGINS]
        origins.append(self.FRONTEND_HOST)
        return origins

    # ── Email / SMTP (template) ────────────────────────
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48
    EMAIL_TEST_USER: str = "test@example.com"

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.APP_NAME
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    # ── First superuser seed (template) ───────────────
    FIRST_SUPERUSER: str = "admin@healthcare.com"        # email của admin đầu tiên
    FIRST_SUPERUSER_PASSWORD: str = "changethis"

    # ── VietQR ─────────────────────────────────────────
    VIETQR_BANK_ID: str = "HDB"
    VIETQR_ACCOUNT_NO: str = ""
    VIETQR_ACCOUNT_NAME: str = ""
    VIETQR_CLIENT_ID: str = ""
    VIETQR_API_KEY: str = ""
    VIETQR_HOST: str = "https://api.vietqr.org"
    VIETQR_USERNAME: str = ""
    VIETQR_SECRET_KEY: str = ""

    # ── Validation ─────────────────────────────────────
    @model_validator(mode="after")
    def _warn_default_secrets(self) -> Self:
        if self.ENVIRONMENT != "local" and self.SECRET_KEY == "changethis":
            raise ValueError("SECRET_KEY must be changed for non-local environments!")
        if self.ENVIRONMENT != "local" and len(self.SECRET_KEY) < 32:
            warnings.warn(
                "SECRET_KEY is too short. Use at least 32 random characters.",
                stacklevel=1,
            )
        return self


settings = Settings()  # type: ignore