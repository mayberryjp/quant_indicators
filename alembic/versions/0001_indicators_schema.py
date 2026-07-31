"""0001 indicators schema

Revision ID: 0001_indicators_schema
Revises:
Create Date: 2026-07-31

Creates the indicators schema with tables for:
- indicator_definitions: registered, pluggable indicator metadata
- indicator_runs: per-run tracking for indicator computation jobs
- indicator_values: computed indicator outputs keyed by
  (symbol_id, bar_date, indicator_code, indicator_version, adjustment_type)

Indicator input bars are read from the market_data.daily_bars table owned
by the quant_daily_bars service. That table is a logical dependency and is
not created or dropped here.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_indicators_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS indicators")

    # ── indicator_definitions ───────────────────────────────────────
    # Pluggable indicator metadata. The registry in code is the source of
    # truth; `indicators sync-definitions` (and the compute job) upsert
    # rows here so consumers can discover what is available.
    op.create_table(
        "indicator_definitions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("input_series", sa.Text),
        sa.Column("outputs", sa.JSON),
        sa.Column("params", sa.JSON),
        sa.Column("min_periods", sa.Integer),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="indicators",
    )
    op.create_unique_constraint(
        "uq_indicator_definitions_code_version",
        "indicator_definitions",
        ["code", "version"],
        schema="indicators",
    )

    # ── indicator_runs ──────────────────────────────────────────────
    op.create_table(
        "indicator_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'running'")),
        sa.Column("mode", sa.Text, nullable=False),  # 'backfill' or 'incremental'
        sa.Column("adjustment_type", sa.Text, nullable=False, server_default=sa.text("'unadjusted'")),
        sa.Column("requested_start_date", sa.Date),
        sa.Column("requested_end_date", sa.Date),
        sa.Column("symbols_requested", sa.Integer, server_default=sa.text("0")),
        sa.Column("symbols_succeeded", sa.Integer, server_default=sa.text("0")),
        sa.Column("symbols_failed", sa.Integer, server_default=sa.text("0")),
        sa.Column("indicators_run", sa.Integer, server_default=sa.text("0")),
        sa.Column("values_upserted", sa.Integer, server_default=sa.text("0")),
        sa.Column("errors", sa.Integer, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text),
        sa.Column("duration_seconds", sa.Float),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        schema="indicators",
    )

    # ── indicator_values ────────────────────────────────────────────
    # symbol_id references quant_symbols symbol_master.symbols.id (logical FK).
    # `value` holds single-output indicators (e.g. SMA); `values_json` holds
    # multi-output indicators (e.g. MACD -> macd/signal/histogram).
    op.create_table(
        "indicator_values",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("symbol_id", sa.Integer, nullable=False),
        sa.Column("ticker", sa.Text, nullable=False),
        sa.Column("bar_date", sa.Date, nullable=False),
        sa.Column("indicator_code", sa.Text, nullable=False),
        sa.Column("indicator_version", sa.Text, nullable=False),
        sa.Column("adjustment_type", sa.Text, nullable=False, server_default=sa.text("'unadjusted'")),
        sa.Column("value", sa.Numeric(20, 8)),
        sa.Column("values_json", sa.JSON),
        sa.Column("indicator_run_id", sa.BigInteger, sa.ForeignKey("indicators.indicator_runs.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="indicators",
    )
    # Unique constraint enforces idempotent upserts.
    op.create_unique_constraint(
        "uq_indicator_values_symbol_date_code_ver_adj",
        "indicator_values",
        ["symbol_id", "bar_date", "indicator_code", "indicator_version", "adjustment_type"],
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_values_ticker_date",
        "indicator_values",
        ["ticker", "bar_date"],
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_values_code_date",
        "indicator_values",
        ["indicator_code", "bar_date"],
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_values_bar_date",
        "indicator_values",
        ["bar_date"],
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_values_run_id",
        "indicator_values",
        ["indicator_run_id"],
        schema="indicators",
    )


def downgrade() -> None:
    op.drop_table("indicator_values", schema="indicators")
    op.drop_table("indicator_runs", schema="indicators")
    op.drop_table("indicator_definitions", schema="indicators")
    # Do NOT drop the indicators schema — it holds the Alembic version table
    # and may be shared. It is created with IF NOT EXISTS and is safe to leave.
