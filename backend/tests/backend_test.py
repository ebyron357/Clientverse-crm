"""ClientVerse.io backend regression tests"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "AdminPass123!")


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="session")
def new_tenant_user():
    s = requests.Session()
    email = f"TEST_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "Passw0rd!!", "name": "Test User"}, timeout=30)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s, email


# --- Auth ---
class TestAuth:
    def test_login(self, admin):
        r = admin.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code in (400, 401)

    def test_register_creates_new_tenant(self, new_tenant_user, admin):
        s, email = new_tenant_user
        me = s.get(f"{API}/auth/me").json()
        admin_me = admin.get(f"{API}/auth/me").json()
        assert me["tenant_id"] != admin_me["tenant_id"], "new user should be in different tenant"


# --- Dashboard ---
class TestDashboard:
    def test_dashboard(self, admin):
        r = admin.get(f"{API}/dashboard")
        assert r.status_code == 200
        d = r.json()
        for k in ["pipeline_value", "won_value", "active_workspaces", "at_risk_commitments", "funnel", "portfolio"]:
            assert k in d, f"missing {k}: {list(d.keys())}"


# --- Pipeline ---
class TestPipeline:
    def test_create_opportunity_and_move_to_won_creates_workspace(self, admin):
        # create company first
        c = admin.post(f"{API}/companies", json={"name": f"TEST_Co_{uuid.uuid4().hex[:6]}"})
        assert c.status_code in (200, 201), c.text
        company_id = c.json()["id"]

        payload = {"name": f"TEST_Opp_{uuid.uuid4().hex[:6]}", "value": 12345, "stage": "qualified", "company_id": company_id}
        r = admin.post(f"{API}/opportunities", json=payload)
        assert r.status_code in (200, 201), r.text
        opp = r.json()
        opp_id = opp["id"]

        # baseline workspace count
        ws0 = admin.get(f"{API}/workspaces").json()
        n0 = len(ws0)

        # move to closed_won
        r2 = admin.patch(f"{API}/opportunities/{opp_id}/stage", json={"stage": "closed_won"})
        assert r2.status_code in (200, 204), r2.text

        ws1 = admin.get(f"{API}/workspaces").json()
        assert len(ws1) >= n0 + 1, "moving to closed_won should auto-create workspace"


# --- Directory ---
class TestDirectory:
    def test_company_and_contact_crud(self, admin):
        r = admin.post(f"{API}/companies", json={"name": f"TEST_Company_{uuid.uuid4().hex[:6]}"})
        assert r.status_code in (200, 201)
        cid = r.json()["id"]

        r = admin.post(f"{API}/contacts", json={"name": "TEST Contact", "email": "test@x.com", "company_id": cid})
        assert r.status_code in (200, 201)

        # list
        assert any(cid == c["id"] for c in admin.get(f"{API}/companies").json())

    def test_contact_rejects_malformed_email(self, admin):
        r = admin.post(f"{API}/contacts", json={"name": "Malformed Contact", "email": "not-an-email"})
        assert r.status_code == 422


# --- Workspaces & Health ---
class TestWorkspaces:
    def test_workspaces_list_and_detail(self, admin):
        r = admin.get(f"{API}/workspaces")
        assert r.status_code == 200
        ws = r.json()
        assert isinstance(ws, list) and len(ws) > 0
        wid = ws[0]["id"]
        r2 = admin.get(f"{API}/workspaces/{wid}")
        assert r2.status_code == 200
        d = r2.json()
        assert "health" in d
        assert "score" in d["health"] and "factors" in d["health"]
        assert "commitments" in d and "tasks" in d and "deliverables" in d


# --- AI ---
class TestAI:
    def _ai_available(self):
        if not os.environ.get("EMERGENT_LLM_KEY"):
            return False
        try:
            import emergentintegrations  # noqa: F401
            return True
        except ImportError:
            return False

    def test_ai_health_summary(self, admin):
        if not self._ai_available():
            pytest.skip("EMERGENT_LLM_KEY / emergentintegrations unavailable — AI generation requires external service")
        ws = admin.get(f"{API}/workspaces").json()
        wid = ws[0]["id"]
        r = admin.post(f"{API}/ai/generate", json={"mode": "health_summary", "workspace_id": wid}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "output" in d or "text" in d or "content" in d, list(d.keys())
        # source refs
        assert any(k in d for k in ["sources", "source_records", "references"]), list(d.keys())
        assert "run_id" in d or "id" in d
        assert any(k in d for k in ["model_version", "model"]), list(d.keys())

    def test_ai_draft(self, admin):
        if not self._ai_available():
            pytest.skip("EMERGENT_LLM_KEY / emergentintegrations unavailable — AI generation requires external service")
        ws = admin.get(f"{API}/workspaces").json()
        wid = ws[0]["id"]
        r = admin.post(f"{API}/ai/generate", json={"mode": "draft_message", "workspace_id": wid, "instruction": "Send a friendly status update"}, timeout=90)
        assert r.status_code == 200, r.text


# --- Registries ---
class TestRegistries:
    @pytest.mark.parametrize("kind", ["integrations", "mcp-servers", "plugins", "webhooks"])
    def test_registry(self, admin, kind):
        r = admin.get(f"{API}/registry/{kind}")
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)


# --- Audit ---
class TestAudit:
    def test_events(self, admin):
        r = admin.get(f"{API}/events")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# --- Tenant isolation ---
class TestTenantIsolation:
    def test_new_user_no_admin_data(self, new_tenant_user):
        s, _ = new_tenant_user
        companies = s.get(f"{API}/companies").json()
        workspaces = s.get(f"{API}/workspaces").json()
        events = s.get(f"{API}/events").json()
        # New tenant should NOT see admin's seeded demo companies
        names = [c.get("name", "") for c in companies]
        assert not any("Acme" in n or "Globex" in n or "Initech" in n for n in names), f"leaked: {names}"
        assert len(workspaces) == 0, f"leaked workspaces: {len(workspaces)}"
