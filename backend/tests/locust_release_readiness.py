import os

from locust import HttpUser, between, task


class ClientVerseReadUser(HttpUser):
    wait_time = between(0.1, 0.4)

    def on_start(self):
        email = os.environ["LOADTEST_ADMIN_EMAIL"]
        password = os.environ["LOADTEST_ADMIN_PASSWORD"]
        with self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
            name="POST /api/auth/login",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login failed with {response.status_code}")
                return
            token = response.json().get("token")
            if not token:
                response.failure("login response did not contain an access token")
                return
            self.headers = {"Authorization": f"Bearer {token}"}

        with self.client.get(
            "/api/workspaces",
            headers=self.headers,
            name="GET /api/workspaces",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                workspaces = response.json()
                self.workspace_id = workspaces[0]["id"] if workspaces else None
            else:
                self.workspace_id = None
                response.failure(f"workspace list failed with {response.status_code}")

    @task(4)
    def dashboard(self):
        self.client.get("/api/dashboard", headers=self.headers, name="GET /api/dashboard")

    @task(3)
    def client_directory(self):
        self.client.get("/api/companies", headers=self.headers, name="GET /api/companies")
        self.client.get("/api/contacts", headers=self.headers, name="GET /api/contacts")

    @task(3)
    def client_workspace(self):
        if self.workspace_id:
            self.client.get(
                f"/api/workspaces/{self.workspace_id}",
                headers=self.headers,
                name="GET /api/workspaces/:id",
            )

    @task(2)
    def portal_and_client_operations(self):
        self.client.get("/api/portal-links", headers=self.headers, name="GET /api/portal-links")
        self.client.get("/api/client-ops/summary", headers=self.headers, name="GET /api/client-ops/summary")

    @task(2)
    def field_and_appointments(self):
        self.client.get("/api/appointments", headers=self.headers, name="GET /api/appointments")
        self.client.get("/api/field/check-ins", headers=self.headers, name="GET /api/field/check-ins")
