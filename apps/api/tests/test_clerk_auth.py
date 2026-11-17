from __future__ import annotations

import threading
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.models import Account, AccountMember, User
from app.security import ClerkIdentity, ClerkTokenVerifier, InvalidToken
from app.services.accounts import create_personal_account
from app.services.users import provision_user
from tests.clerk import ISSUER, FakeJwksClient, TokenMinter, generate_key, new_sub
from tests.helpers import ApiUser


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _counts(db) -> tuple[int, int, int]:
    db.expire_all()
    return (
        db.scalar(select(func.count()).select_from(User)),
        db.scalar(select(func.count()).select_from(Account)),
        db.scalar(select(func.count()).select_from(AccountMember)),
    )


# --- Provisioning ------------------------------------------------------------------------------


def test_first_request_provisions_user_account_and_owner_membership_once(
    client: TestClient, tokens: TokenMinter, db
) -> None:
    sub = new_sub()
    token = tokens.mint(sub, email="ana@firma.test", name="Ana Pérez")

    first = client.get("/api/me", headers=_bearer(token))
    assert first.status_code == 200
    body = first.json()
    assert set(body) == {"user", "account"}
    assert set(body["user"]) == {"id", "email", "fullName"}
    assert body["user"]["email"] == "ana@firma.test"
    assert body["user"]["fullName"] == "Ana Pérez"
    assert body["account"]["name"] == "Ana Pérez"
    assert body["account"]["role"] == "Owner"

    second = client.get("/api/clients", headers=_bearer(tokens.mint(sub)))
    assert second.status_code == 200
    assert client.get("/api/me", headers=_bearer(token)).json() == body
    assert _counts(db) == (1, 1, 1)

    user = db.scalar(select(User).where(User.clerk_user_id == sub))
    assert str(user.id) == body["user"]["id"]
    member = db.scalar(select(AccountMember).where(AccountMember.user_id == user.id))
    assert (str(member.account_id), member.role) == (body["account"]["id"], "Owner")


def test_distinct_clerk_users_get_distinct_accounts(user: ApiUser, other_user: ApiUser) -> None:
    assert user.id != other_user.id
    assert user.account_id != other_user.account_id


@pytest.mark.parametrize(
    ("claims", "email", "full_name"),
    [
        ({"email": None, "name": None}, None, "Usuario"),
        ({"email": "solo@correo.test", "name": None}, "solo@correo.test", "solo@correo.test"),
        ({"email": "  ", "name": "   "}, None, "Usuario"),
        ({"email": None, "name": "Sin Correo"}, None, "Sin Correo"),
    ],
)
def test_missing_claims_fall_back(
    client: TestClient, tokens: TokenMinter, claims: dict, email: str | None, full_name: str
) -> None:
    me = ApiUser.create(client, tokens, **claims).me
    assert me["user"]["email"] == email
    assert me["user"]["fullName"] == full_name
    assert me["account"]["name"] == full_name


def test_claim_changes_update_the_user_and_missing_claims_keep_values(
    client: TestClient, tokens: TokenMinter, db
) -> None:
    user = ApiUser.create(client, tokens, email="old@test.local", name="Nombre Viejo")

    token = tokens.mint(user.sub, email="new@test.local", name="Nuevo")
    renamed = client.get("/api/me", headers=_bearer(token))
    assert renamed.json()["user"] == {"id": user.id, "email": "new@test.local", "fullName": "Nuevo"}

    without_claims = client.get("/api/me", headers=_bearer(tokens.mint(user.sub, email=None, name=None)))
    assert without_claims.json()["user"] == {"id": user.id, "email": "new@test.local", "fullName": "Nuevo"}

    stored = db.get(User, uuid.UUID(user.id))
    assert (stored.email, stored.full_name) == ("new@test.local", "Nuevo")
    # The account keeps the name it was created with.
    assert renamed.json()["account"]["name"] == "Nombre Viejo"


def test_long_claims_are_truncated_to_the_columns(client: TestClient, tokens: TokenMinter) -> None:
    me = ApiUser.create(client, tokens, name="N" * 500, email="e" * 400).me
    assert len(me["user"]["fullName"]) == 200
    assert len(me["user"]["email"]) == 320


