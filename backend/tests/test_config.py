import pytest
from app.config import Settings
from pydantic import ValidationError


@pytest.mark.parametrize("field", ["DATABASE_URL", "JWT_SECRET_KEY", "OPENAI_API_KEY"])
def test_required_configuration_cannot_fall_back_to_defaults(monkeypatch, field):
    monkeypatch.delenv(field, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "secret",
    [
        "too-short",
        "replace-with-a-secure-random-secret-key",
        "document-copilot-dev-secret-key-change-in-production-1234567890",
    ],
)
def test_rejects_insecure_jwt_secrets(secret):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret_key=secret)
