"""Test-session wiring.

The behavioural suite is written against a real MongoDB: the HTTP tests drive a
running API and the unit tests open their own `AsyncIOMotorClient`. Some
environments (CI sandboxes, restricted networks) cannot reach a mongod at all,
which would otherwise mean the suite simply does not run there.

When `MONGO_URL` uses the `mongomock://` scheme — a scheme no real deployment can
use, so production can never land here — the motor client is swapped for the
in-process `mongomock_motor` client. Nothing else changes: the same tests, the
same assertions, the same application code. Against a reachable mongod the driver
swap is inert; only the in-process scheduler default below applies.
"""

import os

# The API runs its scheduled jobs in-process by default. Under test they would sweep the
# same database the tests are asserting on, at times no test controls, so the harness
# turns them off -- as `LEAD_SLA_WATCHER=0` does for the lead watcher. A test that wants
# the scheduler builds its own (`tests/test_scheduler.py`) or sets the variable itself.
# `setdefault`, so an explicit value in the environment still wins.
os.environ.setdefault("IN_PROCESS_SCHEDULER", "0")
# Likewise the automation watcher, which resumes runs parked on a wait step; tests resume
# them by calling `resume_due` with the time they want.
os.environ.setdefault("AUTOMATION_WATCHER", "0")

_MONGO_URL = os.environ.get("MONGO_URL", "")

if _MONGO_URL.startswith("mongomock://"):
    import motor.motor_asyncio as _motor
    from mongomock_motor import AsyncMongoMockClient as _MockClient

    class _PatchedClient(_MockClient):
        def __init__(self, *args, **kwargs):
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
else:
    # Against a real mongod, motor binds a client to the first event loop that uses it
    # (`AgnosticClient.io_loop`). Each in-process `TestClient` runs the app on a loop of
    # its own, but the route modules (crm_core, website_forms, booking, ...) keep the
    # database handle they were registered with at import. So the second test module in
    # a worker to start a TestClient found that client still bound to the first module's
    # loop, already closed: "Event loop is closed" from the startup index build, every
    # route, and every fixture call after it. Production runs one loop per process, so
    # this never arises there. Releasing the app's clients as each TestClient starts lets
    # them bind to that TestClient's own loop, as they would in a fresh process.
    #
    # The app's shutdown also closes its client, and a closed pymongo client cannot be
    # used again ("Cannot use MongoClient after close"); the route modules would carry
    # that closed handle into the next module. So under test the shared client stays
    # open for the life of the worker process, and only its loop binding is released.
    import sys as _sys

    from starlette.testclient import TestClient as _TestClient

    _enter = _TestClient.__enter__

    def _enter_with_unbound_clients(self):
        server = _sys.modules.get("server")
        if server is not None:
            # A motor client answers any unknown attribute with a database of that name,
            # so clients and databases are told apart rather than probed.
            clients = [getattr(server, "mclient", None)]
            databases = [getattr(server, "db", None)]
            for name in ("lead_pipeline", "booking_service"):
                databases.append(getattr(getattr(server, name, None), "db", None))
            clients += [database.client for database in databases if database is not None]
            for client in clients:
                if "_io_loop" in getattr(client, "__dict__", {}):
                    client._io_loop = None
                    # motor's own `close` is a property; the pymongo client underneath
                    # is what actually closes, so that is the one kept open.
                    client.delegate.close = _keep_open
        return _enter(self)

    def _keep_open():
        """Stands in for the shared client's close() under test (see above)."""

    _TestClient.__enter__ = _enter_with_unbound_clients
