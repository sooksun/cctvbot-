from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder secrets shipped for dev/test. MUST be overridden before deploying
# to production; check_production_safety() refuses to boot if any remain.
_DEFAULT_SECRETS: dict[str, str] = {
    "api_secret_key": "dev-secret-change-me-32chars-min",
    "system_api_token": "dev-system-token",
    "admin_password": "admin123!",
}

_PROD_ENVIRONMENTS = {"prod", "production", "staging"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "dev"
    database_url: str = "mysql+pymysql://cctvbot:cctvbot@127.0.0.1:3306/cctvbot"
    api_secret_key: str = "dev-secret-change-me-32chars-min"
    system_api_token: str = "dev-system-token"
    evidence_root: str = "./data/events"
    frigate_base_url: str = "http://frigate:5000"
    cors_origins: str = "http://localhost:3000"
    admin_username: str = "admin"
    admin_password: str = "admin123!"
    line_channel_access_token: str = ""
    line_user_id: str = ""

    def is_production(self) -> bool:
        return self.environment.strip().lower() in _PROD_ENVIRONMENTS

    def insecure_defaults(self) -> list[str]:
        """Names of secret settings still left at their placeholder default."""
        return sorted(
            name
            for name, default in _DEFAULT_SECRETS.items()
            if getattr(self, name) == default
        )

    def check_production_safety(self) -> None:
        """Fail fast when booting in production with placeholder secrets."""
        if not self.is_production():
            return
        issues = self.insecure_defaults()
        if issues:
            raise RuntimeError(
                "Refusing to start in production with default secrets: "
                + ", ".join(issues)
                + ". Set these via environment / .env before deploying."
            )


settings = Settings()
