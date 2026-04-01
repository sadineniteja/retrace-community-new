"""
Twitter/X OAuth 2.0 provider — posting, reading timeline for Social Media Brain.
"""

from urllib.parse import urlencode
import base64

import httpx

from app.core.config import settings
from app.services.oauth_providers.base import OAuthProvider, OAuthTokens, OAuthUserInfo


class TwitterOAuthProvider(OAuthProvider):
    provider_name = "twitter"
    display_name = "Twitter / X"
    auth_url = "https://twitter.com/i/oauth2/authorize"
    token_url = "https://api.twitter.com/2/oauth2/token"
    userinfo_url = "https://api.twitter.com/2/users/me"
    default_scopes = "tweet.read tweet.write users.read offline.access"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.TWITTER_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.default_scopes,
            "state": state,
            "code_challenge": "challenge",
            "code_challenge_method": "plain",
        }
        return f"{self.auth_url}?{urlencode(params)}"

    def _basic_auth(self) -> str:
        creds = f"{settings.TWITTER_CLIENT_ID}:{settings.TWITTER_CLIENT_SECRET}"
        return base64.b64encode(creds.encode()).decode()

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code_verifier": "challenge",
                },
                headers={
                    "Authorization": f"Basic {self._basic_auth()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            scopes=data.get("scope"),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers={
                    "Authorization": f"Basic {self._basic_auth()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
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
                params={"user.fields": "id,name,username,profile_image_url"},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
        return OAuthUserInfo(
            provider_user_id=data.get("id", ""),
            display_name=data.get("name"),
            avatar_url=data.get("profile_image_url"),
            raw=data,
        )

    async def revoke_token(self, token: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.twitter.com/2/oauth2/revoke",
                data={"token": token},
                headers={
                    "Authorization": f"Basic {self._basic_auth()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            return resp.status_code == 200


twitter_oauth = TwitterOAuthProvider()
