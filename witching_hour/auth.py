"""Auth0 login for the family room (the home install, not the public demo).

Why: Xochi's morning note and the live questions to the agent are about someone's
home at night. On the home server, only signed-in family members on an allowlist
may ask the agent or read the live notes. The public demo replays a research
dataset and has no family data, so it never turns this on.

Enabled when AUTH0_DOMAIN, AUTH0_CLIENT_ID, AUTH0_CLIENT_SECRET, SESSION_SECRET and
FAMILY_EMAILS are set and live mode is on (WH_LIVE=1). Callback: /auth/callback.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse


def settings() -> dict:
    return {k: os.environ.get(k, "").strip() for k in
            ("AUTH0_DOMAIN", "AUTH0_CLIENT_ID", "AUTH0_CLIENT_SECRET", "SESSION_SECRET", "FAMILY_EMAILS")}


def enabled() -> bool:
    return os.environ.get("WH_LIVE", "1") == "1" and all(settings().values())


def family_emails() -> set[str]:
    return {e.strip().lower() for e in settings()["FAMILY_EMAILS"].split(",") if e.strip()}


def is_family(info: dict) -> bool:
    email = (info.get("email") or "").strip().lower()
    return bool(email) and info.get("email_verified") is True and email in family_emails()


def current_member(request: Request) -> dict | None:
    if not enabled():
        return None
    return request.session.get("member") if "session" in request.scope else None


def require_family(request: Request) -> None:
    """FastAPI dependency: live agent questions need a signed-in family member when Auth0 is on."""
    if enabled() and not current_member(request):
        raise HTTPException(401, "Family only: sign in with Auth0 first (/auth/login).")


def install(app) -> None:
    """Session middleware and the login routes, only when Auth0 is configured."""

    @app.get("/api/auth/me")
    def me(request: Request):
        m = current_member(request)
        return {"enabled": enabled(), "member": {"name": m.get("name"), "email": m.get("email")} if m else None}

    if not enabled():
        return
    from authlib.integrations.starlette_client import OAuth
    from starlette.middleware.sessions import SessionMiddleware

    s = settings()
    app.add_middleware(SessionMiddleware, secret_key=s["SESSION_SECRET"], same_site="lax", https_only=False)
    oauth = OAuth()
    oauth.register("auth0", client_id=s["AUTH0_CLIENT_ID"], client_secret=s["AUTH0_CLIENT_SECRET"],
                   server_metadata_url=f"https://{s['AUTH0_DOMAIN']}/.well-known/openid-configuration",
                   client_kwargs={"scope": "openid profile email"})

    @app.get("/auth/login", include_in_schema=False)
    async def login(request: Request):
        return await oauth.auth0.authorize_redirect(request, str(request.url_for("auth_callback")))

    @app.get("/auth/callback", name="auth_callback", include_in_schema=False)
    async def callback(request: Request):
        try:
            token = await oauth.auth0.authorize_access_token(request)
        except Exception:
            request.session.clear()
            return RedirectResponse("/?auth=failed#ask")
        info = token.get("userinfo") or {}
        if not is_family(info):
            request.session.clear()
            return RedirectResponse("/?auth=not-family#ask")
        request.session["member"] = {"name": info.get("name") or info.get("email"), "email": info.get("email")}
        return RedirectResponse("/#ask")

    @app.get("/auth/logout", include_in_schema=False)
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse(f"https://{s['AUTH0_DOMAIN']}/v2/logout?client_id={s['AUTH0_CLIENT_ID']}&returnTo="
                                + str(request.base_url).rstrip("/"))
