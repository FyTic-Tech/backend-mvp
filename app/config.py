from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 8000
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"

    supabase_url: str = ""
    supabase_service_key: str = ""

    database_url: str = "postgresql+psycopg://fytic:fytic@localhost:5432/fytic_saas"
    upload_root: str = "var/uploads"
    demo_firm_id: str = "00000000-0000-0000-0000-000000000001"

    @property
    def is_dev(self) -> bool:
        return self.environment != "production"


settings = Settings()
