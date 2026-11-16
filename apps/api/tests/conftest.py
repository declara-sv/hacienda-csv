"""Shared fixtures. Tests run against a dedicated Postgres database (TEST_DATABASE_URL).

The schema is rebuilt from the Alembic migrations once per session and every table is truncated
before each test. The extraction/anexos modules are replaced with deterministic fakes unless a test
is marked `real_integrations`.
"""

from __future__ import annotations

import os

from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@127.0.0.1:54329/hacienda_test"
)
if not (make_url(TEST_DATABASE_URL).database or "").endswith("_test"):
    raise RuntimeError(f"TEST_DATABASE_URL debe apuntar a una base *_test, no a {TEST_DATABASE_URL!r}.")

# Before anything reads settings: never point at another database or a real API key.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["WORKER_ENABLED"] = "false"

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.storage import LocalFileStorage  # noqa: E402
from tests import fakes  # noqa: E402
from tests.helpers import ApiUser  # noqa: E402

API_ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_integrations: use the real app.extraction / app.anexos modules")


def run_migrations(url: str) -> None:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    run_migrations(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_db(engine: Engine) -> Engine:
    """Truncate every table. Requested through `session_factory`, so pure unit tests skip the DB."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return engine


@pytest.fixture(autouse=True)
def _fake_integrations(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if request.node.get_closest_marker("real_integrations") is None:
        fakes.install(monkeypatch)


@pytest.fixture
def session_factory(clean_db: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=clean_db, expire_on_commit=False)


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    return tmp_path / "files"


@pytest.fixture
def settings(storage_root: Path) -> Settings:
    return Settings(
        environment="Testing",
        database_url=TEST_DATABASE_URL,
        storage_provider="Local",
        storage_local_root_path=str(storage_root),
        worker_enabled=False,
        anthropic_api_key="",
        ai_extraction_enabled=False,
        _env_file=None,
    )


@pytest.fixture
def storage(storage_root: Path) -> LocalFileStorage:
    return LocalFileStorage(storage_root)


@pytest.fixture
def app(settings: Settings, session_factory: sessionmaker[Session], storage: LocalFileStorage):
    return create_app(settings, session_factory=session_factory, storage=storage)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user(client: TestClient) -> ApiUser:
    return ApiUser.register(client)


@pytest.fixture
def other_user(client: TestClient) -> ApiUser:
    return ApiUser.register(client)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session
