from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 8000
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"

    @property
    def is_dev(self) -> bool:
        return self.environment != "production"


settings = Settings()
