"""
GitHub OAuth 2.0 provider — repo, PR, issues access for Coder Brain.
"""

from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.services.oauth_providers.base import OAuthProvider, OAuthTokens, OAuthUserInfo


class GitHubOAuthProvider(OAuthProvider):
    provider_name = "github"
    display_name = "GitHub"
    auth_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    userinfo_url = "https://api.github.com/user"
    default_scopes = "user:email repo"

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": self.default_scopes,
            "state": state,
        }
        return f"{self.auth_url}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthTokens(
            access_token=data["access_token"],
            scopes=data.get("scope"),
            token_type=data.get("token_type", "bearer"),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        # GitHub tokens don't expire by default; refresh is a no-op
        raise NotImplementedError("GitHub tokens do not support refresh")

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
        return OAuthUserInfo(
            provider_user_id=str(data["id"]),
            email=data.get("email"),
            display_name=data.get("name") or data.get("login"),
            avatar_url=data.get("avatar_url"),
            raw=data,
        )

    async def revoke_token(self, token: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"https://api.github.com/applications/{settings.GITHUB_CLIENT_ID}/token",
                auth=(settings.GITHUB_CLIENT_ID, settings.GITHUB_CLIENT_SECRET),
                json={"access_token": token},
            )
            return resp.status_code == 204


github_oauth = GitHubOAuthProvider()
