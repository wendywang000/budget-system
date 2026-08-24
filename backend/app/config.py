from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "預算編列系統"
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./budget.db"
    secret_key: str = "dev-only-secret-key-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # 以逗號分隔的允許來源
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
