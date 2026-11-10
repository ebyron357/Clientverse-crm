"""Public address checks: links, the Google callback and the scheduler's target.

Pure unit tests of `public_url`, the command the scheduler workflow runs, and the real
`server` module imported in a subprocess with production-style configuration (the same
technique as `test_railway_config.py`). No database and no network are needed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

import public_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def kinds(findings):
    return [f.kind for f in findings]


# ---------------------------------------------------------------- the checks themselves

@pytest.mark.parametrize("url", [
    "https://crm.clientverse.io",
    "https://crm.clientverse.io/",
    "  https://crm.clientverse.io  ",
    "https://clientverse-crm-production-production.up.railway.app",
])
def test_production_addresses_pass(url):
    assert public_url.check(url, production=True) == []
    assert public_url.check_scheduler_target(url) == []


@pytest.mark.parametrize("url", [
    "https://localhost", "https://localhost:8001", "http://127.0.0.1:8001",
    "https://10.0.0.5", "https://192.168.1.20", "https://[::1]", "https://api.internal",
    "https://box.local", "https://169.254.169.254",
])
def test_local_and_private_addresses_are_local(url):
    assert public_url.LOCAL in kinds(public_url.check(url, production=True))
    assert public_url.check_scheduler_target(url)


@pytest.mark.parametrize("url", [
    "https://clientverse-crm.vercel.app",
    "https://clientverse-crm-git-main-tradeiq.vercel.app",
    "https://clientverse.netlify.app",
    "https://clientverse.pages.dev",
    "https://clientverse.onrender.com",
    "https://abc.ngrok-free.app",
    "https://crm.preview.emergentagent.com",
])
def test_preview_and_copy_hosts_are_preview(url):
    findings = public_url.check(url, production=True)
    assert kinds(findings) == [public_url.PREVIEW]
    assert public_url.CANONICAL_PRODUCTION_URL in findings[0].message
    assert public_url.check_scheduler_target(url)


def test_preview_is_not_fatal_but_local_is():
    assert public_url.fatal(public_url.check("https://x.vercel.app", production=True)) == []
    assert public_url.fatal(public_url.check("https://localhost", production=True))


@pytest.mark.parametrize("url,fragment", [
    ("", "not set"),
    (None, "not set"),
    ("crm.clientverse.io", "absolute"),
    ("ftp://crm.clientverse.io", "absolute"),
    ("https://user:pw@crm.clientverse.io", "username"),
    ("https://crm.clientverse.io/?x=1", "'?'"),
    ("https://crm.clientverse.io/#top", "'?'"),
    ("https://crm.clientverse.io/api", "no path"),
    ("https://crm.clientverse.io:99999", "valid URL"),
])
def test_malformed_addresses_are_invalid(url, fragment):
    findings = public_url.check(url, production=True)
    assert public_url.INVALID in kinds(findings)
    assert any(fragment in f.message for f in findings)


def test_plain_http_is_insecure_only_in_production():
    assert kinds(public_url.check("http://crm.clientverse.io", production=True)) == [
        public_url.INSECURE]
    assert public_url.check("http://crm.clientverse.io", production=False) == []


def test_local_development_addresses_are_fine_outside_production():
    assert public_url.check("http://localhost:3000", production=False) == []


def test_scheduler_requires_a_known_production_host():
    findings = public_url.check_scheduler_target("https://crm.example.com")
    assert kinds(findings) == [public_url.INVALID]
    assert "crm.example.com" in findings[0].message
    assert public_url.CANONICAL_PRODUCTION_URL in findings[0].message


def test_scheduler_rejects_lookalike_hosts():
    for url in ("https://crm.clientverse.io.evil.example", "https://evilcrm.clientverse.io"):
        assert public_url.check_scheduler_target(url)


def test_google_redirect_must_be_the_callback_path():
    good = "https://crm.clientverse.io/api/integrations/google/callback"
    assert public_url.check_google_redirect(good, production=True) == []
    assert public_url.check_google_redirect(good + "/", production=True) == []
    wrong_path = public_url.check_google_redirect("https://crm.clientverse.io/callback",
                                                  production=True)
    assert kinds(wrong_path) == [public_url.INVALID]
    preview = public_url.check_google_redirect(
        "https://clientverse-crm.vercel.app/api/integrations/google/callback", production=True)
    assert kinds(preview) == [public_url.PREVIEW]


def test_report_carries_the_host_never_the_full_value():
    url = "https://crm.clientverse.io"
    row = public_url.report("FRONTEND_URL", url, public_url.check(url, production=True))
    assert row == {"name": "FRONTEND_URL", "host": "crm.clientverse.io", "ok": True,
                   "problems": []}


# ---------------------------------------------------------------- the workflow's command

def run_cli(*args):
    return subprocess.run([sys.executable, str(BACKEND_DIR / "public_url.py"), *args],
                          capture_output=True, text=True, timeout=60)


def test_cli_accepts_production_and_prints_it_normalized():
    proc = run_cli("scheduler", "https://crm.clientverse.io/")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "https://crm.clientverse.io"


@pytest.mark.parametrize("url", ["https://clientverse-crm.vercel.app", "http://localhost:8001",
                                 "", "https://crm.example.com"])
def test_cli_refuses_with_a_github_error_annotation(url):
    proc = run_cli("scheduler", url)
    assert proc.returncode == 1
    assert "::error title=Scheduler address refused" in proc.stdout
    assert "No production request was made." in proc.stdout


def test_cli_usage_error():
    assert run_cli().returncode == 2


def test_scheduler_workflow_checks_the_address_before_calling():
    text = (REPO_ROOT / ".github/workflows/scheduled-jobs.yml").read_text()
    check_at = text.index("public_url.py scheduler")
    assert check_at < text.index("Call the endpoints")
    assert "sparse-checkout: backend/public_url.py" in text


# ---------------------------------------------------------------- the server at boot

BASE_ENV = {
    "MONGO_URL": "mongodb://localhost:27017",
    "DB_NAME": "clientverse_public_url_unit",
    "JWT_SECRET": "public-url-unit-jwt-secret-that-is-long-enough",
    "INTEGRATION_ENC_KEY": Fernet.generate_key().decode(),
    "WEBHOOK_CRON_SECRET": "public-url-unit-cron-secret",
    "ADMIN_EMAIL": "public-url-admin@example.com",
    "ADMIN_PASSWORD": "PublicUrlAdminPassw0rd!1",
    "APP_ENV": "production",
}

PROBE = (
    "import json, server; print(json.dumps({"
    "'frontend_url': server.FRONTEND_URL, "
    "'redirect_findings': [f.kind for f in server.GOOGLE_REDIRECT_FINDINGS], "
    "'report': server.public_url_report()}))"
)


def import_server(extra_env):
    env = dict(os.environ)
    for key in ("FRONTEND_URL", "CORS_ORIGINS", "PUBLIC_BACKEND_URL", "GOOGLE_REDIRECT_URI",
                "RENDER_EXTERNAL_URL", "RAILWAY_PUBLIC_DOMAIN", "APP_ENV"):
        env.pop(key, None)
    env.update(BASE_ENV)
    env.update(extra_env)
    return subprocess.run([sys.executable, "-c", PROBE], cwd=BACKEND_DIR, env=env,
                          capture_output=True, text=True, timeout=120)


def probe(extra_env):
    proc = import_server(extra_env)
    assert proc.returncode == 0, f"server import failed: {proc.stderr[-2000:]}"
    return json.loads(proc.stdout.strip().splitlines()[-1]), proc.stderr


def test_production_boot_with_the_real_addresses_is_clean():
    result, stderr = probe({
        "FRONTEND_URL": "https://crm.clientverse.io",
        "CORS_ORIGINS": "https://crm.clientverse.io",
        "GOOGLE_REDIRECT_URI": "https://crm.clientverse.io/api/integrations/google/callback",
    })
    assert result["redirect_findings"] == []
    assert all(row["ok"] for row in result["report"])
    assert "Public URL check" not in stderr


def test_production_refuses_to_boot_on_a_localhost_frontend_url():
    proc = import_server({"FRONTEND_URL": "https://localhost:3000",
                          "CORS_ORIGINS": "https://localhost:3000"})
    assert proc.returncode != 0
    assert "local or private address" in proc.stderr


def test_production_boots_on_a_preview_frontend_url_but_says_so():
    result, stderr = probe({"FRONTEND_URL": "https://clientverse-crm.vercel.app",
                            "CORS_ORIGINS": "https://clientverse-crm.vercel.app"})
    assert "preview or copy host" in stderr
    frontend = next(r for r in result["report"] if r["name"] == "FRONTEND_URL")
    assert frontend["ok"] is False
    assert frontend["host"] == "clientverse-crm.vercel.app"
    # The derived Google callback is on the same preview host, so connecting is refused.
    assert result["redirect_findings"] == [public_url.PREVIEW]


def test_production_flags_a_google_callback_on_the_wrong_path():
    result, stderr = probe({
        "FRONTEND_URL": "https://crm.clientverse.io",
        "CORS_ORIGINS": "https://crm.clientverse.io",
        "GOOGLE_REDIRECT_URI": "https://crm.clientverse.io/oauth/callback",
    })
    assert result["redirect_findings"] == [public_url.INVALID]
    assert "Google connections are refused" in stderr
