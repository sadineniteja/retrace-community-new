"""
Base OAuth provider — abstract interface for all OAuth integrations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    token_type: str = "Bearer"
    scopes: Optional[str] = None
    id_token: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class OAuthUserInfo:
    provider_user_id: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    raw: Optional[dict] = None


class OAuthProvider(ABC):
    """Abstract base for OAuth providers."""

    provider_name: str = ""
    display_name: str = ""
    auth_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    default_scopes: str = ""

    @abstractmethod
    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Build the URL to redirect the user to for authorization."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        """Exchange an authorization code for tokens."""
        ...

    @abstractmethod
    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        """Refresh an expired access token."""
        ...

    @abstractmethod
    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch the authenticated user's profile."""
        ...

    async def revoke_token(self, token: str) -> bool:
        """Revoke a token. Returns True if successful."""
        return False