def test_concurrent_first_requests_create_one_user(session_factory, db) -> None:
    identity = ClerkIdentity(clerk_user_id=new_sub(), email="race@test.local", name="Carrera")
    result: dict = {}

    def second_request() -> None:
        with session_factory() as session:
            try:
                result["user_id"] = provision_user(session, identity).id
            except Exception as exc:  # surfaced by the assertions below
                result["error"] = exc

    with session_factory() as first:
        # The first request has inserted the user and account but not committed yet.
        winner = User(clerk_user_id=identity.clerk_user_id, email=identity.email, full_name="Carrera")
        first.add(winner)
        first.flush()
        create_personal_account(first, winner)
        first.flush()

        thread = threading.Thread(target=second_request)
        thread.start()
        thread.join(timeout=1)
        assert thread.is_alive(), "the second insert should wait on the unique clerk_user_id index"
        first.commit()
    thread.join(timeout=10)

    assert "error" not in result, result.get("error")
    assert result["user_id"] == winner.id
    assert _counts(db) == (1, 1, 1)


def test_parallel_first_requests_over_http_create_one_user(
    client: TestClient, tokens: TokenMinter, db
) -> None:
    sub = new_sub()
    barrier = threading.Barrier(6)
    statuses: list[int] = []
    ids: set[str] = set()

    def call() -> None:
        token = tokens.mint(sub)
        barrier.wait()
        response = client.get("/api/me", headers=_bearer(token))
        statuses.append(response.status_code)
        if response.status_code == 200:
            ids.add(response.json()["user"]["id"])

    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert statuses == [200] * 6
    assert len(ids) == 1
    assert _counts(db) == (1, 1, 1)


# --- Rejected tokens ---------------------------------------------------------------------------


def _assert_unauthorized(response) -> None:
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {"title": "No autorizado.", "status": 401}
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_or_malformed_authorization_is_401(client: TestClient, tokens: TokenMinter) -> None:
    _assert_unauthorized(client.get("/api/me"))
    _assert_unauthorized(client.get("/api/clients", headers=_bearer("abc.def.ghi")))
    _assert_unauthorized(client.get("/api/clients", headers={"Authorization": f"Basic {tokens.mint()}"}))
    _assert_unauthorized(client.get("/api/catalogs/renta"))


@pytest.mark.parametrize(
    "case",
    [
        "bad_signature",
        "expired",
        "not_yet_valid",
        "wrong_issuer",
        "wrong_azp",
        "unknown_kid",
        "hs256",
        "no_sub",
        "blank_sub",
        "no_exp",
        "non_string_azp",
    ],
)
def test_invalid_tokens_are_401_and_provision_nothing(
    client: TestClient, tokens: TokenMinter, db, case: str
) -> None:
    token = {
        "bad_signature": lambda: tokens.mint(key=generate_key()),
        "expired": lambda: tokens.mint(expires_in=-120),
        "not_yet_valid": lambda: tokens.mint(nbf=int(time.time()) + 300),
        "wrong_issuer": lambda: tokens.mint(issuer="https://other.clerk.accounts.dev"),
        "wrong_azp": lambda: tokens.mint(azp="https://evil.example.com"),
        "unknown_kid": lambda: tokens.mint(kid="other-kid"),
        "hs256": lambda: tokens.mint(algorithm="HS256"),
        "no_sub": lambda: _without(tokens, "sub"),
        "blank_sub": lambda: tokens.mint(sub="   "),
        "no_exp": lambda: _without(tokens, "exp"),
        "non_string_azp": lambda: tokens.mint(azp=["http://localhost:5173"]),
    }[case]()
    _assert_unauthorized(client.get("/api/me", headers=_bearer(token)))
    assert _counts(db) == (0, 0, 0)


def _without(tokens: TokenMinter, claim: str) -> str:
    claims = jwt.decode(tokens.mint(), options={"verify_signature": False})
    claims.pop(claim)
    return jwt.encode(claims, tokens.key, algorithm="RS256", headers={"kid": tokens.kid})


