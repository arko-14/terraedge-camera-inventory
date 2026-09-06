"""Application configuration, loaded from environment variables.

Secrets never live in source control: everything sensitive is read from the
environment (a local `.env` file in development, real env vars in production).
`.env.example` documents every key without carrying a single real value.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder used in .env.example. Refusing to boot on this value in
# production is what stops a throwaway dev secret reaching a real deployment.
INSECURE_DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    environment: Literal["development", "production", "test"] = "development"

    database_url: str = "postgresql+psycopg://terraedge:terraedge@localhost:5432/terraedge"

    jwt_secret: str = INSECURE_DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720  # 12 hours

    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_secure: bool = False
    session_cookie_name: str = "terraedge_session"
    csrf_cookie_name: str = "terraedge_csrf"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Path to the built frontend. Set it and this app serves the web app too,
    # on one origin; leave it empty for a split deployment.
    static_dir: str = ""

    seed_admin_password: str = ""
    seed_chahala_password: str = ""
    seed_nawana_password: str = ""

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        # Managed providers hand out driverless `postgres://` URLs; SQLAlchemy 2
        # needs the driver named, so rewrite rather than make every deploy do it.
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def static_path(self) -> Path | None:
        """The built frontend directory, if this deployment serves one."""
        if not self.static_dir:
            return None
        path = Path(self.static_dir)
        return path if (path / "index.html").is_file() else None

    @property
    def serves_frontend(self) -> bool:
        return self.static_path is not None

    def check_production_settings(self) -> None:
        """Fail fast on unsafe production configuration.

        Called at application start-up (not at import time) so that tests and
        tooling can construct Settings freely.
        """
        if not self.is_production:
            return

        if self.jwt_secret in (INSECURE_DEV_SECRET, "", None) or len(self.jwt_secret) < 32:
            raise RuntimeError(
                "JWT_SECRET must be set to a strong random value (>=32 chars) in production. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if not self.cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true in production (cookies are sent over HTTPS only).")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise RuntimeError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true.")
        if "*" in self.cors_origins:
            raise RuntimeError("Wildcard CORS origins are not allowed when credentials are enabled.")
        # A single-origin deployment serves the frontend itself and needs no
        # cross-origin allow-list; a split deployment must name its frontend.
        if not self.serves_frontend and not self.cors_origin_list:
            raise RuntimeError(
                "CORS_ORIGINS must list the exact frontend origin(s), or set STATIC_DIR "
                "to serve the frontend from this application."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
