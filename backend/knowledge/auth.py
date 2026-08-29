"""
Secure admin authentication — env-driven, hashed password, JWT with admin claim.
Never exposes credentials to frontend.
"""
import hashlib
import uuid
import time
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password

# Simple in-memory rate limiter for login
_login_attempts: dict[str, list[float]] = {}


def _get_admin_username() -> str:
    return getattr(settings, "ADMIN_USERNAME", "admin")


def _get_admin_password() -> str:
    return getattr(settings, "ADMIN_PASSWORD", "admin123")


def _get_admin_hash() -> str:
    return getattr(settings, "ADMIN_PASSWORD_HASH", "")


def _get_secret() -> str:
    return getattr(settings, "ADMIN_JWT_SECRET", getattr(settings, "SECRET_KEY", "change-me"))


def _get_expiry_hours() -> int:
    return getattr(settings, "ADMIN_JWT_EXPIRY_HOURS", 12)


def verify_admin_credentials(username: str, password: str) -> bool:
    expected_user = _get_admin_username()
    if username != expected_user:
        return False
    h = _get_admin_hash()
    if h:
        # Support both Django hashed format and raw sha256 fallback
        try:
            if h.startswith("pbkdf2") or h.startswith("bcrypt") or h.startswith("argon2"):
                return check_password(password, h)
            # Assume sha256 hex if 64 chars
            if len(h) == 64 and all(c in "0123456789abcdef" for c in h.lower()):
                return hashlib.sha256(password.encode()).hexdigest() == h.lower()
            return check_password(password, h)
        except Exception:
            return False
    # Fallback plaintext dev credentials
    return password == _get_admin_password()


def create_admin_token(username: str) -> tuple[str, str, datetime]:
    jti = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=_get_expiry_hours())
    payload = {
        "sub": username,
        "is_admin": True,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    token = jwt.encode(payload, _get_secret(), algorithm="HS256")
    # Track session
    try:
        from .models import AdminSession
        AdminSession.objects.create(
            admin_username=username,
            jti=jti,
            expires_at=exp,
            is_valid=True,
        )
    except Exception:
        pass
    return token, jti, exp


def verify_admin_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        if not payload.get("is_admin"):
            return None
        jti = payload.get("jti")
        # Check session validity if exists
        try:
            from .models import AdminSession
            sess = AdminSession.objects.filter(jti=jti).first()
            if sess and not sess.is_valid:
                return None
            if sess and sess.expires_at < datetime.now(timezone.utc):
                return None
        except Exception:
            pass
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def check_rate_limit(ip: str) -> bool:
    """Return True if allowed, False if rate-limited (5/min)."""
    now = time.time()
    lst = _login_attempts.get(ip, [])
    lst = [t for t in lst if now - t < 60]
    if len(lst) >= 5:
        _login_attempts[ip] = lst
        return False
    lst.append(now)
    _login_attempts[ip] = lst
    return True


def make_hash_for_env(password: str) -> str:
    """Helper to generate Django hash for ADMIN_PASSWORD_HASH."""
    return make_password(password)
