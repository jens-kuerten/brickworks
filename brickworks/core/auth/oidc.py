"""
OpenID Connect authentication using Authlib and FastAPI security.
To get a token use fastapi_oauth2 as a dependency in your route.
e.g.:
    @app.get("/login")
    async def login(token: str = fastapi_oauth2):
        user = await authlib_oauth.auth0.parse_id_token(token)
        return {"user": user}
"""

from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from pydantic import AnyUrl, BaseModel, EmailStr

from brickworks.core.models.user_model import UserModel
from brickworks.core.settings import settings

authlib_oauth = OAuth()


def _get_oidc_client() -> StarletteOAuth2App:
    client = authlib_oauth.register(
        name=settings.OIDC_PROVIDER_NAME,
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        server_metadata_url=settings.OIDC_DISCOVERY_URL,
        client_kwargs={"scope": "openid profile email"},
    )
    if not client:
        raise ValueError("OIDC client was not registered.")
    return client


oidc_client: StarletteOAuth2App = _get_oidc_client()


class OIDCAddress(BaseModel):
    """
    OIDC Address Claim.
    https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims
    """

    formatted: str | None = None
    street_address: str | None = None
    locality: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None


class OIDCUserInfo(BaseModel):
    """
    OIDC Standard Claims.
    https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims

    Note: The standard claim does not require the email claim to be present,
    however, we require it in our implementation - otherwise the user cannot be created.
    """

    sub: str

    email: EmailStr

    email_verified: bool | None = None
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    middle_name: str | None = None
    nickname: str | None = None
    preferred_username: str | None = None
    profile: AnyUrl | None = None
    picture: AnyUrl | None = None
    website: AnyUrl | None = None

    gender: str | None = None
    birthdate: str | None = None
    zoneinfo: str | None = None
    locale: str | None = None
    phone_number: str | None = None
    phone_number_verified: bool | None = None
    address: OIDCAddress | None = None
    updated_at: int | None = None


async def create_user_from_userinfo(userinfo: OIDCUserInfo) -> UserModel:
    """
    Create a user from the userinfo dictionary returned by the OIDC provider.
    This is a placeholder implementation. In a real application, you would want to create a user in your database.
    """

    user = await UserModel(
        sub=userinfo.sub,
        email=str(userinfo.email),
        given_name=userinfo.given_name or "",
        family_name=userinfo.family_name or "",
        name=userinfo.name or f"{userinfo.given_name} {userinfo.family_name}",
        email_verified=userinfo.email_verified or False,
        phone_number=userinfo.phone_number or "",
        phone_number_verified=userinfo.phone_number_verified or False,
        locale=userinfo.locale or "en",
    ).persist()
    return user


async def get_or_create_user_from_userinfo(userinfo: OIDCUserInfo) -> UserModel:
    """
    Get or create a user from the userinfo dictionary returned by the OIDC provider.
    This is a placeholder implementation. In a real application, you would want to create a user in your database.
    """
    user = await UserModel.get_one_or_none(sub=userinfo.sub, _apply_policies=False)
    if not user:
        user = await create_user_from_userinfo(userinfo)
    return user
