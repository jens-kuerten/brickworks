import logging
import secrets

from authlib.integrations.base_client import OAuthError
from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from starlette.requests import Request

from brickworks.core.auth.oidc import OIDCUserInfo, get_or_create_user_from_userinfo, oidc_client
from brickworks.core.schemas.auth_schemas import CSRFTokenResponse
from brickworks.core.settings import settings

logger = logging.getLogger(__name__)
auth_router = r = APIRouter(prefix="/auth")


@r.get("/login")
async def _login(request: Request) -> RedirectResponse:
    """
    Will redirect the user to the OIDC provider for authentication.
    """
    redirect_uri = request.url_for("_redirect")
    # we need to help out mypy here, because authlib isn't typed
    response: RedirectResponse = await oidc_client.authorize_redirect(request, redirect_uri)
    return response


@r.get("/redirect")
async def _redirect(request: Request) -> Response:
    """
    This is the redirect URL that the OIDC provider will call after the user has logged in.
    If the login was successful we set the user in the session and redirect to the POST_LOGIN_REDIRECT_URI.
    """
    try:
        token = await oidc_client.authorize_access_token(request)
    except OAuthError as error:
        # TODO: redirect to error page?
        return HTMLResponse(f"<h1>{error.error}</h1>")
    userinfo = token.get("userinfo")
    if not userinfo:
        return HTMLResponse("<h1>Userinfo not found</h1>")
    try:
        userinfo_model = OIDCUserInfo.model_validate(userinfo)
    except ValidationError as error:
        logger.error("Userinfo validation error!", exc_info=error)
        return HTMLResponse(f"<h1>{error.errors()}</h1>")
    user = await get_or_create_user_from_userinfo(userinfo_model)
    request.session["user_uuid"] = user.uuid

    return RedirectResponse(url=settings.POST_LOGIN_REDIRECT_URI)


@r.get("/logout")
async def _logout(request: Request) -> RedirectResponse:
    """
    Will logout the user by clearing the session.
    If the OIDC provider supports it, we will also redirect to the logout URL of the OIDC provider.
    After that we redirect to the POST_LOGOUT_REDIRECT_URI.
    """
    request.session.pop("user", None)
    metadata = await oidc_client.load_server_metadata()
    if "end_session_endpoint" in metadata:
        logout_url = f"{metadata['end_session_endpoint']}?post_logout_redirect_uri={settings.POST_LOGOUT_REDIRECT_URI}"
        return RedirectResponse(url=logout_url)
    return RedirectResponse(url=settings.POST_LOGOUT_REDIRECT_URI)


@r.get("/csrf")
async def _csrf(request: Request) -> CSRFTokenResponse:
    """
    This endpoint returns a CSRF token for the user.
    """
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_hex(32)
        request.session["csrf_token"] = token
    return CSRFTokenResponse(csrf_token=token)
