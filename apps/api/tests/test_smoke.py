from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_describes_service(client: TestClient) -> None:
    body = client.get("/").json()
    assert body["status"] == "ok"
    assert body["environment"] == "Testing"


def test_unknown_api_route_returns_problem_details_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 404


def test_malformed_guid_in_route_is_404(user) -> None:
    response = user.get("/api/clients/not-a-guid")
    assert response.status_code == 404


def test_swagger_only_in_development_or_when_enabled(settings, session_factory, storage) -> None:
    hidden = TestClient(create_app(settings, session_factory=session_factory, storage=storage))
    assert hidden.get("/swagger").status_code == 404
    assert hidden.get("/openapi.json").status_code == 404

    enabled = settings.model_copy(update={"enable_swagger": True})
    shown = TestClient(create_app(enabled, session_factory=session_factory, storage=storage))
    assert shown.get("/swagger").status_code == 200
    assert shown.get("/openapi.json").status_code == 200


def test_cors_allows_configured_origins_and_vercel_https(client: TestClient) -> None:
    def preflight(origin: str):
        return client.options(
            "/api/clients",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    allowed = preflight("http://localhost:5173")
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert allowed.headers.get("access-control-allow-credentials") == "true"

    assert preflight("HTTP://LOCALHOST:5173").headers.get("access-control-allow-origin")
    assert preflight("https://my-app-git-main.vercel.app").headers.get("access-control-allow-origin")
    assert preflight("http://my-app.vercel.app").headers.get("access-control-allow-origin") is None
    assert preflight("https://evil.example.com").headers.get("access-control-allow-origin") is None


def test_cors_vercel_can_be_disabled(settings, session_factory, storage) -> None:
    strict = settings.model_copy(update={"cors_allow_vercel_subdomains": False})
    client = TestClient(create_app(strict, session_factory=session_factory, storage=storage))
    response = client.options(
        "/api/clients",
        headers={"Origin": "https://my-app.vercel.app", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers.get("access-control-allow-origin") is None
