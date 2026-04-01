"""
LinkedIn OAuth 2.0 provider — profile, messaging, job search access for Brains.
"""

from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.services.oauth_providers.base import OAuthProvider, OAuthTokens, OAuthUserInfo


class LinkedInOAuthProvider(OAuthProvider):
    provider_name = "linkedin"
    display_name = "LinkedIn"
    auth_url = "https://www.linkedin.com/oauth/v2/authorization"
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    userinfo_url = "https://api.linkedin.com/v2/userinfo"
    default_scopes = "openid profile email w_member_social"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.LINKEDIN_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.default_scopes,
            "state": state,
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }, headers={"Content-Type": "application/x-www-form-urlencoded"})
            resp.raise_for_status()
            data = resp.json()
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scopes=data.get("scope"),
            id_token=data.get("id_token"),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_url, data={
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
            resp.raise_for_status()
            data = resp.json()
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", refresh_token),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthUserInfo(
            provider_user_id=data.get("sub", ""),
            email=data.get("email"),
            display_name=data.get("name"),
            avatar_url=data.get("picture"),
            raw=data,
        )


linkedin_oauth = LinkedInOAuthProvider()
