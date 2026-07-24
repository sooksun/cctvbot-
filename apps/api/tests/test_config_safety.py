"""Boot-time secret validation: refuse default secrets in production."""

import pytest

from app.config import Settings

_DEFAULTS = {
    "api_secret_key": "dev-secret-change-me-32chars-min",
    "system_api_token": "dev-system-token",
    "admin_password": "admin123!",
}
_REAL = {
    "api_secret_key": "a-real-secret-key-at-least-32-characters",
    "system_api_token": "real-system-token-value",
    "admin_password": "Str0ng-Passw0rd!",
}


def test_dev_allows_default_secrets():
    s = Settings(environment="dev", **_DEFAULTS)
    s.check_production_safety()  # must not raise
    assert s.is_production() is False


def test_production_rejects_default_secrets():
    s = Settings(environment="production", **_DEFAULTS)
    with pytest.raises(RuntimeError) as exc:
        s.check_production_safety()
    # all three placeholders reported
    assert "api_secret_key" in str(exc.value)
    assert "system_api_token" in str(exc.value)
    assert "admin_password" in str(exc.value)


def test_production_rejects_partial_default_secrets():
    s = Settings(
        environment="prod",
        api_secret_key=_REAL["api_secret_key"],
        system_api_token=_DEFAULTS["system_api_token"],  # still default
        admin_password=_REAL["admin_password"],
    )
    with pytest.raises(RuntimeError) as exc:
        s.check_production_safety()
    assert "system_api_token" in str(exc.value)
    assert "api_secret_key" not in str(exc.value)


def test_production_ok_with_overridden_secrets():
    s = Settings(environment="production", **_REAL)
    s.check_production_safety()  # must not raise
    assert s.insecure_defaults() == []
