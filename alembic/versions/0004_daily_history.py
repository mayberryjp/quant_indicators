"""0004 daily history with 365-day retention

Restores indicator_values from a single current-value snapshot back into a
daily time series: one row per (symbol_id, bar_date, indicator_code,
indicator_version, adjustment_type). The compute job now stores every day it
can compute (not just the latest point) and prunes rows older than 365
calendar days.

Existing snapshot rows are preserved as-is on upgrade; each becomes the first
historical row for its series at its recorded bar_date. No data is dropped
because the new uniqueness key is a strict superset of the old one.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_daily_history"
down_revision: Union[str, None] = "0003_flatten_output_rows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_indicator_values_code", table_name="indicator_values", schema="indicators")
    op.drop_index("ix_indicator_values_ticker", table_name="indicator_values", schema="indicators")

    op.drop_constraint(
        "uq_indicator_values_symbol_code_ver_adj",
        "indicator_values",
        schema="indicators",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_indicator_values_symbol_date_code_ver_adj",
        "indicator_values",
        ["symbol_id", "bar_date", "indicator_code", "indicator_version", "adjustment_type"],
        schema="indicators",
    )

    # bar_date index backs the retention prune; the composite indexes serve
    # time-series reads by ticker or indicator code.
    op.create_index(
        "ix_indicator_values_bar_date",
        "indicator_values",
        ["bar_date"],
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


def downgrade() -> None:
    # Collapse the time series back into a current-value snapshot: keep only the
    # most recent bar_date per group (ties broken by id) so the narrower unique
    # constraint can be restored without collisions.
    op.execute(
        """
        DELETE FROM indicators.indicator_values a
        USING indicators.indicator_values b
        WHERE a.symbol_id = b.symbol_id
          AND a.indicator_code = b.indicator_code
          AND a.indicator_version = b.indicator_version
          AND a.adjustment_type = b.adjustment_type
          AND (a.bar_date < b.bar_date
               OR (a.bar_date = b.bar_date AND a.id < b.id))
        """
    )

    op.drop_index("ix_indicator_values_code_date", table_name="indicator_values", schema="indicators")
    op.drop_index("ix_indicator_values_ticker_date", table_name="indicator_values", schema="indicators")
    op.drop_index("ix_indicator_values_bar_date", table_name="indicator_values", schema="indicators")

    op.drop_constraint(
        "uq_indicator_values_symbol_date_code_ver_adj",
        "indicator_values",
        schema="indicators",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_indicator_values_symbol_code_ver_adj",
        "indicator_values",
        ["symbol_id", "indicator_code", "indicator_version", "adjustment_type"],
        schema="indicators",
    )

    op.create_index(
        "ix_indicator_values_ticker",
        "indicator_values",
        ["ticker"],
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_values_code",
        "indicator_values",
        ["indicator_code"],
        schema="indicators",
    )
