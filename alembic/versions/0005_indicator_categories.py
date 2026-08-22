"""0005 indicator categories lookup table.

Adds indicators.indicator_categories: a static lookup that maps each indicator
base code to exactly one category label (moving_average, trend, momentum,
volatility, volume, level, intraday_range). Seed data is frozen here so the
migration stays self-contained and reproducible.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_indicator_categories"
down_revision: Union[str, None] = "0004_daily_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# One label per indicator base code (frozen snapshot; see registry for codes).
_CATEGORIES: dict[str, str] = {
    # ── moving averages / price overlays ──────────────────────────────
    "sma_10": "moving_average",
    "sma_20": "moving_average",
    "sma_50": "moving_average",
    "sma_100": "moving_average",
    "sma_200": "moving_average",
    "ema_9": "moving_average",
    "ema_12": "moving_average",
    "ema_26": "moving_average",
    "ema_50": "moving_average",
    "ema_200": "moving_average",
    "wma_20": "moving_average",
    "hma_20": "moving_average",
    "dema_20": "moving_average",
    "tema_20": "moving_average",
    "vwma_20": "moving_average",
    # ── trend / directional ───────────────────────────────────────────
    "adx_14": "trend",
    "aroon_25": "trend",
    "vortex_14": "trend",
    "psar": "trend",
    # ── momentum / oscillators ────────────────────────────────────────
    "rsi_14": "momentum",
    "macd": "momentum",
    "stoch_14_3": "momentum",
    "stochrsi_14": "momentum",
    "willr_14": "momentum",
    "cci_20": "momentum",
    "roc_12": "momentum",
    "mom_10": "momentum",
    "cmo_14": "momentum",
    "ppo": "momentum",
    "tsi": "momentum",
    "ao": "momentum",
    "uo": "momentum",
    "trix_15": "momentum",
    "dpo_20": "momentum",
    # ── volatility ────────────────────────────────────────────────────
    "atr_14": "volatility",
    "bbands_20_2": "volatility",
    "keltner_20": "volatility",
    "donchian_20": "volatility",
    "hv_20": "volatility",
    "ulcer_14": "volatility",
    "stddev_20": "volatility",
    # ── volume ────────────────────────────────────────────────────────
    "obv": "volume",
    "adl": "volume",
    "cmf_20": "volume",
    "chaikin_osc": "volume",
    "force_index_13": "volume",
    "eom_14": "volume",
    "pvt": "volume",
    "vol_sma_20": "volume",
    "mfi_14": "volume",
    # ── levels / price structure ──────────────────────────────────────
    "support_resistance_20": "level",
    "support_resistance_50": "level",
    "support_resistance_100": "level",
    "support_resistance_252": "level",
    "pivot_points": "level",
    "pivot_fib": "level",
    "volume_shelf_60": "level",
    # ── intraday range ────────────────────────────────────────────────
    "intraday_open_range_5": "intraday_range",
    "intraday_open_range_20": "intraday_range",
    "intraday_open_range_30": "intraday_range",
    "intraday_open_range_45": "intraday_range",
    "intraday_open_range_60": "intraday_range",
    "intraday_open_range_90": "intraday_range",
    "intraday_open_range_180": "intraday_range",
    "intraday_open_range_365": "intraday_range",
}


def upgrade() -> None:
    op.create_table(
        "indicator_categories",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="indicators",
    )
    op.create_index(
        "ix_indicator_categories_category",
        "indicator_categories",
        ["category"],
        schema="indicators",
    )

    categories_table = sa.table(
        "indicator_categories",
        sa.column("code", sa.Text),
        sa.column("category", sa.Text),
        schema="indicators",
    )
    op.bulk_insert(
        categories_table,
        [{"code": code, "category": category} for code, category in _CATEGORIES.items()],
    )


def downgrade() -> None:
    op.drop_index("ix_indicator_categories_category", table_name="indicator_categories", schema="indicators")
    op.drop_table("indicator_categories", schema="indicators")
