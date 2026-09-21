"""Test-session wiring.

The behavioural suite is written against a real MongoDB: the HTTP tests drive a
running API and the unit tests open their own `AsyncIOMotorClient`. Some
environments (CI sandboxes, restricted networks) cannot reach a mongod at all,
which would otherwise mean the suite simply does not run there.

When `MONGO_URL` uses the `mongomock://` scheme — a scheme no real deployment can
use, so production can never land here — the motor client is swapped for the
in-process `mongomock_motor` client. Nothing else changes: the same tests, the
same assertions, the same application code. Against a reachable mongod the file
is inert.
"""

import os

_MONGO_URL = os.environ.get("MONGO_URL", "")

if _MONGO_URL.startswith("mongomock://"):
    import motor.motor_asyncio as _motor
    from mongomock_motor import AsyncMongoMockClient as _MockClient

    class _PatchedClient(_MockClient):
        def __init__(self, *args, **kwargs):  # noqa: D107 - drops the URL, keeps the API
            super().__init__()

    _motor.AsyncIOMotorClient = _PatchedClient

    # mongomock returns None from find_one_and_update when a projection is combined with
    # return_document=AFTER, even though the update itself is applied. The application
    # reads that return value to decide whether it won an atomic state transition, so
    # without this the driver -- not the code under test -- would fail those tests. Apply
    # the projection in Python and leave the atomic update untouched.
    from mongomock_motor import AsyncMongoMockCollection as _MockCollection

    _orig_foau = _MockCollection.find_one_and_update

    async def _find_one_and_update(self, filter, update, projection=None, **kwargs):
        doc = await _orig_foau(self, filter, update, **kwargs)
        if doc is None or not projection:
            return doc
        if isinstance(projection, dict) and set(projection.values()) == {0}:
            return {k: v for k, v in doc.items() if k not in projection}
        if isinstance(projection, dict):
            keep = {k for k, v in projection.items() if v}
            keep.discard("_id")
            out = {k: v for k, v in doc.items() if k in keep}
            if projection.get("_id", 1):
                out["_id"] = doc.get("_id")
            return out
        return doc

    _MockCollection.find_one_and_update = _find_one_and_update

    # Modules that imported the symbol directly still need the patched one.
    for _name in ("server",):
        try:
            _mod = __import__(_name)
        except Exception:  # pragma: no cover - server import is optional here
            continue
        if hasattr(_mod, "AsyncIOMotorClient"):
            _mod.AsyncIOMotorClient = _PatchedClient
