"""enable row level security on every table

Supabase publishes the `public` schema through its Data API, where the public "anon" key can read
any table that has no row-level security. The API connects as the table owner, which bypasses RLS,
so enabling it with no policies shuts out the Data API without affecting the app.

Revision ID: 0002_enable_rls
Revises: b838993f1765
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_enable_rls"
down_revision: str | Sequence[str] | None = "b838993f1765"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "alembic_version",
    "users",
    "accounts",
    "account_members",
    "clients",
    "client_configs",
    "filing_periods",
    "uploads",
    "dte_documents",
    "generation_runs",
    "generation_run_files",
    "output_artifacts",
    "usage_events",
)


def upgrade() -> None:
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    # Views run with their owner's rights by default, which would skip RLS on usage_events.
    op.execute("ALTER VIEW usage_monthly SET (security_invoker = true)")


def downgrade() -> None:
    op.execute("ALTER VIEW usage_monthly SET (security_invoker = false)")
    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
