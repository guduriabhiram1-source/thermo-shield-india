"""Registration, Gmail-code verification, JWT, refresh, logout, roles."""
from __future__ import annotations

import jwt

from .conftest import EMAIL, auth


def test_register_requires_verification_before_login(client):
    email = "pending.user@example.org"
    pw = "AnotherStr0ngPass"
    r = client.post("/api/auth/register", json={"email": email, "password": pw, "confirm_password": pw})
    assert r.status_code == 201, r.text
    msg = next(m for m in reversed(EMAIL.sent) if email in m.to)
    assert "verification code" in msg.subject.lower() and msg.text.count("expires in 10 minutes")
    code = msg.subject.split(":")[-1].strip()
    assert len(code) == 6 and code.isdigit()
    # login blocked until verified
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 403 and "verification required" in r.json()["detail"].lower()
    # wrong code rejected, right code accepted
    assert client.post("/api/auth/verify-email", json={"email": email, "code": "000000" if code != "000000" else "111111"}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"email": email, "code": code}).status_code == 200
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["is_verified"] is True and body["user"]["role"] == "VIEWER" and body["refresh_token"]


def test_password_policy_and_mismatch(client):
    r = client.post("/api/auth/register", json={"email": "weak@example.org", "password": "short1", "confirm_password": "short1"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "weak@example.org", "password": "LongEnoughPass1", "confirm_password": "LongEnoughPass2"})
    assert r.status_code == 422


def test_resend_verification_cooldown(client):
    email = "resend.user@example.org"
    pw = "ResendStr0ngPass"
    assert client.post("/api/auth/register", json={"email": email, "password": pw, "confirm_password": pw}).status_code == 201
    r = client.post("/api/auth/resend-verification", json={"email": email})
    assert r.status_code == 429  # cooldown just after registration
    assert client.post("/api/auth/resend-verification", json={"email": "nobody@example.org"}).status_code == 200  # no account enumeration


def test_first_user_is_admin_and_jwt_claims(client, admin):
    assert admin["user"]["role"] == "ADMIN"
    payload = jwt.decode(admin["access_token"], "test-secret-not-for-production", algorithms=["HS256"])
    assert payload["role"] == "ADMIN" and payload["type"] == "access" and payload["email"] == "admin.user@example.org"
    me = client.get("/api/auth/me", headers=auth(admin))
    assert me.status_code == 200 and me.json()["email"] == "admin.user@example.org"


def test_invalid_and_tampered_tokens(client, admin):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"}).status_code == 401
    forged = jwt.encode({"sub": "1", "role": "ADMIN", "type": "access"}, "wrong-secret", algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_refresh_rotation_and_logout(client, viewer):
    r = client.post("/api/auth/refresh", json={"refresh_token": viewer["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert new["refresh_token"] != viewer["refresh_token"]
    # old refresh token is single-use
    assert client.post("/api/auth/refresh", json={"refresh_token": viewer["refresh_token"]}).status_code == 401
    r = client.post("/api/auth/logout", json={"refresh_token": new["refresh_token"]}, headers=auth(new))
    assert r.status_code == 200
    assert client.post("/api/auth/refresh", json={"refresh_token": new["refresh_token"]}).status_code == 401


def test_role_management_requires_admin(client, admin, viewer):
    assert client.get("/api/users", headers=auth(viewer)).status_code == 403
    users = client.get("/api/users", headers=auth(admin)).json()
    assert any(u["email"] == "viewer.user@example.org" for u in users)
    # admin cannot demote self
    assert client.patch(f"/api/users/{admin['user']['id']}", json={"role": "VIEWER"}, headers=auth(admin)).status_code == 400


def test_public_status_exposes_no_secrets(client):
    s = client.get("/api/system/status").json()
    assert s["data_policy"].startswith("REAL DATA ONLY") and "history_window" in s
    assert "smtp" not in str(s).lower() or "password" not in str(s).lower()
    assert client.get("/api/events").status_code == 401  # everything else needs a login
