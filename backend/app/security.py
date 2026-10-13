"""Authentication and short-lived BLE token helpers.

This prototype uses opaque bearer tokens stored as SHA-256 digests and
PBKDF2 password hashes. For production, add refresh/revocation policies,
rate limiting, HTTPS, and managed secrets.
"""
import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import ApiToken, User

PASSWORD_ITERATIONS = 310_000
ACCESS_TOKEN_TTL_HOURS = 24
BLE_TOKEN_ROTATION_SECONDS = 20
BLE_TOKEN_BYTES = 8
MIN_RSSI_DBM = int(os.getenv("PROXYPROOF_MIN_RSSI_DBM", "-88"))
bearer_scheme = HTTPBearer(auto_error=False)


def utc_now_naive() -> datetime:
    """Use naive UTC timestamps for consistent SQLite storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256\u0024{PASSWORD_ITERATIONS}\u0024{salt.hex()}\u0024{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, expected_hex = stored_hash.split("\u0024", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations_text),
        )
        return hmac.compare_digest(digest.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def hash_access_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_access_token(db: Session, user: User) -> tuple[str, datetime]:
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_TTL_HOURS)
    db.add(
        ApiToken(
            token_hash=hash_access_token(raw_token),
            user_id=user.id,
            expires_at=expires_at.replace(tzinfo=None),
        )
    )
    return raw_token, expires_at


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    digest = hash_access_token(credentials.credentials)
    token = db.get(ApiToken, digest)
    now = utc_now_naive()
    if token is None or token.expires_at <= now:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User account is inactive.")
    return user


def require_role(*allowed_roles: str) -> Callable:
    """Create a FastAPI dependency restricting access to explicit roles."""
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Your role cannot perform this action.")
        return user
    return dependency


def _attendance_secret() -> bytes:
    secret = os.getenv(
        "PROXYPROOF_TOKEN_SECRET",
        "local-development-secret-change-before-deployment",
    )
    return secret.encode("utf-8")


def current_ble_slot(now_epoch: float | None = None) -> int:
    return int((time.time() if now_epoch is None else now_epoch) // BLE_TOKEN_ROTATION_SECONDS)


def make_ble_token(session_id: str, slot: int | None = None) -> str:
    """Return a compact 8-byte token encoded as 16 lowercase hex characters."""
    slot_number = current_ble_slot() if slot is None else slot
    message = f"{session_id}:{slot_number}".encode("utf-8")
    digest = hmac.new(_attendance_secret(), message, hashlib.sha256).digest()
    return digest[:BLE_TOKEN_BYTES].hex()


def valid_ble_token(session_id: str, candidate: str, now_epoch: float | None = None) -> bool:
    if len(candidate) != BLE_TOKEN_BYTES * 2:
        return False
    slot = current_ble_slot(now_epoch)
    # Accept current and previous slot so a token near a rotation boundary
    # has a brief grace period. The session deadline is still enforced separately.
    return any(
        hmac.compare_digest(make_ble_token(session_id, slot - offset), candidate.lower())
        for offset in (0, 1)
    )
