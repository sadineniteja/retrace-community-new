"""
Connected account model — OAuth/cookie/API-key credentials for external services.

Stores encrypted credentials for services a Brain needs to interact with
(LinkedIn, Gmail, GitHub, brokerage accounts, etc.).
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class ConnectedAccount(Base):
    """An external service account connected to a Brain."""

    __tablename__ = "connected_accounts"

    account_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    brain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("brains.brain_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id"), nullable=False, index=True,
    )

    # Service identity
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # linkedin | google | github | twitter | discord | slack | email_imap |
    # binance | coinbase | robinhood | indeed | glassdoor | custom_api
    provider_display_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    account_identifier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Auth method
    auth_type: Mapped[str] = mapped_column(String(20), nullable=False, default="oauth")
    # oauth | api_key | cookie | basic_auth

    # Encrypted credential storage (Fernet via encryption.py)
    # JSON blob: {"access_token": "...", "refresh_token": "...", "expires_at": "..."}
    # or cookies: {"cookies": [...], "user_agent": "..."}
    # or api_key: {"api_key": "...", "api_secret": "..."}
    credentials_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # OAuth-specific
    oauth_scopes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active | expired | revoked | error
    status_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    brain = relationship("Brain", back_populates="connected_accounts")

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "brain_id": self.brain_id,
            "user_id": self.user_id,
            "provider": self.provider,
            "provider_display_name": self.provider_display_name,
            "account_identifier": self.account_identifier,
            "auth_type": self.auth_type,
            "oauth_scopes": self.oauth_scopes,
            "token_expires_at": self.token_expires_at.isoformat() if self.token_expires_at else None,
            "status": self.status,
            "status_message": self.status_message,
            "is_active": self.is_active,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_verified_at": self.last_verified_at.isoformat() if self.last_verified_at else None,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
