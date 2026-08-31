"""Railway deployment configuration tests.

The Railway startup failure class (`KeyError: 'MONGO_URL'`, HTTPS guard refusals) is a
configuration problem, so these tests import the real server module in a subprocess with
Railway-style environment and assert the derived public URL configuration. No mocks of
the configuration logic itself: the subprocess executes the actual module import path.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet


BACKEND_DIR = Path(__file__).resolve().parents[1]

BASE_ENV = {
    "MONGO_URL": "mongodb://localhost:27017",
    "DB_NAME": "clientverse_railway_unit",
    "JWT_SECRET": "railway-unit-jwt-secret-that-is-long-enough",
    "INTEGRATION_ENC_KEY": Fernet.generate_key().decode(),
    "WEBHOOK_CRON_SECRET": "railway-unit-cron-secret",
    "ADMIN_EMAIL": "railway-admin@example.com",
    "ADMIN_PASSWORD": "RailwayAdminPassw0rd!1",
}

PROBE = (
    "import json, server; print(json.dumps({"
    "'frontend_url': server.FRONTEND_URL, "
    "'cors': server.CORS_ORIGINS, "
    "'public_backend': server._PUBLIC_BACKEND, "
    "'google_redirect': server.GOOGLE_REDIRECT_URI, "
    "'is_production': server.IS_PRODUCTION}))"
)


def import_server(extra_env):
    env = {k: v for k, v in os.environ.items()}
    for key in ("FRONTEND_URL", "CORS_ORIGINS", "PUBLIC_BACKEND_URL", "GOOGLE_REDIRECT_URI",
                "RENDER_EXTERNAL_URL", "RAILWAY_PUBLIC_DOMAIN", "APP_ENV"):
        env.pop(key, None)
    env.update(BASE_ENV)
    env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"server import failed: {proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_railway_public_domain_derives_https_urls():
    result = import_server({"RAILWAY_PUBLIC_DOMAIN": "clientverse-production.up.railway.app",
                            "APP_ENV": "production"})
    assert result["frontend_url"] == "https://clientverse-production.up.railway.app"
    assert result["cors"] == ["https://clientverse-production.up.railway.app"]
    assert result["public_backend"] == "https://clientverse-production.up.railway.app"
    assert result["google_redirect"] == (
        "https://clientverse-production.up.railway.app/api/integrations/google/callback"
    )
    assert result["is_production"] is True


def test_explicit_frontend_url_wins_over_railway_domain():
    result = import_server({"RAILWAY_PUBLIC_DOMAIN": "clientverse-production.up.railway.app",
                            "FRONTEND_URL": "https://crm.example.com",
                            "APP_ENV": "production"})
    assert result["frontend_url"] == "https://crm.example.com"
    assert result["cors"] == ["https://crm.example.com"]


def test_render_external_url_wins_over_railway_domain():
    result = import_server({"RAILWAY_PUBLIC_DOMAIN": "clientverse-production.up.railway.app",
                            "RENDER_EXTERNAL_URL": "https://clientverse.onrender.com",
                            "APP_ENV": "production"})
    assert result["frontend_url"] == "https://clientverse.onrender.com"


def test_railway_production_requires_no_localhost_fallback():
    result = import_server({"RAILWAY_PUBLIC_DOMAIN": "clientverse-production.up.railway.app",
                            "APP_ENV": "production"})
    assert "localhost" not in result["frontend_url"]
    assert all(origin.startswith("https://") for origin in result["cors"])
