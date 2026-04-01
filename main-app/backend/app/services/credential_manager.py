"""
Credential manager — encrypt/decrypt/store/refresh credentials for connected accounts.

Uses the existing Fernet encryption from app.core.encryption to store
OAuth tokens, API keys, cookies, and other secrets securely.
"""

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.encryption import encrypt_value, decrypt_value
from app.models.connected_account import ConnectedAccount

logger = structlog.get_logger()


class CredentialManager:
    """Manages encrypted credential storage for Brain connected accounts."""

    def encrypt_credentials(self, credentials: dict) -> str:
        return encrypt_value(json.dumps(credentials))

    def decrypt_credentials(self, encrypted: str) -> dict:
        try:
            return json.loads(decrypt_value(encrypted))
        except (json.JSONDecodeError, Exception):
            return {}

    async def list_accounts(
        self, session: AsyncSession, brain_id: str, user_id: str,
    ) -> list[ConnectedAccount]:
        result = await session.execute(
            select(ConnectedAccount)
            .where(ConnectedAccount.brain_id == brain_id, ConnectedAccount.user_id == user_id)
            .order_by(ConnectedAccount.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_account(
        self, session: AsyncSession, account_id: str, user_id: str,
    ) -> Optional[ConnectedAccount]:
        result = await session.execute(
            select(ConnectedAccount)
            .where(ConnectedAccount.account_id == account_id, ConnectedAccount.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def store_api_key(
        self,
        session: AsyncSession,
        brain_id: str,
        user_id: str,
        provider: str,
        api_key: str,
        api_secret: Optional[str] = None,
        display_name: Optional[str] = None,
        account_identifier: Optional[str] = None,
    ) -> ConnectedAccount:
        creds = {"api_key": api_key}
        if api_secret:
            creds["api_secret"] = api_secret

        account = ConnectedAccount(
            account_id=str(uuid4()),
            brain_id=brain_id,
            user_id=user_id,
            provider=provider,
            provider_display_name=display_name or provider.replace("_", " ").title(),
            account_identifier=account_identifier,
            auth_type="api_key",
            credentials_encrypted=self.encrypt_credentials(creds),
            status="active",
            is_active=True,
        )
        session.add(account)
        await session.flush()
        return account

    async def store_oauth_tokens(
        self,
        session: AsyncSession,
        brain_id: str,
        user_id: str,
        provider: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        scopes: Optional[str] = None,
        display_name: Optional[str] = None,
        account_identifier: Optional[str] = None,
    ) -> ConnectedAccount:
        creds = {"access_token": access_token}
        if refresh_token:
            creds["refresh_token"] = refresh_token
        if expires_at:
            creds["expires_at"] = expires_at.isoformat()

        account = ConnectedAccount(
            account_id=str(uuid4()),
            brain_id=brain_id,
            user_id=user_id,
            provider=provider,
            provider_display_name=display_name or provider.replace("_", " ").title(),
            account_identifier=account_identifier,
            auth_type="oauth",
            credentials_encrypted=self.encrypt_credentials(creds),
            oauth_scopes=scopes,
            token_expires_at=expires_at,
            status="active",
            is_active=True,
        )
        session.add(account)
        await session.flush()
        return account

    async def store_cookies(
        self,
        session: AsyncSession,
        brain_id: str,
        user_id: str,
        provider: str,
        cookies: list[dict],
        user_agent: Optional[str] = None,
        display_name: Optional[str] = None,
        account_identifier: Optional[str] = None,
    ) -> ConnectedAccount:
        creds = {"cookies": cookies}
        if user_agent:
            creds["user_agent"] = user_agent

        account = ConnectedAccount(
            account_id=str(uuid4()),
            brain_id=brain_id,
            user_id=user_id,
            provider=provider,
            provider_display_name=display_name or provider.replace("_", " ").title(),
            account_identifier=account_identifier,
            auth_type="cookie",
            credentials_encrypted=self.encrypt_credentials(creds),
            status="active",
            is_active=True,
        )
        session.add(account)
        await session.flush()
        return account

    async def get_decrypted_credentials(
        self, session: AsyncSession, account_id: str, user_id: str,
    ) -> Optional[dict]:
        account = await self.get_account(session, account_id, user_id)
        if not account or not account.credentials_encrypted:
            return None
        return self.decrypt_credentials(account.credentials_encrypted)

    async def update_credentials(
        self,
        session: AsyncSession,
        account: ConnectedAccount,
        credentials: dict,
        expires_at: Optional[datetime] = None,
    ) -> ConnectedAccount:
        account.credentials_encrypted = self.encrypt_credentials(credentials)
        if expires_at:
            account.token_expires_at = expires_at
        account.status = "active"
        account.updated_at = datetime.utcnow()
        await session.flush()
        return account

    async def verify_account(
        self, session: AsyncSession, account: ConnectedAccount,
    ) -> ConnectedAccount:
        account.last_verified_at = datetime.utcnow()
        account.status = "active"
        account.updated_at = datetime.utcnow()
        await session.flush()
        return account

    async def mark_expired(
        self, session: AsyncSession, account: ConnectedAccount, message: Optional[str] = None,
    ) -> ConnectedAccount:
        account.status = "expired"
        account.status_message = message or "Credentials expired"
        account.updated_at = datetime.utcnow()
        await session.flush()
        return account

    async def disconnect(
        self, session: AsyncSession, account: ConnectedAccount,
    ) -> None:
        await session.delete(account)
        await session.flush()

    async def touch_last_used(
        self, session: AsyncSession, account: ConnectedAccount,
    ) -> None:
        account.last_used_at = datetime.utcnow()
        await session.flush()


credential_manager = CredentialManager()
