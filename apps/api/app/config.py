from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "mysql+pymysql://cctvbot:cctvbot@127.0.0.1:3306/cctvbot"
    api_secret_key: str = "dev-secret-change-me-32chars-min"
    system_api_token: str = "dev-system-token"
    evidence_root: str = "./data/events"
    cors_origins: str = "http://localhost:3000"
    admin_username: str = "admin"
    admin_password: str = "admin123!"
    line_channel_access_token: str = ""
    line_user_id: str = ""


settings = Settings()
