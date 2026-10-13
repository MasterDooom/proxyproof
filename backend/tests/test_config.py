import pytest

from app.config import is_production_environment, required_secret
from app.security import _attendance_secret, get_organiser_invite_code


def clear_runtime_environment(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("RENDER", raising=False)


def test_local_development_has_explicit_documented_fallbacks(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.delenv("PROXYPROOF_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("PROXYPROOF_ORGANISER_INVITE_CODE", raising=False)

    assert not is_production_environment()
    assert _attendance_secret() == b"local-development-secret-change-before-deployment"
    assert get_organiser_invite_code() == "local-demo-organiser-code"


def test_production_requires_token_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("PROXYPROOF_TOKEN_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="PROXYPROOF_TOKEN_SECRET is missing"):
        _attendance_secret()


def test_production_rejects_weak_token_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("PROXYPROOF_TOKEN_SECRET", "too-short")

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        _attendance_secret()


def test_production_accepts_a_strong_token_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)
    secret = "0123456789abcdef0123456789abcdef"
    monkeypatch.setenv("PROXYPROOF_TOKEN_SECRET", secret)

    assert _attendance_secret() == secret.encode("utf-8")


def test_render_environment_is_production_and_requires_invite_code(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("PROXYPROOF_ORGANISER_INVITE_CODE", raising=False)

    assert is_production_environment()
    with pytest.raises(RuntimeError, match="PROXYPROOF_ORGANISER_INVITE_CODE is missing"):
        get_organiser_invite_code()


def test_production_invite_code_must_have_minimum_length(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("PROXYPROOF_ORGANISER_INVITE_CODE", "weak")

    with pytest.raises(RuntimeError, match="at least 16 bytes"):
        get_organiser_invite_code()


def test_required_secret_does_not_trim_secret_interior(monkeypatch):
    clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("SAMPLE_SECRET", "  valid local secret  ")

    assert required_secret(
        "SAMPLE_SECRET", minimum_length=32, development_default=None
    ) == "valid local secret"
