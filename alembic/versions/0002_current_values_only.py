"""0002 current values only

Collapses indicator_values from a historical time series into a current-value
snapshot: exactly one row per (symbol_id, indicator_code, indicator_version,
adjustment_type). `bar_date` is retained as an as-of column (the bar the current
value was computed from) but is no longer part of the uniqueness key.

Existing history is de-duplicated in place, keeping only the most recent
bar_date per group; older rows are dropped. Indicator values are cheaply
regenerable by the next compute run, so this loss of history is intentional.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_current_values_only"
down_revision: Union[str, None] = "0001_indicators_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Keep only the most recent bar_date per group (ties broken by id) so the
    # new unique constraint can be applied without collisions.
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

    op.drop_index("ix_indicator_values_ticker_date", table_name="indicator_values", schema="indicators")
    op.drop_index("ix_indicator_values_code_date", table_name="indicator_values", schema="indicators")
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


def downgrade() -> None:
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

    op.create_index(
        "ix_indicator_values_bar_date",
        "indicator_values",
        ["bar_date"],
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_values_code_date",
        "indicator_values",
        ["indicator_code", "bar_date"],
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_values_ticker_date",
        "indicator_values",
        ["ticker", "bar_date"],
        schema="indicators",
    )
