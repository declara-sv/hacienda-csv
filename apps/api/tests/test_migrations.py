from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text

from app.db import Base


def test_migrations_create_every_table_and_match_the_models(engine: Engine) -> None:
    tables = set(inspect(engine).get_table_names())
    assert {
        "users",
        "refresh_tokens",
        "clients",
        "client_configs",
        "filing_periods",
        "uploads",
        "dte_documents",
        "generation_runs",
        "generation_run_files",
        "output_artifacts",
        "alembic_version",
    } <= tables

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_active_run_partial_unique_index_exists(engine: Engine) -> None:
    with engine.connect() as conn:
        definition = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_generation_runs_active_per_period'")
        ).scalar_one()
    assert "UNIQUE" in definition
    assert "Pending" in definition and "Running" in definition


def test_app_startup_does_not_run_migrations() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    assert "alembic" not in source
