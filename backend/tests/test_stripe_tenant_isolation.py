"""Cross-tenant Stripe isolation tests (pilot-readiness security pass, Phase 1).

Background: sync_stripe previously read one global STRIPE_API_KEY and imported every
customer/invoice/subscription from the connected Stripe account into whichever tenant
called sync, without checking whether the record actually belonged to that tenant's own
contacts (unlike the Gmail/Calendar adapters, which already skip unmatched records). Two
pilot companies sharing one deployment could therefore see each other's Stripe data.

These tests call the async provider/webhook functions directly, in-process, so the Stripe
SDK can be monkeypatched (a real HTTP round trip to a separately-running server process
cannot be intercepted this way, which is why the existing live Stripe test in
test_integrations.py can only run with a real STRIPE_API_KEY and skips otherwise).

They use the real `server.db` handle (a live MongoDB in CI, or a mongomock substitute in
local sandboxes without Docker) rather than hand-rolled fakes, so upserts, `$setOnInsert`,
and query filters behave exactly as they do in production.
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy

from cryptography.fernet import Fernet

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["APP_ENV"] = "test"
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clientverse_stripe_isolation_unit")
os.environ.setdefault("JWT_SECRET", "stripe-isolation-unit-jwt-secret-long-enough")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")
os.environ.setdefault("INTEGRATION_ENC_KEY", Fernet.generate_key().decode())

import server  # noqa: E402


def run(coro):
    # Motor's AsyncIOMotorClient binds to whatever event loop is running when it first
    # performs an operation; reusing plain asyncio.run() (a fresh loop every call) across
    # many calls in one process breaks it with "Event loop is closed" against a real
    # MongoDB (this only worked against a mongomock substitute, which has no such
    # binding). Bind a fresh client to a fresh loop on every call instead.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        server.mclient = server.AsyncIOMotorClient(os.environ["MONGO_URL"])
        server.db = server.mclient[os.environ["DB_NAME"]]
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _tenant_id():
    return f"ten_stripeiso_{uuid.uuid4().hex[:10]}"


async def _seed_contact(tenant_id, email, company_id=None):
    await server.db.contacts.insert_one({
        "id": server.new_id("con"), "tenant_id": tenant_id, "email": email,
        "name": email, "company_id": company_id, "created_at": server.now_iso(),
    })


def _fake_customer(cid, email, name="Cust"):
    return {"id": cid, "email": email, "name": name, "currency": "usd", "created": 1700000000}


def _fake_invoice(iid, customer_email, amount_due=5000, paid=False, status="open"):
    return {"id": iid, "customer_email": customer_email, "status": status,
            "amount_due": amount_due, "currency": "usd", "paid": paid, "created": 1700000000}


def _fake_subscription(sid, customer_id, status="active"):
    return {"id": sid, "customer": customer_id, "status": status,
            "items": {"data": [{"price": {"currency": "usd"}}]}, "created": 1700000000}


def _patch_stripe_lists(monkeypatch, customers=None, invoices=None, subscriptions=None):
    monkeypatch.setattr(server._stripe.Customer, "list",
                         lambda **kw: SimpleNamespace(data=customers or []))
    monkeypatch.setattr(server._stripe.Invoice, "list",
                         lambda **kw: SimpleNamespace(data=invoices or []))
    monkeypatch.setattr(server._stripe.Subscription, "list",
                         lambda **kw: SimpleNamespace(data=subscriptions or []))


# ---------- A & B: tenant A and tenant B Stripe objects are mutually invisible ----------

def test_stripe_sync_tenant_a_and_b_objects_are_mutually_invisible(monkeypatch):
    tenant_a = _tenant_id()
    tenant_b = _tenant_id()
    run(_seed_contact(tenant_a, "alice@acme-a.example"))
    run(_seed_contact(tenant_b, "bob@acme-b.example"))

    shared_customers = [
        _fake_customer("cus_alice", "alice@acme-a.example", "Alice"),
        _fake_customer("cus_bob", "bob@acme-b.example", "Bob"),
    ]
    shared_invoices = [
        _fake_invoice("in_alice", "alice@acme-a.example"),
        _fake_invoice("in_bob", "bob@acme-b.example"),
    ]
    _patch_stripe_lists(monkeypatch, customers=shared_customers, invoices=shared_invoices)
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_shared_account")

    run(server.sync_stripe(tenant_a, "test"))
    _patch_stripe_lists(monkeypatch, customers=shared_customers, invoices=shared_invoices)
    run(server.sync_stripe(tenant_b, "test"))

    a_rows = run(server.db.crm_billing.find({"tenant_id": tenant_a}, {"_id": 0}).to_list(100))
    b_rows = run(server.db.crm_billing.find({"tenant_id": tenant_b}, {"_id": 0}).to_list(100))

    a_emails = {r.get("email") for r in a_rows}
    b_emails = {r.get("email") for r in b_rows}

    assert "alice@acme-a.example" in a_emails
    assert "bob@acme-b.example" not in a_emails, "Tenant A can see Tenant B's Stripe customer"
    assert "bob@acme-b.example" in b_emails
    assert "alice@acme-a.example" not in b_emails, "Tenant B can see Tenant A's Stripe customer"


# ---------- C: direct-ID access does not bypass tenant filtering ----------

def test_stripe_payment_intent_direct_id_access_denied_cross_tenant(monkeypatch):
    tenant_a = _tenant_id()
    tenant_b = _tenant_id()
    invoice_id = f"inv_{uuid.uuid4().hex[:10]}"
    run(server.db.invoices.insert_one({
        "id": invoice_id, "tenant_id": tenant_a, "workspace_id": "ws_x", "total": 10.0,
        "currency": "usd", "status": "issued",
    }))
    monkeypatch.setenv("STRIPE_API_KEY", "rk_test_x")

    async def _attempt():
        return await server.create_stripe_payment_intent(
            invoice_id, server.StripePaymentIntentInput(),
            user={"tenant_id": tenant_b, "email": "eve@example.com"},
        )

    try:
        run(_attempt())
        raise AssertionError("expected cross-tenant invoice access to be denied")
    except server.HTTPException as exc:
        assert exc.status_code == 404


# ---------- D: webhook processing cannot attach records to the wrong tenant ----------

def test_stripe_webhook_cannot_attach_event_to_a_different_tenants_invoice(monkeypatch):
    tenant_a = _tenant_id()
    tenant_b = _tenant_id()
    invoice_b_id = f"inv_{uuid.uuid4().hex[:10]}"
    run(server.db.invoices.insert_one({
        "id": invoice_b_id, "tenant_id": tenant_b, "workspace_id": "ws_b", "total": 40.0,
        "currency": "usd", "status": "issued", "payment_status": "unpaid",
        "stripe_payment_intent_id": None,
    }))
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_fake")

    event = {
        "id": f"evt_{uuid.uuid4().hex[:10]}", "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_attacker_controlled", "amount_received": 4000, "currency": "usd",
            # Attacker (or a misrouted webhook) claims tenant A but targets tenant B's invoice id.
            "metadata": {"clientverse_tenant_id": tenant_a, "clientverse_invoice_id": invoice_b_id},
        }},
    }
    monkeypatch.setattr(server._stripe.Webhook, "construct_event",
                         lambda *_a, **_k: deepcopy(event))

    class FakeRequest:
        headers = {"Stripe-Signature": "t=1,v1=valid"}

        async def body(self):
            return b"signed-payload"

    result = run(server.stripe_webhook(FakeRequest()))
    assert result["handled"] is False

    invoice_b = run(server.db.invoices.find_one({"id": invoice_b_id}, {"_id": 0}))
    assert invoice_b["payment_status"] == "unpaid"
    assert invoice_b["stripe_payment_intent_id"] is None


# ---------- E: sync does not import unmatched records anywhere ----------

def test_stripe_sync_skips_unmatched_records_entirely(monkeypatch):
    tenant_a = _tenant_id()
    run(_seed_contact(tenant_a, "alice@acme-a.example"))

    customers = [
        _fake_customer("cus_alice", "alice@acme-a.example", "Alice"),
        _fake_customer("cus_mallory", "mallory@unrelated.example", "Mallory"),
    ]
    _patch_stripe_lists(monkeypatch, customers=customers)
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_shared_account")

    summary = run(server.sync_stripe(tenant_a, "test"))

    rows = run(server.db.crm_billing.find({"tenant_id": tenant_a}, {"_id": 0}).to_list(100))
    emails = {r.get("email") for r in rows}
    assert "alice@acme-a.example" in emails
    assert "mallory@unrelated.example" not in emails

    all_billing_for_mallory = run(
        server.db.crm_billing.find({"email": "mallory@unrelated.example"}, {"_id": 0}).to_list(100)
    )
    assert all_billing_for_mallory == [], "unmatched Stripe customer must not be stored under any tenant"
    assert summary["matched"] == 1
    assert summary.get("skipped_unmatched", 0) == 1


# ---------- per-tenant credential storage mirrors the Google pattern ----------

def test_sync_stripe_prefers_tenant_scoped_credential_over_shared_env_key(monkeypatch):
    tenant_a = _tenant_id()
    run(_seed_contact(tenant_a, "alice@acme-a.example"))
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_shared_should_not_be_used")

    run(server.db.stripe_credentials.insert_one({
        "tenant_id": tenant_a,
        "enc": server.enc_secret({"api_key": "sk_test_tenant_a_own_key"}),
        "credential_version": 1,
    }))

    seen_keys = []

    def fake_customer_list(**kw):
        seen_keys.append(server._stripe.api_key)
        return SimpleNamespace(data=[_fake_customer("cus_alice", "alice@acme-a.example")])

    monkeypatch.setattr(server._stripe.Customer, "list", fake_customer_list)
    monkeypatch.setattr(server._stripe.Invoice, "list", lambda **kw: SimpleNamespace(data=[]))
    monkeypatch.setattr(server._stripe.Subscription, "list", lambda **kw: SimpleNamespace(data=[]))

    run(server.sync_stripe(tenant_a, "test"))

    assert seen_keys == ["sk_test_tenant_a_own_key"]


def test_stripe_connect_with_api_key_stores_tenant_scoped_credential_not_shared(monkeypatch):
    tenant_a = _tenant_id()
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_shared_should_not_be_stored")
    monkeypatch.setattr(server._stripe.Account, "retrieve",
                         lambda: {"email": "billing@acme-a.example", "id": "acct_a"})

    result = run(server.stripe_connect(
        server.StripeConnectInput(api_key="sk_test_tenant_a_own_key"),
        user={"tenant_id": tenant_a, "email": "admin@acme-a.example"},
    ))
    assert result["ok"] is True

    stored = run(server.db.stripe_credentials.find_one({"tenant_id": tenant_a}, {"_id": 0}))
    assert stored is not None
    decrypted = server.dec_secret(stored["enc"])
    assert decrypted["api_key"] == "sk_test_tenant_a_own_key"

    # disconnecting must remove the tenant-scoped credential too
    run(server.disconnect_provider("stripe", user={"tenant_id": tenant_a, "email": "admin@acme-a.example"}))
    stored_after = run(server.db.stripe_credentials.find_one({"tenant_id": tenant_a}, {"_id": 0}))
    assert stored_after is None
