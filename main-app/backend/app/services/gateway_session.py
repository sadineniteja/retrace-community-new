"""
Session-scoped LLM gateway signing material.

The Cloudflare edge expects X-Gateway-Sig = ts.HMAC(secret, ts). The shared secret is stored
in the users table encrypted with the user's password (PBKDF2 + AES-GCM). At login we decrypt
with the password they just typed and keep the plaintext only in memory until logout / expiry.

Connect-ask-act (or an admin) can populate llm_gateway_secret_blob / llm_gateway_secret_salt
per user; ReTrace never ships that secret in .env per customer.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import threading
import time
from contextvars import ContextVar
from typing import TYPE_CHECKING, Optional

# Set by middleware when the incoming request carries a Supabase access JWT.
# When present, this token IS the gateway credential — the Worker validates it
# directly via JWKS, so no HMAC signing is needed.
gateway_supabase_token: ContextVar[Optional[str]] = ContextVar("gateway_supabase_token", default=None)

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.core.config import settings

if TYPE_CHECKING:
    from app.models.user import User

PBKDF2_ITERATIONS = 390_000
PENDING_MFA_TTL_S = 600

_lock = threading.Lock()
# user_id -> (plaintext_hmac_secret, expires_unix)
_session_gateway: dict[str, tuple[str, float]] = {}
# user_id -> (plaintext_hmac_secret, expires_unix) between password OK and MFA complete
_pending_mfa_gateway: dict[str, tuple[str, float]] = {}

# Set by HTTP middleware from Bearer JWT (sub)
llm_gateway_request_user_id: ContextVar[Optional[str]] = ContextVar("llm_gateway_request_user_id", default=None)


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_llm_gateway_secret(plaintext_secret: str, password: str) -> tuple[str, str]:
    """Return (blob_b64, salt_b64) for storage on User."""
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext_secret.encode("utf-8"), None)
    blob = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    return blob, salt_b64


def decrypt_llm_gateway_secret(blob_b64: str, salt_b64: str, password: str) -> Optional[str]:
    try:
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        raw = base64.urlsafe_b64decode(blob_b64.encode("ascii"))
        nonce, ct = raw[:12], raw[12:]
        key = _derive_key(password, salt)
        aes = AESGCM(key)
        pt = aes.decrypt(nonce, ct, None)
        return pt.decode("utf-8")
    except Exception:
        return None


def try_load_gateway_secret_at_login(user: User, password_plain: str) -> Optional[str]:
    blob = getattr(user, "llm_gateway_secret_blob", None)
    salt = getattr(user, "llm_gateway_secret_salt", None)
    if not blob or not salt:
        return None
    return decrypt_llm_gateway_secret(blob, salt, password_plain)


def store_session_gateway_secret(user_id: str, secret: str) -> None:
    exp = time.time() + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    with _lock:
        _session_gateway[user_id] = (secret, exp)


def extend_session_gateway_ttl(user_id: str) -> None:
    with _lock:
        tup = _session_gateway.get(user_id)
        if tup:
            secret, _ = tup
            exp = time.time() + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
            _session_gateway[user_id] = (secret, exp)


def clear_session_gateway_secret(user_id: str) -> None:
    with _lock:
        _session_gateway.pop(user_id, None)
        _pending_mfa_gateway.pop(user_id, None)


def stash_pending_gateway_for_mfa(user_id: str, secret: str) -> None:
    exp = time.time() + PENDING_MFA_TTL_S
    with _lock:
        _pending_mfa_gateway[user_id] = (secret, exp)


def promote_pending_gateway_to_session(user_id: str) -> None:
    with _lock:
        tup = _pending_mfa_gateway.pop(user_id, None)
    if tup:
        secret, _ = tup
        store_session_gateway_secret(user_id, secret)


def get_session_gateway_secret(user_id: str) -> Optional[str]:
    with _lock:
        tup = _session_gateway.get(user_id)
        if not tup:
            return None
        secret, exp = tup
        if time.time() > exp:
            _session_gateway.pop(user_id, None)
            return None
        return secret


def gateway_hmac_headers(secret: str) -> dict[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode("utf-8"), ts.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"X-Gateway-Sig": f"{ts}.{sig}"}


def gateway_llm_headers() -> dict[str, str]:
    """
    Extra headers for outbound managed-gateway calls.

    Supabase JWT path: the JWT travels as api_key/Authorization — no extra headers needed.
    HMAC path (email / enterprise logins): return X-Gateway-Sig.
    """
    # Supabase JWT users: Worker validates the JWT from the Authorization header itself.
    if gateway_supabase_token.get():
        return {}

    uid = llm_gateway_request_user_id.get()
    if uid:
        sec = get_session_gateway_secret(uid)
        if sec:
            return gateway_hmac_headers(sec)

    fb = (settings.GATEWAY_EDGE_FALLBACK_HMAC_SECRET or "").strip()
    if fb:
        return gateway_hmac_headers(fb)

    return {}
