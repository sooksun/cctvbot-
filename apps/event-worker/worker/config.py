from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_base_url: str = "http://api:8000"
    system_api_token: str = "dev-system-token"
    evidence_root: str = "./data/events"
    debounce_seconds: int = 60
    timezone: str = "Asia/Bangkok"
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883


settings = Settings()
