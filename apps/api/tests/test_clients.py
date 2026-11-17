from __future__ import annotations

from tests.helpers import CLIENT_NIT, ApiUser


def test_create_client_returns_detail_with_base_config(user: ApiUser) -> None:
    response = user.post(
        "/api/clients",
        json={
            "name": " Empresa Demo ",
            "taxId": "0614-010101-101-1",
            "nit": "0614-010101-101-1",
            "nrc": "123456-7",
            "defaultTipoOperacion": "1",
            "defaultTipoIngreso": "3",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/api/clients/{body['id']}"
    assert body["name"] == "Empresa Demo"
    assert body["notes"] is None
    assert body["nit"] == "0614-010101-101-1"
    assert body["nrc"] == "123456-7"
    assert body["defaultTipoOperacion"] == "1"
    assert body["defaultTipoIngreso"] == "3"
    assert body["filingPeriods"] == []
    [config] = body["configurations"]
    assert config["name"] == "Base" and config["isActive"] is True
    assert config["prefillValuesJson"] == "{}"
    assert body["createdAtUtc"].endswith("Z")


def test_create_client_without_new_fields_still_works(user: ApiUser) -> None:
    response = user.post("/api/clients", json={"name": "Legacy", "taxId": "X-1", "notes": "n"})
    assert response.status_code == 201
    assert response.json()["nit"] is None


def test_client_validation(user: ApiUser) -> None:
    bad_nit = user.post("/api/clients", json={"name": "A", "taxId": "1", "nit": "06A4"})
    assert bad_nit.status_code == 400
    assert bad_nit.json()["errors"] == {"nit": ["Solo se permiten dígitos y guiones."]}

    unknown_code = user.post("/api/clients", json={"name": "A", "taxId": "1", "defaultTipoOperacion": "9"})
    assert unknown_code.status_code == 400
    assert unknown_code.json()["errors"] == {
        "defaultTipoOperacion": ["El código no existe en el catálogo de Renta."]
    }

    missing = user.post("/api/clients", json={"name": "  ", "taxId": "1"})
    assert missing.status_code == 400
    assert missing.json()["errors"]["name"] == ["El campo es requerido."]


def test_list_clients_returns_summaries_ordered_by_name(user: ApiUser) -> None:
    b = user.create_client(name="Beta")
    user.create_client(name="Alfa")
    user.create_period(b)
    clients = user.get("/api/clients").json()
    assert [c["name"] for c in clients] == ["Alfa", "Beta"]
    beta = clients[1]
    assert beta["filingPeriodsCount"] == 1
    assert beta["nit"] == CLIENT_NIT
    assert beta["defaultTipoIngreso"] == "3"


def test_update_client_keeps_structured_fields_when_omitted(user: ApiUser) -> None:
    client_id = user.create_client()
    response = user.put(f"/api/clients/{client_id}", json={"name": "Nuevo", "taxId": "T-2", "notes": "x"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Nuevo" and body["notes"] == "x"
    assert body["nit"] == CLIENT_NIT and body["defaultTipoOperacion"] == "1"

    cleared = user.put(
        f"/api/clients/{client_id}",
        json={"name": "Nuevo", "taxId": "T-2", "defaultTipoOperacion": None, "nrc": "99-1"},
    ).json()
    assert cleared["defaultTipoOperacion"] is None
    assert cleared["nrc"] == "99-1"
    assert cleared["notes"] is None


def test_get_and_delete_client(user: ApiUser) -> None:
    client_id = user.create_client()
    user.create_period(client_id, 2026, 2)
    user.create_period(client_id, 2026, 3)
    detail = user.get(f"/api/clients/{client_id}").json()
    assert [(p["year"], p["month"]) for p in detail["filingPeriods"]] == [(2026, 3), (2026, 2)]

    assert user.delete(f"/api/clients/{client_id}").status_code == 204
    assert user.get(f"/api/clients/{client_id}").status_code == 404


def test_other_users_clients_are_404(user: ApiUser, other_user: ApiUser) -> None:
    client_id = user.create_client()
    body = {"name": "X", "taxId": "Y"}
    assert other_user.get(f"/api/clients/{client_id}").status_code == 404
    assert other_user.put(f"/api/clients/{client_id}", json=body).status_code == 404
    assert other_user.delete(f"/api/clients/{client_id}").status_code == 404
    assert other_user.get("/api/clients").json() == []


# --- configs ------------------------------------------------------------------------------------


def test_configs_crud_keeps_a_single_active_config(user: ApiUser) -> None:
    client_id = user.create_client()
    url = f"/api/clients/{client_id}/configs"

    created = user.post(url, json={"name": "Nueva", "prefillValuesJson": '{"a":1}', "isActive": True})
    assert created.status_code == 201
    new_id = created.json()["id"]
    configs = user.get(url).json()
    assert [c["isActive"] for c in configs] == [True, False]
    assert configs[0]["id"] == new_id

    base_id = configs[1]["id"]
    updated = user.put(
        f"{url}/{base_id}", json={"name": "Base 2", "prefillValuesJson": "{}", "isActive": True}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Base 2"
    assert [c["id"] for c in user.get(url).json() if c["isActive"]] == [base_id]

    # Deleting the active config promotes the most recently updated remaining one.
    assert user.delete(f"{url}/{base_id}").status_code == 204
    remaining = user.get(url).json()
    assert len(remaining) == 1 and remaining[0]["isActive"] is True


def test_config_json_must_be_valid(user: ApiUser) -> None:
    client_id = user.create_client()
    response = user.post(
        f"/api/clients/{client_id}/configs", json={"name": "Mala", "prefillValuesJson": "{nope"}
    )
    assert response.status_code == 400
    assert "json" in response.json()["errors"]


def test_configs_of_other_users_are_404(user: ApiUser, other_user: ApiUser) -> None:
    client_id = user.create_client()
    url = f"/api/clients/{client_id}/configs"
    config_id = user.get(url).json()[0]["id"]
    assert other_user.get(url).status_code == 404
    assert other_user.post(url, json={"name": "x"}).status_code == 404
    assert other_user.put(f"{url}/{config_id}", json={"name": "x"}).status_code == 404
    assert other_user.delete(f"{url}/{config_id}").status_code == 404


# --- periods ------------------------------------------------------------------------------------


def test_periods_crud(user: ApiUser) -> None:
    client_id = user.create_client()
    url = f"/api/clients/{client_id}/periods"

    created = user.post(url, json={"year": 2026, "month": 1})
    assert created.status_code == 201
    period = created.json()
    assert period["uploadsCount"] == 0
    assert created.headers["location"] == f"{url}/{period['id']}"

    duplicate = user.post(url, json={"year": 2026, "month": 1})
    assert duplicate.status_code == 400
    assert duplicate.json()["errors"] == {"period": ["El período ya existe para este cliente."]}

    other = user.post(url, json={"year": 2026, "month": 2}).json()
    clash = user.put(f"{url}/{other['id']}", json={"year": 2026, "month": 1})
    assert clash.status_code == 400
    assert clash.json()["errors"] == {"period": ["Ya existe otro período con ese año y mes."]}

    moved = user.put(f"{url}/{other['id']}", json={"year": 2025, "month": 12})
    assert moved.status_code == 200 and moved.json()["month"] == 12

    user.upload(client_id, period["id"])
    listed = user.get(url).json()
    assert [(p["year"], p["month"], p["uploadsCount"]) for p in listed] == [(2026, 1, 1), (2025, 12, 0)]

    assert user.delete(f"{url}/{other['id']}").status_code == 204
    assert len(user.get(url).json()) == 1


def test_period_validation(user: ApiUser) -> None:
    client_id = user.create_client()
    response = user.post(f"/api/clients/{client_id}/periods", json={"year": 1999, "month": 13})
    assert response.status_code == 400
    errors = response.json()["errors"]
    assert errors["year"] == ["El valor debe ser mayor o igual a 2000."]
    assert errors["month"] == ["El valor debe ser menor o igual a 12."]


def test_periods_of_other_users_are_404(user: ApiUser, other_user: ApiUser) -> None:
    client_id, period_id = user.setup_period()
    url = f"/api/clients/{client_id}/periods"
    assert other_user.get(url).status_code == 404
    assert other_user.post(url, json={"year": 2026, "month": 5}).status_code == 404
    assert other_user.put(f"{url}/{period_id}", json={"year": 2026, "month": 5}).status_code == 404
    assert other_user.delete(f"{url}/{period_id}").status_code == 404
