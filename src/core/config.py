from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    stripe_api_key: str
    database_url: str = "sqlite:///./payments.db"


settings = Settings()
