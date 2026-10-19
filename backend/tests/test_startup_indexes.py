"""Startup index building: one failure must not skip the rest.

The index builders used to share one try block, so the first failure silently skipped
every index after it -- including uniqueness guarantees that later modules rely on.
"""

import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ["LEAD_SLA_WATCHER"] = "0"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_startup_indexes_unit")
os.environ.setdefault("JWT_SECRET", "startup-indexes-unit-jwt-secret-long-enough-12")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_EMAIL", "admin@startup-indexes.example")
os.environ.setdefault("ADMIN_PASSWORD", "Startup-Indexes-Admin-1!")

from fastapi.testclient import TestClient

import crm_core
import server
import website_forms


def test_a_failing_index_set_does_not_skip_the_ones_after_it(monkeypatch):
    registered = server.lead_pipeline.db
    server.db = registered
    server.mclient = getattr(registered, "client", server.mclient)

    async def broken(_db):
        raise RuntimeError("existing data violates this index")

    monkeypatch.setattr(crm_core, "ensure_indexes", broken)
    with TestClient(server.app) as client:
        async def indexes():
            return await server.db[website_forms.FORMS].index_information()
        names = client.portal.call(indexes)
    # website_forms builds after crm_core in the startup list.
    assert any("public_key" in name for name in names), names
