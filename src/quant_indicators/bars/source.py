"""Read daily OHLCV bars from Postgres for indicator computation.

Bars are produced and owned by the quant_daily_bars service and live in
`market_data.daily_bars` by default. The schema/table are configurable via
the BARS_SCHEMA / BARS_TABLE environment variables so this service stays
decoupled from the exact storage location.
"""

from __future__ import annotations

import os
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine

from quant_indicators.bars.models import Bar, SymbolBars


def bars_schema() -> str:
    return os.environ.get("BARS_SCHEMA", "market_data")


def bars_table() -> str:
    return os.environ.get("BARS_TABLE", "daily_bars")


def _qualified_bars_table() -> str:
    return f"{bars_schema()}.{bars_table()}"


def list_symbols_with_bars(
    engine: Engine,
    *,
    adjustment_type: str,
    tickers: list[str] | None = None,
) -> list[tuple[int, str]]:
    """Return (symbol_id, ticker) pairs that have bars for the given series."""
    table = _qualified_bars_table()
    where = ["adjustment_type = :adjustment_type"]
    values: dict[str, object] = {"adjustment_type": adjustment_type}
    if tickers:
        where.append("ticker = ANY(:tickers)")
        values["tickers"] = tickers
    where_clause = " AND ".join(where)

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT symbol_id, ticker
                FROM {table}
                WHERE {where_clause}
                GROUP BY symbol_id, ticker
                ORDER BY ticker
            """),
            values,
        ).fetchall()
    return [(int(r[0]), r[1]) for r in rows]


def load_symbol_bars(
    engine: Engine,
    *,
    symbol_id: int,
    ticker: str,
    adjustment_type: str,
    start_date: date | None,
    end_date: date | None,
) -> SymbolBars:
    """Load bars for one symbol ordered by date ascending.

    `start_date` should already include any warm-up lookback needed by the
    longest-window indicator so results near the requested window are correct.
    """
    table = _qualified_bars_table()
    where = ["symbol_id = :symbol_id", "adjustment_type = :adjustment_type"]
    values: dict[str, object] = {
        "symbol_id": symbol_id,
        "adjustment_type": adjustment_type,
    }
    if start_date is not None:
        where.append("bar_date >= :start_date")
        values["start_date"] = start_date
    if end_date is not None:
        where.append("bar_date <= :end_date")
        values["end_date"] = end_date
    where_clause = " AND ".join(where)

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT bar_date, open, high, low, close, volume, vwap
                FROM {table}
                WHERE {where_clause}
                ORDER BY bar_date ASC
            """),
            values,
        ).mappings().all()

    bars = [Bar.from_row(dict(row)) for row in rows]
    return SymbolBars(symbol_id=symbol_id, ticker=ticker, bars=bars)
