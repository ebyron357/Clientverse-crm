"""Production cannot opt out of the JWT signing-secret startup guard."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _boot(environment, secret, override):
    env = dict(os.environ)
    for name in ("RAILWAY_PUBLIC_DOMAIN", "RENDER_EXTERNAL_URL", "GOOGLE_REDIRECT_URI"):
        env.pop(name, None)
    env.update({
        "APP_ENV": environment,
        "JWT_SECRET": secret,
        "ALLOW_INSECURE_JWT": override,
        "MONGO_URL": "mongodb://127.0.0.1:27017",
        "DB_NAME": "jwt_configuration_test",
        "FRONTEND_URL": "https://crm.example.com",
        "PUBLIC_BACKEND_URL": "https://crm.example.com",
        "CORS_ORIGINS": "https://crm.example.com",
        "WEBHOOK_CRON_SECRET": "disposable-cron-secret",
        "INTEGRATION_ENC_KEY": Fernet.generate_key().decode(),
    })
    return subprocess.run(
        [sys.executable, "-c", "import server; print('JWT startup guard passed')"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("environment", ["production", "prod", " PRODUCTION ", "staging"])
@pytest.mark.parametrize("secret", ["short", "replace-with-a-long-random-hex-string"])
def test_deployed_environments_reject_insecure_jwt_override(environment, secret):
    result = _boot(environment, secret, "1")
    assert result.returncode != 0, "The development override must not bypass a deployed startup guard"
    assert "JWT_SECRET must be a strong secret" in result.stderr
    assert "JWT startup guard passed" not in result.stdout


@pytest.mark.parametrize("environment", ["development", "dev", "test", "testing", "local"])
def test_disposable_local_environments_retain_explicit_override(environment):
    result = _boot(environment, "short", "1")
    assert result.returncode == 0, result.stderr[-2000:]


def test_local_environment_still_requires_opt_in_for_weak_secret():
    result = _boot("development", "short", "")
    assert result.returncode != 0
    assert "JWT_SECRET must be a strong secret" in result.stderr


def test_production_accepts_strong_secret_with_stale_override_flag():
    # A harmless leftover flag should not take a correctly configured deployment down.
    result = _boot("production", "disposable-test-only-jwt-secret-at-least-32-characters", "1")
    assert result.returncode == 0, result.stderr[-2000:]
