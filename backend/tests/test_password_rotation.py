"""Rotating a password ends the sessions issued under the old one.

`seed()` re-syncs the administrator's password from ADMIN_PASSWORD at every boot, and
the owner handoff tells the owner to rotate it after first login. Tokens last seven days
and carried nothing tied to the password, so a leaked token outlived the rotation meant
to cut it off.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "password-rotation-unit-jwt-secret-long-enough")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server


def _request(token):
    return SimpleNamespace(cookies={}, headers={"Authorization": f"Bearer {token}"})


def test_rotating_admin_password_ends_earlier_sessions(monkeypatch):
    email = f"operator_{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setenv("ADMIN_EMAIL", email)
    monkeypatch.setenv("ADMIN_PASSWORD", "FirstPassword2026!")
    monkeypatch.delenv("DEMO_MEMBER_EMAIL", raising=False)
    name = f"clientverse_pwrot_{uuid.uuid4().hex[:8]}"

    async def body():
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        previous, server.db = server.db, server.mclient[name]
        try:
            await server.seed()
            user = await server.db.users.find_one({"email": email})
            old = server.create_access_token(user["user_id"], email,
                                             user.get("password_version") or 0)
            assert (await server.get_current_user(_request(old)))["email"] == email

            os.environ["ADMIN_PASSWORD"] = "RotatedPassword2026!"
            await server.seed()
            with pytest.raises(server.HTTPException) as ended:
                await server.get_current_user(_request(old))

            rotated = await server.db.users.find_one({"email": email})
            fresh = server.create_access_token(rotated["user_id"], email,
                                               rotated.get("password_version") or 0)
            still_valid = await server.get_current_user(_request(fresh))
            await server.seed()  # an unchanged password ends nothing
            return ended.value, still_valid, await server.get_current_user(_request(fresh))
        finally:
            await server.mclient.drop_database(name)
            server.db = previous

    loop = asyncio.new_event_loop()
    try:
        ended, still_valid, after_reboot = loop.run_until_complete(body())
    finally:
        loop.close()
    assert ended.status_code == 401 and "password change" in ended.detail
    assert still_valid["email"] == email and after_reboot["email"] == email
