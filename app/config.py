from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 8000
    frontend_url: str = "http://localhost:5173"
    app_frontend_url: str = ""
    environment: str = "development"

    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""
    resend_api_key: str = ""
    supabase_hook_secret: str = ""
    supabase_webhook_secret: str = ""
    internal_api_key: str = ""
    gemini_api_key: str = ""

    @property
    def is_dev(self) -> bool:
        return self.environment != "production"


settings = Settings()
