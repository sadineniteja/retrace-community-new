"""
Connected accounts API — manage OAuth, API key, and cookie credentials for Brains.

Provides endpoints to:
- Start OAuth flow (get authorization URL)
- Handle OAuth callback (exchange code for tokens)
- Store API keys / cookies directly
- List, verify, disconnect accounts
"""

import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, CurrentUser
from app.db.database import get_session
from app.services.brain_manager import brain_manager
from app.services.credential_manager import credential_manager

logger = structlog.get_logger()
router = APIRouter()

# In-memory store for OAuth state → (brain_id, provider, redirect_uri)
# In production, use Redis or a short-lived DB row.
_oauth_states: dict[str, dict] = {}


# ── Schemas ───────────────────────────────────────────────────────────


class AccountResponse(BaseModel):
    account_id: str
    brain_id: str
    provider: str
    provider_display_name: str
    account_identifier: Optional[str] = None
    auth_type: str
    status: str
    status_message: Optional[str] = None
    is_active: bool
    last_used_at: Optional[str] = None
    last_verified_at: Optional[str] = None
    created_at: Optional[str] = None


class OAuthStartRequest(BaseModel):
    provider: str = Field(..., pattern="^(google|linkedin|github|twitter)$")
    redirect_uri: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class ApiKeyStoreRequest(BaseModel):
    provider: str
    api_key: str
    api_secret: Optional[str] = None
    display_name: Optional[str] = None
    account_identifier: Optional[str] = None


class CookieStoreRequest(BaseModel):
    provider: str
    cookies: list[dict]
    user_agent: Optional[str] = None
    display_name: Optional[str] = None
    account_identifier: Optional[str] = None


# ── List / Get ────────────────────────────────────────────────────────


@router.get("/{brain_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    brain_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all connected accounts for a brain."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    accounts = await credential_manager.list_accounts(session, brain_id, current_user.user_id)
    return [AccountResponse(**a.to_dict()) for a in accounts]


@router.get("/{brain_id}/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    brain_id: str,
    account_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a specific connected account."""
    account = await credential_manager.get_account(session, account_id, current_user.user_id)
    if not account or account.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponse(**account.to_dict())


# ── OAuth Flow ────────────────────────────────────────────────────────


def _get_provider(name: str):
    if name == "google":
        from app.services.oauth_providers.google import google_oauth
        return google_oauth
    elif name == "linkedin":
        from app.services.oauth_providers.linkedin import linkedin_oauth
        return linkedin_oauth
    elif name == "github":
        from app.services.oauth_providers.github import github_oauth
        return github_oauth
    elif name == "twitter":
        from app.services.oauth_providers.twitter import twitter_oauth
        return twitter_oauth
    raise ValueError(f"Unknown provider: {name}")


@router.post("/{brain_id}/accounts/oauth/start")
async def oauth_start(
    brain_id: str,
    data: OAuthStartRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Start an OAuth flow — returns the authorization URL to redirect the user to."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    provider = _get_provider(data.provider)
    state = secrets.token_urlsafe(32)

    _oauth_states[state] = {
        "brain_id": brain_id,
        "user_id": current_user.user_id,
        "provider": data.provider,
        "redirect_uri": data.redirect_uri,
    }

    auth_url = provider.get_authorization_url(data.redirect_uri, state)
    return {"authorization_url": auth_url, "state": state}


@router.post("/{brain_id}/accounts/oauth/callback", response_model=AccountResponse)
async def oauth_callback(
    brain_id: str,
    data: OAuthCallbackRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Handle OAuth callback — exchange code for tokens and store the account."""
    state_data = _oauth_states.pop(data.state, None)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    if state_data["brain_id"] != brain_id or state_data["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="State mismatch")

    provider_name = state_data["provider"]
    redirect_uri = state_data["redirect_uri"]
    provider = _get_provider(provider_name)

    try:
        tokens = await provider.exchange_code(data.code, redirect_uri)
    except Exception as e:
        logger.error("OAuth code exchange failed", provider=provider_name, error=str(e))
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {str(e)}")

    # Get user info for account identifier
    account_identifier = None
    try:
        user_info = await provider.get_user_info(tokens.access_token)
        account_identifier = user_info.email or user_info.display_name
    except Exception:
        pass

    expires_at = None
    if tokens.expires_in:
        expires_at = datetime.utcnow() + timedelta(seconds=tokens.expires_in)

    account = await credential_manager.store_oauth_tokens(
        session,
        brain_id=brain_id,
        user_id=current_user.user_id,
        provider=provider_name,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=expires_at,
        scopes=tokens.scopes,
        display_name=provider.display_name,
        account_identifier=account_identifier,
    )
    await session.commit()
    return AccountResponse(**account.to_dict())


# ── API Key Storage ───────────────────────────────────────────────────


@router.post("/{brain_id}/accounts/api-key", response_model=AccountResponse, status_code=201)
async def store_api_key(
    brain_id: str,
    data: ApiKeyStoreRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Store an API key credential for a brain."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    account = await credential_manager.store_api_key(
        session,
        brain_id=brain_id,
        user_id=current_user.user_id,
        provider=data.provider,
        api_key=data.api_key,
        api_secret=data.api_secret,
        display_name=data.display_name,
        account_identifier=data.account_identifier,
    )
    await session.commit()
    return AccountResponse(**account.to_dict())


# ── Cookie Storage ────────────────────────────────────────────────────


@router.post("/{brain_id}/accounts/cookies", response_model=AccountResponse, status_code=201)
async def store_cookies(
    brain_id: str,
    data: CookieStoreRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Store browser cookies for a brain (e.g., LinkedIn session)."""
    brain = await brain_manager.get_brain(session, brain_id, current_user.user_id)
    if not brain:
        raise HTTPException(status_code=404, detail="Brain not found")

    account = await credential_manager.store_cookies(
        session,
        brain_id=brain_id,
        user_id=current_user.user_id,
        provider=data.provider,
        cookies=data.cookies,
        user_agent=data.user_agent,
        display_name=data.display_name,
        account_identifier=data.account_identifier,
    )
    await session.commit()
    return AccountResponse(**account.to_dict())


# ── Disconnect ────────────────────────────────────────────────────────


@router.delete("/{brain_id}/accounts/{account_id}", status_code=204)
async def disconnect_account(
    brain_id: str,
    account_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Disconnect and delete a connected account."""
    account = await credential_manager.get_account(session, account_id, current_user.user_id)
    if not account or account.brain_id != brain_id:
        raise HTTPException(status_code=404, detail="Account not found")

    # Try to revoke OAuth token
    if account.auth_type == "oauth" and account.credentials_encrypted:
        try:
            creds = credential_manager.decrypt_credentials(account.credentials_encrypted)
            provider = _get_provider(account.provider)
            await provider.revoke_token(creds.get("access_token", ""))
        except Exception:
            pass

    await credential_manager.disconnect(session, account)
    await session.commit()
