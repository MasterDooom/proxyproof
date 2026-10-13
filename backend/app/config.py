"""Fail-closed runtime configuration for ProxyProof.

Render sets RENDER=true. Locally, explicitly missing values may use clearly
documented development fallbacks; hosted deployments must provide strong secrets
and a durable database URL.
"""
import os


def is_production_environment() -> bool:
    """Return whether the process is running in a production-like environment."""
    return (
        os.getenv("APP_ENV", "").strip().lower() == "production"
        or os.getenv("RENDER", "").strip().lower() == "true"
    )


def required_secret(
    name: str,
    *,
    minimum_length: int,
    development_default: str | None = None,
) -> str:
    """Load a secret and validate it strictly in production."""
    value = os.getenv(name, "").strip()
    if not value:
        if is_production_environment():
            raise RuntimeError(f"Required production setting {name} is missing.")
        if development_default is None:
            raise RuntimeError(f"Required setting {name} is missing.")
        return development_default
    if is_production_environment() and len(value.encode("utf-8")) < minimum_length:
        raise RuntimeError(
            f"Production setting {name} must be at least {minimum_length} bytes."
        )
    return value
