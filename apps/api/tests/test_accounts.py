from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Account, AccountMember, Client
from tests.helpers import PASSWORD, ApiUser


def test_register_creates_account_with_owner_membership(client: TestClient, db) -> None:
    response = client.post(
        "/api/auth/register",
        json={"email": "firma@test.local", "password": PASSWORD, "fullName": " Contadores Pérez "},
    )
    assert response.status_code == 201
    user = response.json()["user"]

    (member,) = db.scalars(select(AccountMember).where(AccountMember.user_id == uuid.UUID(user["id"])))
    account = db.get(Account, member.account_id)
    assert account.name == "Contadores Pérez"
    assert member.role == "Owner"
    assert user["account"] == {"id": str(account.id), "name": "Contadores Pérez", "role": "Owner"}


def test_login_and_refresh_return_the_default_account(client: TestClient, user: ApiUser) -> None:
    email = f"login-{uuid.uuid4().hex}@test.local"
    registered = ApiUser.register(client, email)
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()
    assert login["user"]["account"] == registered.auth["user"]["account"]
    refreshed = client.post("/api/auth/refresh", json={"refreshToken": login["refreshToken"]}).json()
    assert refreshed["user"]["account"]["id"] == registered.auth["user"]["account"]["id"]


def test_clients_belong_to_the_account(user: ApiUser, db) -> None:
    client_id = user.create_client()
    client = db.get(Client, uuid.UUID(client_id))
    assert str(client.account_id) == user.auth["user"]["account"]["id"]


def test_users_of_different_accounts_cannot_see_each_others_clients(
    user: ApiUser, other_user: ApiUser
) -> None:
    client_id, period_id = user.setup_period()

    assert other_user.get("/api/clients").json() == []
    assert other_user.get(f"/api/clients/{client_id}").status_code == 404
    assert other_user.get(f"/api/clients/{client_id}/periods/{period_id}/uploads").status_code == 404
    assert other_user.delete(f"/api/clients/{client_id}").status_code == 404
    assert len(user.get("/api/clients").json()) == 1


def test_foreign_account_header_is_rejected(user: ApiUser, other_user: ApiUser) -> None:
    user.create_client()
    foreign = user.auth["user"]["account"]["id"]
    response = other_user.http.get("/api/clients", headers={**other_user.headers, "X-Account-Id": foreign})
    assert response.status_code == 403
    assert response.json()["title"] == "No tiene acceso a esta cuenta."

    unknown = other_user.http.get(
        "/api/clients", headers={**other_user.headers, "X-Account-Id": str(uuid.uuid4())}
    )
    assert unknown.status_code == 403


def test_malformed_account_header_is_400(user: ApiUser) -> None:
    response = user.http.get("/api/clients", headers={**user.headers, "X-Account-Id": "nope"})
    assert response.status_code == 400
    assert response.json()["errors"] == {"X-Account-Id": ["Identificador inválido."]}


def test_own_account_header_is_accepted(user: ApiUser) -> None:
    user.create_client()
    own = user.auth["user"]["account"]["id"]
    response = user.http.get("/api/clients", headers={**user.headers, "X-Account-Id": own})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_member_of_a_second_account_can_switch_with_the_header(
    user: ApiUser, other_user: ApiUser, db
) -> None:
    shared_client = user.create_client(name="Cliente de la firma")
    firm = uuid.UUID(user.auth["user"]["account"]["id"])
    db.add(AccountMember(account_id=firm, user_id=uuid.UUID(other_user.auth["user"]["id"]), role="Member"))
    db.commit()

    # Without the header the earliest membership (their own account) is used.
    assert other_user.get("/api/clients").json() == []
    headers = {**other_user.headers, "X-Account-Id": str(firm)}
    listed = other_user.http.get("/api/clients", headers=headers).json()
    assert [c["id"] for c in listed] == [shared_client]
    assert other_user.http.get(f"/api/clients/{shared_client}", headers=headers).status_code == 200
