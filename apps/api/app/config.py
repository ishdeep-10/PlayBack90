from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "PlayBack90 API"
    api_prefix: str = "/api"
    environment: str = "development"
    frontend_url: str = "http://localhost:3000"

    r2_account_id: str | None = None
    r2_access_key: str | None = None
    r2_secret_key: str | None = None
    r2_bucket: str | None = None

    anthropic_api_key: str | None = None
    ai_model: str = "claude-sonnet-4-6"

    redis_url: str = "redis://localhost:6379/0"
    live_scrape_rate_limit_per_minute: int = 5

    football_data_api_key: str | None = None
    football_data_base_url: str = "https://api.football-data.org/v4"
    football_data_timeout_seconds: float = 10.0
    standings_cache_ttl_seconds: int = 600
    standings_stale_ttl_seconds: int = 86_400

    auth_required: bool = False
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None
    clerk_audience: str | None = None
    auth_allowed_emails: str | None = None
    auth_allowed_user_ids: str | None = None

    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ROOT_DIR / "Data" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def r2_endpoint_url(self) -> str | None:
        if not self.r2_account_id:
            return None
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def has_r2_credentials(self) -> bool:
        return all(
            [
                self.r2_account_id,
                self.r2_access_key,
                self.r2_secret_key,
                self.r2_bucket,
            ]
        )


settings = Settings()
