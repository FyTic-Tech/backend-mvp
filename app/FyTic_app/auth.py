from dataclasses import dataclass
import hmac

import jwt
from jwt import PyJWKClient
from fastapi import Depends, Header, HTTPException

from app.config import settings
from app.db import get_db

INTERNAL_ROLES = {"super_admin", "internal_dev", "internal_team"}
ORG_ROLES = {"admin", "member", "limited", "super_admin"}

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(
            f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
        )
    return _jwks_client


@dataclass
class AuthUser:
    user_id: str
    org_id: str | None
    role: str


def _decode_jwt(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization[7:]
    if not settings.supabase_url:
        raise HTTPException(503, "Supabase URL not configured")
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["HS256", "ES256"],
            audience="authenticated",
        )
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def get_current_user(authorization: str = Header(...)) -> AuthUser:
    user_id = _decode_jwt(authorization)
    db = get_db()
    result = (
        db.table("users")
        .select("org_id,role,is_active,deleted_at")
        .eq("id", user_id)
        .execute()
    )
    if not result.data or result.data[0].get("deleted_at"):
        raise HTTPException(403, "User not found or deactivated")
    row = result.data[0]
    if not row.get("is_active", True):
        raise HTTPException(403, "Account deactivated")
    return AuthUser(user_id=user_id, org_id=row.get("org_id"), role=row.get("role", ""))


def require_org(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.org_id:
        raise HTTPException(403, "No organization assigned")
    if user.role not in ORG_ROLES:
        raise HTTPException(403, "Not an org member")
    return user


def require_write(user: AuthUser = Depends(require_org)) -> AuthUser:
    """Blocks limited role from mutating endpoints marked 📖."""
    if user.role == "limited":
        raise HTTPException(403, "Limited role is read-only for this action")
    return user


def require_admin(user: AuthUser = Depends(require_org)) -> AuthUser:
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(403, "Admin role required")
    return user


def require_internal(
    user: AuthUser = Depends(get_current_user),
    x_internal_key: str | None = Header(default=None, alias="X-Internal-Key"),
) -> AuthUser:
    if user.role not in INTERNAL_ROLES:
        raise HTTPException(403, "Internal role required")
    if not settings.internal_api_key or not hmac.compare_digest(
        x_internal_key or "", settings.internal_api_key
    ):
        raise HTTPException(403, "Invalid or missing X-Internal-Key")
    return user
