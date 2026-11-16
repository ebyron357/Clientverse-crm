"""Private editor drafts: identity isolation, stale-write ordering, idempotent retry,
expiry and version-exact discard. Runs on the in-process driver; it needs no
transactions because each draft write is a single-document conditional update."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

import drafts
from drafts import DraftStore, DraftWrite

ALICE = {"tenant_id": "t1", "user_id": "u-alice"}
BOB = {"tenant_id": "t1", "user_id": "u-bob"}
OTHER_TENANT = {"tenant_id": "t2", "user_id": "u-alice"}


class Clock:
    def __init__(self):
        # Anchored to real time: the in-process driver applies TTL indexes against the
        # wall clock, so a fixed past date would be swept before the store could read it.
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def __call__(self):
        return self.now


def op(n):
    return f"operation-{n:010d}"


def write(expected, content, n, target=3):
    return DraftWrite(operation_id=op(n), expected_draft_version=expected, target_version=target, content=content)


@pytest.fixture
def env():
    db = AsyncMongoMockClient()["drafts_test"]
    asyncio.run(drafts.prepare(db))
    clock = Clock()
    return DraftStore(db, clock), clock


def run(coro):
    return asyncio.run(coro)


def test_first_save_then_refresh_restores(env):
    store, _ = env
    saved = run(store.write(ALICE, "lead", "L1", "note", write(0, "Called, left voicemail", 1)))
    assert saved["state"] == "draft_saved" and saved["draft"]["draft_version"] == 1
    restored = run(store.read(ALICE, "lead", "L1", "note"))
    assert restored["content"] == "Called, left voicemail" and restored["target_version"] == 3


def test_drafts_are_private_to_actor_and_tenant(env):
    store, _ = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "private", 1)))
    assert run(store.read(BOB, "lead", "L1", "note")) is None
    assert run(store.read(OTHER_TENANT, "lead", "L1", "note")) is None


def test_stale_autosave_cannot_overwrite_newer_text(env):
    store, _ = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "v1", 1)))
    run(store.write(ALICE, "lead", "L1", "note", write(1, "v2 from phone", 2)))
    with pytest.raises(HTTPException) as err:
        run(store.write(ALICE, "lead", "L1", "note", write(1, "late v2 from laptop", 3)))
    assert err.value.status_code == 409
    assert err.value.detail["code"] == "draft_conflict"
    assert err.value.detail["current"]["content"] == "v2 from phone"


def test_concurrent_first_saves_from_two_devices(env):
    store, _ = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "tab A", 1)))
    with pytest.raises(HTTPException) as err:
        run(store.write(ALICE, "lead", "L1", "note", write(0, "tab B", 2)))
    assert err.value.detail["current"]["content"] == "tab A"


def test_retry_of_same_operation_is_idempotent(env):
    store, _ = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "v1", 1)))
    again = run(store.write(ALICE, "lead", "L1", "note", write(0, "v1", 1)))
    assert again["draft"]["draft_version"] == 1


def test_operation_key_reuse_with_different_text_is_refused(env):
    store, _ = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "v1", 1)))
    with pytest.raises(HTTPException) as err:
        run(store.write(ALICE, "lead", "L1", "note", write(0, "different", 1)))
    assert err.value.detail["code"] == "operation_key_reused"


def test_expired_draft_is_not_restored(env):
    store, clock = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "old", 1)))
    clock.now += timedelta(days=drafts.INACTIVITY_DAYS, seconds=1)
    assert run(store.read(ALICE, "lead", "L1", "note")) is None
    fresh = run(store.write(ALICE, "lead", "L1", "note", write(0, "new start", 2)))
    assert fresh["draft"]["draft_version"] == 1


def test_activity_extends_expiry(env):
    store, clock = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "v1", 1)))
    clock.now += timedelta(days=20)
    run(store.write(ALICE, "lead", "L1", "note", write(1, "v2", 2)))
    clock.now += timedelta(days=20)
    assert run(store.read(ALICE, "lead", "L1", "note"))["content"] == "v2"


def test_discard_consumes_only_exact_version(env):
    store, _ = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "submitted text", 1)))
    run(store.write(ALICE, "lead", "L1", "note", write(1, "typed during save", 2)))
    result = run(store.discard(ALICE, "lead", "L1", "note", draft_version=1))
    assert result["state"] == "newer_draft_kept"
    assert run(store.read(ALICE, "lead", "L1", "note"))["content"] == "typed during save"
    assert run(store.discard(ALICE, "lead", "L1", "note", draft_version=2))["state"] == "discarded"
    assert run(store.read(ALICE, "lead", "L1", "note")) is None


def test_purge_actor_removes_only_that_actor(env):
    store, _ = env
    run(store.write(ALICE, "lead", "L1", "note", write(0, "a", 1)))
    run(store.write(BOB, "lead", "L1", "note", write(0, "b", 2)))
    assert run(store.purge_actor("t1", "u-alice")) == 1
    assert run(store.read(BOB, "lead", "L1", "note"))["content"] == "b"


def test_content_is_bounded():
    with pytest.raises(ValueError):
        DraftWrite(operation_id=op(1), expected_draft_version=0, target_version=0,
                   content="x" * (drafts.MAX_CONTENT + 1))


def test_rollout_flag_is_explicit(monkeypatch):
    monkeypatch.setenv("RECORD_DRAFT_TENANTS", " t1 , t9 ")
    assert drafts.enabled("t1") and not drafts.enabled("t2")
    monkeypatch.delenv("RECORD_DRAFT_TENANTS")
    assert not drafts.enabled("t1")
