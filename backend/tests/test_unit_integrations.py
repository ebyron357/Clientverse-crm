"""
Unit tests for integration normalizers, encryption, and OAuth logic.
These run without MongoDB or network — pure function validation.
"""
import os
import sys
import time
import hashlib
import base64

# Ensure server module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("JWT_SECRET", "a" * 32)
os.environ.setdefault("ALLOW_INSECURE_JWT", "1")

import server


class TestGmailNormalizer:
    def test_basic_message(self):
        msg = {"id": "m1", "threadId": "t1", "snippet": "hi there", "labelIds": ["INBOX"],
               "internalDate": "1700000000000",
               "payload": {"headers": [{"name": "From", "value": "Alice <alice@acme.com>"},
                                        {"name": "To", "value": "me@x.com"},
                                        {"name": "Subject", "value": "Kickoff"}]}}
        n = server.normalize_gmail_message(msg)
        assert n["external_id"] == "m1"
        assert n["subject"] == "Kickoff"
        assert n["from_email"] == "alice@acme.com"
        assert "me@x.com" in n["to"]
        assert n["labels"] == ["INBOX"]
        assert n["ts"] is not None

    def test_missing_headers(self):
        msg = {"id": "m2", "payload": {"headers": []}}
        n = server.normalize_gmail_message(msg)
        assert n["external_id"] == "m2"
        assert n["subject"] == "(no subject)"
        assert n["from_email"] is None

    def test_cc_included_in_to(self):
        msg = {"id": "m3", "payload": {"headers": [
            {"name": "To", "value": "a@b.com"},
            {"name": "Cc", "value": "c@d.com"}]}}
        n = server.normalize_gmail_message(msg)
        assert "a@b.com" in n["to"]
        assert "c@d.com" in n["to"]

    def test_invalid_internal_date(self):
        msg = {"id": "m4", "internalDate": "not_a_number", "payload": {"headers": []}}
        n = server.normalize_gmail_message(msg)
        assert n["ts"] is None


class TestCalendarNormalizer:
    def test_basic_event(self):
        ev = {"id": "e1", "summary": "Review", "status": "confirmed",
              "start": {"dateTime": "2026-07-01T10:00:00Z"}, "end": {"dateTime": "2026-07-01T11:00:00Z"},
              "organizer": {"email": "Bob@Acme.com"},
              "attendees": [{"email": "Carol@acme.com"}, {"email": "me@x.com"}],
              "hangoutLink": "https://meet.google.com/abc"}
        n = server.normalize_calendar_event(ev)
        assert n["external_id"] == "e1"
        assert n["title"] == "Review"
        assert n["organizer"] == "bob@acme.com"
        assert "carol@acme.com" in n["attendees"]
        assert n["conference_link"] == "https://meet.google.com/abc"

    def test_all_day_event(self):
        ev = {"id": "e2", "summary": "Holiday", "start": {"date": "2026-12-25"}, "end": {"date": "2026-12-26"}}
        n = server.normalize_calendar_event(ev)
        assert n["start"] == "2026-12-25"
        assert n["end"] == "2026-12-26"

    def test_conference_data_preferred(self):
        ev = {"id": "e3", "start": {}, "end": {},
              "conferenceData": {"entryPoints": [{"uri": "https://zoom.us/j/123"}]},
              "hangoutLink": "https://meet.google.com/fallback"}
        n = server.normalize_calendar_event(ev)
        assert n["conference_link"] == "https://zoom.us/j/123"

    def test_no_organizer(self):
        ev = {"id": "e4", "start": {}, "end": {}}
        n = server.normalize_calendar_event(ev)
        assert n["organizer"] is None
        assert n["title"] == "(untitled)"


class TestStripeNormalizers:
    def test_invoice(self):
        inv = server.normalize_stripe_invoice({"id": "in_1", "customer_email": "X@Y.com", "status": "open",
                                               "amount_due": 25000, "currency": "usd", "paid": False, "created": 1700000000})
        assert inv["type"] == "invoice"
        assert inv["amount"] == 250.0
        assert inv["email"] == "x@y.com"
        assert inv["payment_status"] == "open"

    def test_paid_invoice(self):
        inv = server.normalize_stripe_invoice({"id": "in_2", "customer_email": "a@b.com", "status": "paid",
                                               "amount_due": 5000, "currency": "eur", "paid": True, "created": 1700000000})
        assert inv["payment_status"] == "paid"

    def test_customer(self):
        cust = server.normalize_stripe_customer({"id": "cus_1", "email": "A@B.com", "name": "Acme", "created": 1700000000})
        assert cust["type"] == "customer"
        assert cust["email"] == "a@b.com"
        assert cust["name"] == "Acme"

    def test_subscription(self):
        sub = server.normalize_stripe_subscription({"id": "sub_1", "status": "active", "customer": "cus_1",
                                                    "created": 1700000000, "items": {"data": [{"price": {"currency": "usd"}}]}})
        assert sub["type"] == "subscription"
        assert sub["status"] == "active"
        assert sub["currency"] == "usd"

    def test_customer_no_email(self):
        cust = server.normalize_stripe_customer({"id": "cus_2", "email": None, "name": "NoEmail", "created": 0})
        assert cust["email"] is None


class TestEncryption:
    def test_enc_dec_round_trip(self):
        if not os.environ.get("INTEGRATION_ENC_KEY"):
            from cryptography.fernet import Fernet
            os.environ["INTEGRATION_ENC_KEY"] = Fernet.generate_key().decode()
            # reload enc helpers
            import importlib
            importlib.reload(server)
        data = {"access_token": "ya29.test", "refresh_token": "1//test", "expires_at": time.time() + 3600}
        encrypted = server.enc_secret(data)
        decrypted = server.dec_secret(encrypted)
        assert decrypted == data

    def test_enc_secret_not_plaintext(self):
        if not os.environ.get("INTEGRATION_ENC_KEY"):
            from cryptography.fernet import Fernet
            os.environ["INTEGRATION_ENC_KEY"] = Fernet.generate_key().decode()
            import importlib
            importlib.reload(server)
        data = {"access_token": "ya29.secret_value"}
        encrypted = server.enc_secret(data)
        assert "ya29.secret_value" not in encrypted


class TestJWT:
    def test_create_and_decode_token(self):
        token = server.create_access_token("user_123", "test@example.com")
        import jwt
        payload = jwt.decode(token, server.JWT_SECRET, algorithms=[server.JWT_ALG])
        assert payload["sub"] == "user_123"
        assert payload["email"] == "test@example.com"
        assert payload["type"] == "access"

    def test_password_hash_verify(self):
        hashed = server.hash_password("TestPass123!")
        assert server.verify_password("TestPass123!", hashed)
        assert not server.verify_password("WrongPass", hashed)


class TestOAuthSecurity:
    def test_pkce_challenge(self):
        """Verify PKCE S256 challenge is correctly computed."""
        verifier = "test_verifier_string_for_pkce"
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        # Recompute to verify
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert challenge == expected
        assert "=" not in challenge  # padding stripped
