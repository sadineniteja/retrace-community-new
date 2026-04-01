"""
Map Supabase JWT claims to a local User row (RBAC / tenant only). Identity is always from Supabase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User


async def resolve_supabase_user(
    session: AsyncSession,
    payload: dict,
    *,
    touch_login: bool = False,
) -> Optional[User]:
    """
    Find or create the local user for this Supabase identity.

    touch_login: set last_login_at (use True only on explicit remote-login, not every API call).
    """
    email = payload.get("email")
    if not email or not isinstance(email, str):
        return None

    user_meta = payload.get("user_metadata") or {}
    full_name = user_meta.get("full_name", "")

    result = await session.execute(select(User).where(func.lower(User.email) == email.lower()))
    user = result.scalar_one_or_none()

    if not user:
        tenant_result = await session.execute(select(Tenant).limit(1))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                tenant_id=str(uuid4()),
                name="Default",
                status="active",
                auth_method="email",
            )
            session.add(tenant)
            await session.flush()

        user = User(
            user_id=str(uuid4()),
            tenant_id=tenant.tenant_id,
            email=email,
            display_name=full_name or email.split("@")[0],
            auth_provider="supabase",
            role="admin",
            hashed_password=None,
            is_active=True,
        )
        session.add(user)
        await session.flush()
    else:
        if full_name and not user.display_name:
            user.display_name = full_name
        if touch_login:
            user.last_login_at = datetime.utcnow()
        if user.role != "zero_admin":
            user.role = "admin"
        if user.auth_provider != "supabase":
            user.auth_provider = "supabase"

    return user
