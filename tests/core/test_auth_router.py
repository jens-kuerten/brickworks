from authlib.integrations.base_client import OAuthError
from fastapi.responses import RedirectResponse
from httpx import AsyncClient
from pytest_mock import MockerFixture


async def test_login_redirects(client: AsyncClient, mocker: MockerFixture) -> None:
    mock_authorize_redirect = mocker.patch(
        "brickworks.core.routers.auth_router.oidc_client.authorize_redirect",
        return_value=RedirectResponse(url="https://example.com"),
    )
    response = await client.get("/api/core/auth/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "location" in response.headers
    mock_authorize_redirect.assert_called_once()


async def test_redirect_success(client: AsyncClient, mocker: MockerFixture) -> None:
    mock_token = {"userinfo": {"sub": "123", "name": "Test User", "email": "test@example.com"}}
    mocker.patch(
        "brickworks.core.routers.auth_router.oidc_client.authorize_access_token",
        return_value=mock_token,
    )
    response = await client.get("/api/core/auth/redirect")
    assert response.status_code in (302, 307)
    assert "location" in response.headers


async def test_redirect_oauth_error(client: AsyncClient, mocker: MockerFixture) -> None:
    mocker.patch(
        "brickworks.core.routers.auth_router.oidc_client.authorize_access_token",
        side_effect=OAuthError(error="oauth_error"),
    )
    response = await client.get("/api/core/auth/redirect", follow_redirects=False)
    assert response.status_code == 200
    assert "oauth_error" in response.text


async def test_logout_with_end_session(client: AsyncClient, mocker: MockerFixture) -> None:
    mocker.patch(
        "brickworks.core.routers.auth_router.oidc_client.load_server_metadata",
        return_value={"end_session_endpoint": "https://logout.example.com"},
    )
    response = await client.get("/api/core/auth/logout")
    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("https://logout.example.com")


async def test_logout_without_end_session(client: AsyncClient, mocker: MockerFixture) -> None:
    mocker.patch(
        "brickworks.core.routers.auth_router.oidc_client.load_server_metadata",
        return_value={},
    )
    response = await client.get("/api/core/auth/logout")
    assert response.status_code in (302, 307)
    assert "location" in response.headers


async def test_csrf_token_new(client: AsyncClient) -> None:
    response = await client.get("/api/core/auth/csrf")
    assert response.status_code == 200
    assert "csrf_token" in response.json()
    assert len(response.json()["csrf_token"]) == 64


async def test_csrf_token_existing(client: AsyncClient) -> None:
    # Use the same client context to preserve session
    response1 = await client.get("/api/core/auth/csrf")
    token1 = response1.json()["csrf_token"]
    response2 = await client.get("/api/core/auth/csrf")
    token2 = response2.json()["csrf_token"]
    assert token1 == token2
