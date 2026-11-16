from __future__ import annotations

import datetime as dt

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import RefreshToken
from app.security import hash_refresh_token
from tests.helpers import PASSWORD, ApiUser


def test_register_returns_201_with_token_pair(client: TestClient, settings) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "  Ana@Example.com ", "password": PASSWORD, "fullName": " Ana Pérez "},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"accessToken", "accessTokenExpiresAtUtc", "refreshToken", "user"}
    assert body["user"]["email"] == "Ana@Example.com"
    assert body["user"]["fullName"] == "Ana Pérez"
    assert body["accessTokenExpiresAtUtc"].endswith("Z")

    claims = jwt.decode(
        body["accessToken"],
        settings.jwt_signing_key,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert claims["sub"] == body["user"]["id"]
    assert claims["email"] == "Ana@Example.com"
    expires = dt.datetime.fromisoformat(body["accessTokenExpiresAtUtc"])
    assert abs(expires.timestamp() - claims["exp"]) < 2


def test_register_duplicate_email_is_400_with_field_error(client: TestClient) -> None:
    ApiUser.register(client, "dup@test.local")
    response = client.post(
        "/api/auth/register", json={"email": "DUP@test.local", "password": PASSWORD, "fullName": "X"}
    )
    assert response.status_code == 400
    assert response.json()["errors"] == {"email": ["Este correo ya está registrado."]}


def test_validation_errors_are_400_problem_details_in_spanish(client: TestClient) -> None:
    response = client.post("/api/auth/register", json={"email": "nope", "password": "short"})
    assert response.status_code == 400
    body = response.json()
    assert body["status"] == 400
    assert body["errors"]["email"] == ["El correo electrónico no es válido."]
    assert body["errors"]["password"] == ["Debe tener al menos 8 caracteres."]
    assert body["errors"]["fullName"] == ["El campo es requerido."]


def test_invalid_json_body_is_400(client: TestClient) -> None:
    response = client.post("/api/auth/login", content=b"{nope", headers={"Content-Type": "application/json"})
    assert response.status_code == 400


def test_login_success_and_invalid_credentials(client: TestClient) -> None:
    ApiUser.register(client, "login@test.local")
    ok = client.post("/api/auth/login", json={"email": "LOGIN@test.local", "password": PASSWORD})
    assert ok.status_code == 200
    assert ok.json()["refreshToken"]

    bad = client.post("/api/auth/login", json={"email": "login@test.local", "password": "WrongPass123"})
    assert bad.status_code == 401
    assert bad.json()["title"] == "Credenciales inválidas."

    unknown = client.post("/api/auth/login", json={"email": "ghost@test.local", "password": PASSWORD})
    assert unknown.status_code == 401


def test_refresh_rotates_token_and_rejects_reuse(client: TestClient, db) -> None:
    user = ApiUser.register(client)
    first = user.auth["refreshToken"]

    rotated = client.post("/api/auth/refresh", json={"refreshToken": first})
    assert rotated.status_code == 200
    second = rotated.json()["refreshToken"]
    assert second != first

    reused = client.post("/api/auth/refresh", json={"refreshToken": first})
    assert reused.status_code == 401
    assert reused.json()["title"] == "Refresh token inválido o expirado."

    assert client.post("/api/auth/refresh", json={"refreshToken": second}).status_code == 200

    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(first)))
    assert stored is not None and stored.revoked_at_utc is not None
    assert stored.token_hash != first


def test_expired_refresh_token_is_rejected(client: TestClient, db) -> None:
    user = ApiUser.register(client)
    token = user.auth["refreshToken"]
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(token)))
    stored.expires_at_utc = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    db.commit()
    assert client.post("/api/auth/refresh", json={"refreshToken": token}).status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    user = ApiUser.register(client)
    token = user.auth["refreshToken"]
    response = user.post("/api/auth/logout", json={"refreshToken": token})
    assert response.status_code == 204
    assert client.post("/api/auth/refresh", json={"refreshToken": token}).status_code == 401
    # Unknown or already revoked tokens are a no-op.
    assert client.post("/api/auth/logout", json={"refreshToken": token}).status_code == 204


def test_protected_routes_require_valid_bearer(client: TestClient, settings) -> None:
    missing = client.get("/api/clients")
    assert missing.status_code == 401
    assert missing.json()["status"] == 401

    garbage = client.get("/api/clients", headers={"Authorization": "Bearer abc.def.ghi"})
    assert garbage.status_code == 401

    user = ApiUser.register(client)
    claims = jwt.decode(user.auth["accessToken"], options={"verify_signature": False})
    wrong_audience = jwt.encode({**claims, "aud": "other"}, settings.jwt_signing_key, algorithm="HS256")
    response = client.get("/api/clients", headers={"Authorization": f"Bearer {wrong_audience}"})
    assert response.status_code == 401

    expired = jwt.encode(
        {**claims, "exp": int(dt.datetime.now(dt.UTC).timestamp()) - 120},
        settings.jwt_signing_key,
        algorithm="HS256",
    )
    assert client.get("/api/clients", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    assert user.get("/api/clients").status_code == 200
