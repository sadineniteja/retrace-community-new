"""
Supabase access JWT verification via JWKS (RS256 / ES256). No shared JWT secret.
"""

from __future__ import annotations

from typing import Any, Optional

import jwt as pyjwt
from fastapi import HTTPException, status
from jwt import PyJWKClient, exceptions as jwk_exc

from app.core.config import settings

_jwks_client: Optional[PyJWKClient] = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        base = settings.SUPABASE_URL.rstrip("/")
        _jwks_client = PyJWKClient(
            f"{base}/auth/v1/.well-known/jwks.json",
            cache_keys=True,
            lifespan=600,
        )
    return _jwks_client


def try_decode_supabase_access_token(token: str) -> Optional[dict[str, Any]]:
    """
    If the bearer token is a valid Supabase access JWT, return claims; else None.
    Never raises — used on the hot path (middleware, get_current_user).
    """
    if not (settings.SUPABASE_URL or "").strip():
        return None
    try:
        header = pyjwt.get_unverified_header(token)
        if (header.get("alg") or "").upper() == "HS256":
            return None
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
    except Exception:
        return None


def decode_supabase_login_token(token: str) -> dict[str, Any]:
    """
    Strict decode for POST /remote-login — raises HTTPException with actionable errors.
    """
    supabase_url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    if not supabase_url:
        raise HTTPException(500, "SUPABASE_URL not configured on this instance")

    try:
        header = pyjwt.get_unverified_header(token)
    except pyjwt.DecodeError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Supabase token: {exc}")

    alg = (header.get("alg") or "").upper()
    if alg == "HS256":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This app verifies Supabase tokens via JWKS only (no JWT secret). "
            "In Supabase: enable asymmetric JWT signing / signing keys so access tokens use "
            "RS256 or ES256, then retry.",
        )

    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Supabase token expired — sign in again")
    except (pyjwt.InvalidTokenError, jwk_exc.PyJWKClientError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid Supabase token: {exc}")

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub or not email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token missing sub or email")
    return payload
