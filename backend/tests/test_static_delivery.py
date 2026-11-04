"""How the compiled frontend is delivered (2026-11-04 audit, batch C).

The SPA bundle went out uncompressed and uncached: 1.9 MB on every visit. Static files are
now gzipped and cached by content hash; index.html and SPA deep links revalidate; API
responses are never compressed (they can carry session tokens beside user-supplied text).

Built on a tiny app that uses the same two classes over a temporary build directory, so the
test needs neither a frontend build nor a database.
"""

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_static_delivery_unit")
os.environ.setdefault("JWT_SECRET", "static-delivery-unit-jwt-secret-long-enough-12")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server

BUNDLE = "console.log('clientverse');\n" * 400  # ~11 KB, compresses well


def _app(build: Path) -> FastAPI:
    app = FastAPI()

    @app.get("/api/echo")
    def echo():
        return {"token": "x" * 2000}

    app.add_middleware(server.StaticGZipMiddleware)
    app.mount("/", server.ClientVerseStaticFiles(directory=str(build), html=True), name="frontend")
    return app


def _build(tmp_path: Path) -> Path:
    (tmp_path / "static" / "js").mkdir(parents=True)
    (tmp_path / "static" / "js" / "main.abc123.js").write_text(BUNDLE)
    (tmp_path / "index.html").write_text("<!doctype html><title>ClientVerse</title>" + "<p>shell</p>" * 200)
    return tmp_path


def test_hashed_static_files_are_gzipped_and_cached_for_a_year(tmp_path):
    client = TestClient(_app(_build(tmp_path)))
    response = client.get("/static/js/main.abc123.js", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.text == BUNDLE


def test_index_and_spa_deep_links_revalidate(tmp_path):
    client = TestClient(_app(_build(tmp_path)))
    for path in ("/", "/index.html", "/workspaces/ws_123", "/settings/team"):
        response = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-cache", path
        assert "shell" in response.text


def test_api_responses_are_never_compressed(tmp_path):
    client = TestClient(_app(_build(tmp_path)))
    response = client.get("/api/echo", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert "content-encoding" not in response.headers


def test_a_missing_asset_still_404s_instead_of_serving_the_shell(tmp_path):
    client = TestClient(_app(_build(tmp_path)))
    assert client.get("/static/js/missing.js").status_code == 404
