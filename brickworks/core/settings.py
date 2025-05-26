from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SESSION_SECRET: str = ""  # used for signing session data
    JWT_SECRET: str = ""  # used for signing jwts

    MULTI_TENANCY_ENABLED: bool = False
    MASTER_DOMAIN: str = "example.com"
    MASTER_DB_SCHEMA: str = "public"

    # Database settings
    DB_HOST: str = "127.0.0.1:5432"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "postgres"

    USE_REDIS: bool = True
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # OIDC
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_DISCOVERY_URL: str = "https://accounts.google.com/.well-known/openid-configuration"
    OIDC_PROVIDER_NAME: str = "google"
    POST_LOGOUT_REDIRECT_URI: str = "/"
    POST_LOGIN_REDIRECT_URI: str = "/"


settings = Settings()
