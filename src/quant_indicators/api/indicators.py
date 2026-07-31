"""Data access for the retrieval API.

All queries are read-only and parameterized. Rows are returned as plain dicts
ready for JSON serialization; JSON columns are already decoded by the driver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _decode_values(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _row_to_value(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": row["ticker"],
        "symbol_id": row["symbol_id"],
        "bar_date": row["bar_date"].isoformat() if isinstance(row["bar_date"], date) else row["bar_date"],
        "indicator_code": row["indicator_code"],
        "indicator_version": row["indicator_version"],
        "adjustment_type": row["adjustment_type"],
        "value": float(row["value"]) if row.get("value") is not None else None,
    }


def list_indicator_definitions(engine: Engine, *, active_only: bool = True) -> list[dict[str, Any]]:
    clause = "WHERE active = true" if active_only else ""
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT code, version, display_name, active, input_series,
                       outputs, params, min_periods, description
                FROM indicators.indicator_definitions
                {clause}
                ORDER BY code, version
            """)
        ).mappings().all()
    return [
        {
            "code": r["code"],
            "version": r["version"],
            "display_name": r["display_name"],
            "active": r["active"],
            "input_series": r["input_series"],
            "outputs": _decode_values(r["outputs"]),
            "params": _decode_values(r["params"]),
            "min_periods": r["min_periods"],
            "description": r["description"],
        }
        for r in rows
    ]


@dataclass(frozen=True)
class ValuesQuery:
    ticker: str | None = None
    indicator_code: str | None = None
    adjustment_type: str | None = None
    limit: int = 500
    offset: int = 0


def list_indicator_values(engine: Engine, query: ValuesQuery) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}
    if query.ticker:
        conditions.append("ticker = :ticker")
        params["ticker"] = query.ticker.upper()
    if query.indicator_code:
        conditions.append("indicator_code = :indicator_code")
        params["indicator_code"] = query.indicator_code
    if query.adjustment_type:
        conditions.append("adjustment_type = :adjustment_type")
        params["adjustment_type"] = query.adjustment_type

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params["limit"] = max(1, min(query.limit, 5000))
    params["offset"] = max(0, query.offset)

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT symbol_id, ticker, bar_date, indicator_code, indicator_version,
                       adjustment_type, value
                FROM indicators.indicator_values
                {where}
                ORDER BY ticker, indicator_code
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()
    return [_row_to_value(dict(r)) for r in rows]


def latest_values_for_ticker(
    engine: Engine, ticker: str, *, adjustment_type: str | None = None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"ticker": ticker.upper()}
    adj_clause = ""
    if adjustment_type:
        adj_clause = "AND adjustment_type = :adjustment_type"
        params["adjustment_type"] = adjustment_type

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT symbol_id, ticker, bar_date, indicator_code, indicator_version,
                       adjustment_type, value
                FROM indicators.indicator_values
                WHERE ticker = :ticker {adj_clause}
                ORDER BY indicator_code, indicator_version, adjustment_type
            """),
            params,
        ).mappings().all()
    return [_row_to_value(dict(r)) for r in rows]


def coverage(engine: Engine, *, ticker: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    where = ""
    if ticker:
        where = "WHERE ticker = :ticker"
        params["ticker"] = ticker.upper()

    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT ticker, indicator_code,
                       count(*) AS points,
                       min(bar_date) AS first_date,
                       max(bar_date) AS last_date
                FROM indicators.indicator_values
                {where}
                GROUP BY ticker, indicator_code
                ORDER BY ticker, indicator_code
            """),
            params,
        ).mappings().all()
    return [
        {
            "ticker": r["ticker"],
            "indicator_code": r["indicator_code"],
            "points": r["points"],
            "first_date": r["first_date"].isoformat() if r["first_date"] else None,
            "last_date": r["last_date"].isoformat() if r["last_date"] else None,
        }
        for r in rows
    ]


def _run_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    def iso(value: Any) -> Any:
        return value.isoformat() if hasattr(value, "isoformat") else value

    return {
        "id": row["id"],
        "mode": row["mode"],
        "status": row["status"],
        "adjustment_type": row["adjustment_type"],
        "requested_start_date": iso(row.get("requested_start_date")),
        "requested_end_date": iso(row.get("requested_end_date")),
        "symbols_requested": row["symbols_requested"],
        "symbols_succeeded": row["symbols_succeeded"],
        "symbols_failed": row["symbols_failed"],
        "indicators_run": row["indicators_run"],
        "values_upserted": row["values_upserted"],
        "errors": row["errors"],
        "error_message": row.get("error_message"),
        "duration_seconds": float(row["duration_seconds"]) if row.get("duration_seconds") is not None else None,
        "started_at": iso(row.get("started_at")),
        "finished_at": iso(row.get("finished_at")),
    }


_RUN_COLUMNS = """
    id, mode, status, adjustment_type, requested_start_date, requested_end_date,
    symbols_requested, symbols_succeeded, symbols_failed, indicators_run,
    values_upserted, errors, error_message, duration_seconds, started_at, finished_at
"""


def list_runs(engine: Engine, *, limit: int = 50) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"""
                SELECT {_RUN_COLUMNS}
                FROM indicators.indicator_runs
                ORDER BY id DESC
                LIMIT :limit
            """),
            {"limit": max(1, min(limit, 500))},
        ).mappings().all()
    return [_run_to_dict(dict(r)) for r in rows]


def get_run(engine: Engine, run_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"""
                SELECT {_RUN_COLUMNS}
                FROM indicators.indicator_runs
                WHERE id = :run_id
            """),
            {"run_id": run_id},
        ).mappings().first()
    return _run_to_dict(dict(row)) if row is not None else None


def latest_run(engine: Engine) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(f"""
                SELECT {_RUN_COLUMNS}
                FROM indicators.indicator_runs
                ORDER BY id DESC
                LIMIT 1
            """)
        ).mappings().first()
    return _run_to_dict(dict(row)) if row is not None else None
