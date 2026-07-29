from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from flowpilot.config import Settings
from flowpilot.schemas import Actor


ROLE_ORDER = {"viewer": 0, "operator": 1, "approver": 2, "admin": 3}


@lru_cache(maxsize=4)
def _jwk_client(url: str) -> PyJWKClient:
    return PyJWKClient(url)


def actor_from_request(request: Request, settings: Settings) -> Actor:
    if settings.auth_mode == "demo":
        if settings.environment == "production":
            raise HTTPException(status_code=500, detail="Demo auth is disabled in production")
        return Actor(
            tenant_id=request.headers.get("X-Tenant-ID", settings.demo_tenant_id),
            user_id=request.headers.get("X-User-ID", settings.demo_user_id),
            email=request.headers.get("X-User-Email", settings.demo_user_email),
            role=request.headers.get("X-User-Role", "approver"),
        )

    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    if not settings.oidc_jwks_url or not settings.oidc_audience or not settings.oidc_issuer:
        raise HTTPException(status_code=500, detail="OIDC is not fully configured")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        signing_key = _jwk_client(settings.oidc_jwks_url).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    tenant_id = str(claims.get("tenant_id") or claims.get("org_id") or "")
    subject = str(claims.get("sub") or "")
    if not tenant_id or not subject:
        raise HTTPException(status_code=403, detail="Token lacks tenant or subject claims")
    role = str(claims.get("role", "viewer"))
    if role not in ROLE_ORDER:
        role = "viewer"
    return Actor(
        tenant_id=tenant_id,
        user_id=subject,
        email=claims.get("email"),
        role=role,  # type: ignore[arg-type]
    )


def require_role(actor: Actor, minimum: str) -> None:
    if ROLE_ORDER.get(actor.role, -1) < ROLE_ORDER[minimum]:
        raise HTTPException(status_code=403, detail=f"Role {minimum} or higher is required")