def test_clock_skew_within_leeway_is_accepted(client: TestClient, tokens: TokenMinter) -> None:
    response = client.get("/api/me", headers=_bearer(tokens.mint(expires_in=-10)))
    assert response.status_code == 200


def test_token_without_azp_is_accepted(client: TestClient, tokens: TokenMinter) -> None:
    assert client.get("/api/me", headers=_bearer(tokens.mint(azp=None))).status_code == 200


# --- Verifier unit tests -----------------------------------------------------------------------


def _verifier(settings: Settings, jwks_client: FakeJwksClient, **overrides) -> ClerkTokenVerifier:
    return ClerkTokenVerifier(settings.model_copy(update=overrides), jwks_client=jwks_client)


def test_authorized_parties_and_vercel_origins(settings, jwks_client, tokens: TokenMinter) -> None:
    verifier = _verifier(settings, jwks_client, clerk_authorized_parties=["https://app.example.com/"])
    for azp in ("https://app.example.com", "HTTPS://APP.EXAMPLE.COM", "https://my-app-git-x.vercel.app"):
        assert verifier.verify(tokens.mint(azp=azp)).clerk_user_id
    for azp in ("http://localhost:5173", "http://my-app.vercel.app", "https://vercel.app.evil.com"):
        with pytest.raises(InvalidToken):
            verifier.verify(tokens.mint(azp=azp))

    no_vercel = _verifier(settings, jwks_client, cors_allow_vercel_subdomains=False)
    with pytest.raises(InvalidToken):
        no_vercel.verify(tokens.mint(azp="https://my-app.vercel.app"))
    assert no_vercel.verify(tokens.mint(azp="http://localhost:3000")).clerk_user_id


def test_verify_returns_identity_claims(settings, jwks_client, tokens: TokenMinter) -> None:
    verifier = _verifier(settings, jwks_client)
    sub = new_sub()
    identity = verifier.verify(tokens.mint(sub, email=" ana@test.local ", name=""))
    assert identity == ClerkIdentity(clerk_user_id=sub, email="ana@test.local", name=None)


def test_jwks_keys_are_cached(settings, jwks_client: FakeJwksClient, tokens: TokenMinter) -> None:
    verifier = _verifier(settings, jwks_client)
    for _ in range(3):
        verifier.verify(tokens.mint())
    assert jwks_client.fetches == 1


def test_clerk_settings_defaults_and_derived_jwks_url() -> None:
    defaults = Settings(_env_file=None)
    assert defaults.clerk_issuer == "https://exciting-gopher-5507.clerk.accounts.dev"
    assert defaults.clerk_jwks_url == "https://exciting-gopher-5507.clerk.accounts.dev/.well-known/jwks.json"
    assert defaults.clerk_authorized_parties == ["http://localhost:3000", "http://localhost:5173"]

    custom = Settings(_env_file=None, clerk_issuer=f"{ISSUER}/")
    assert custom.clerk_issuer == ISSUER
    assert custom.clerk_jwks_url == f"{ISSUER}/.well-known/jwks.json"
    explicit = Settings(_env_file=None, clerk_jwks_url="https://keys.example.com/jwks.json")
    assert explicit.clerk_jwks_url == "https://keys.example.com/jwks.json"


def test_clerk_settings_read_json_list_from_env(monkeypatch) -> None:
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.example.com")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", '["https://app.example.com","https://www.example.com"]')
    settings = Settings(_env_file=None)
    assert settings.clerk_issuer == "https://clerk.example.com"
    assert settings.clerk_authorized_parties == ["https://app.example.com", "https://www.example.com"]


def test_app_without_injected_verifier_does_not_fetch_jwks_on_startup(
    settings, session_factory, storage
) -> None:
    from app.main import create_app

    app = create_app(settings, session_factory=session_factory, storage=storage)
    assert app.state.token_verifier._jwks_client is None


def test_invalid_json_body_is_400(user: ApiUser) -> None:
    headers = {**user.headers, "Content-Type": "application/json"}
    response = user.http.post("/api/clients", content=b"{nope", headers=headers)
    assert response.status_code == 400
