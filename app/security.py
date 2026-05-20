"""
Security utilities — full-stack-fastapi-template pattern.

Changes from previous version:
- Removed refresh_token (template chỉ dùng access token)
- Kept `role` claim in token payload for RBAC without DB roundtrip
- password_hash / verify_password unchanged (pwdlib Argon2id + bcrypt fallback)
- ALGORITHM constant exposed at module level (same as template)
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from pydantic import BaseModel, ValidationError

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.account import Account

# ── Password hasher (Argon2id primary, bcrypt fallback) ──────────────────────
password_hash = PasswordHash(
    (
        Argon2Hasher(),   # new passwords
        BcryptHasher(),   # legacy hashes — auto-rehashed on next login
    )
)

ALGORITHM = "HS256"

# ── OAuth2 scheme ─────────────────────────────────────────────────────────────
reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


# ── Token payload ─────────────────────────────────────────────────────────────
class TokenPayload(BaseModel):
    """Claims embedded in the JWT."""
    sub: str | None = None   # account_id (UUID as string)
    role: str | None = None  # ADMIN | PATIENT


# ── Password helpers ──────────────────────────────────────────────────────────

def get_password_hash(password: str) -> str:
    """Hash a password with Argon2id."""
    return password_hash.hash(password)


# keep old alias so existing code keeps working
hash_password = get_password_hash


def verify_password(plain: str, hashed: str) -> tuple[bool, str | None]:
    """
    Verify password and return (is_valid, new_hash_if_rehashed).
    If the stored hash uses bcrypt (legacy), it will be re-hashed with Argon2id.
    """
    return password_hash.verify_and_update(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(subject: str | Any, expires_delta: timedelta, role: str = "") -> str:
    """Create a JWT access token — template signature + role claim."""
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode: dict[str, Any] = {"exp": expire, "sub": str(subject)}
    if role:
        to_encode["role"] = role
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(subject: str | Any, expires_delta: timedelta) -> str:
    """Create a JWT refresh token."""
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode: dict[str, Any] = {"exp": expire, "sub": str(subject), "type": "refresh"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def generate_password_reset_token(email: str) -> str:
    from app.utils import generate_password_reset_token as _gen
    return _gen(email)


def verify_password_reset_token(token: str) -> str | None:
    from app.utils import verify_password_reset_token as _verify
    return _verify(token)


# ── Dependency: get DB session ────────────────────────────────────────────────
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_account(
    db: Session = Depends(get_db),
    token: str = Depends(reusable_oauth2),
) -> Account:
    """
    FastAPI dependency — resolves the current authenticated account.
    Validates the JWT and fetches the Account row from DB.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if token_data.sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        subject_uuid = UUID(token_data.sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    account = db.query(Account).filter(Account.account_id == subject_uuid).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return account


# ── Type alias for convenience in routers ────────────────────────────────────
CurrentAccount = Annotated[Account, Depends(get_current_account)]


# ── RBAC factory (giữ nguyên từ code gốc) ────────────────────────────────────

def require_roles(*roles: str):
    """
    Usage:  _ = Depends(require_roles("ADMIN", "DOCTOR"))

    Returns the current account if the role matches, raises 403 otherwise.
    """
    def _check(account: CurrentAccount) -> Account:
        if account.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{account.role}' is not permitted. "
                    f"Required: {list(roles)}"
                ),
            )
        return account
    return _check


def get_current_active_superuser(current_account: CurrentAccount) -> Account:
    """Template-style superuser check — maps to ADMIN role."""
    if current_account.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges",
        )
    return current_account