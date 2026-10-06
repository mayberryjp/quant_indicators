"""Read daily OHLCV bars from the quant_daily_bars HTTP API.

Bars are produced and owned by the quant_daily_bars service. This service
consumes them over that service's read API instead of querying its database
tables directly, so the two stay decoupled and this service only ever touches
its own `indicators` schema. Set BARS_API_URL to the base URL of the bars API
(default http://localhost:8000).
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests

from quant_indicators.bars.models import Bar, SymbolBars

# The bars API caps /bars at 500 rows per response; page through with this size.
_PAGE_LIMIT = 500
_HTTP_TIMEOUT_SECONDS = 30


def bars_api_url() -> str:
    return os.environ.get("BARS_API_URL", "http://localhost:8000").rstrip("/")


def _get_json(session: requests.Session, path: str, params: dict[str, Any]) -> dict[str, Any]:
    response = session.get(
        f"{bars_api_url()}{path}",
        params=params,
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def list_symbols_with_bars(
    *,
    adjustment_type: str,
    session: requests.Session | None = None,
    tickers: list[str] | None = None,
) -> list[tuple[int, str]]:
    """Return (symbol_id, ticker) pairs that have bars, via the bars API.

    The coverage endpoint reports the full symbol universe regardless of
    `adjustment_type`; symbols lacking bars for the requested series simply
    yield no rows in `load_symbol_bars` and are skipped by the compute job.
    """
    if session is None:
        with requests.Session() as owned_session:
            return list_symbols_with_bars(
                adjustment_type=adjustment_type,
                session=owned_session,
                tickers=tickers,
            )

    payload = _get_json(session, "/bars/coverage", {})
    wanted = set(tickers) if tickers else None
    result: list[tuple[int, str]] = []
    for item in payload.get("items", []):
        ticker = item["ticker"]
        if wanted is not None and ticker not in wanted:
            continue
        result.append((int(item["symbol_id"]), ticker))
    result.sort(key=lambda row: row[1])
    return result


def load_symbol_bars(
    *,
    symbol_id: int,
    ticker: str,
    adjustment_type: str,
    start_date: date | None,
    end_date: date | None,
    session: requests.Session | None = None,
) -> SymbolBars:
    """Load bars for one symbol ordered by date ascending, via the bars API.

    `start_date` should already include any warm-up lookback needed by the
    longest-window indicator so results near the requested window are correct.
    """
    if session is None:
        with requests.Session() as owned_session:
            return load_symbol_bars(
                symbol_id=symbol_id,
                ticker=ticker,
                adjustment_type=adjustment_type,
                start_date=start_date,
                end_date=end_date,
                session=owned_session,
            )

    base_params: dict[str, Any] = {
        "symbol_id": symbol_id,
        "adjustment_type": adjustment_type,
        "from_date": start_date.isoformat() if start_date is not None else None,
        "to_date": end_date.isoformat() if end_date is not None else None,
        "limit": _PAGE_LIMIT,
    }

    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = _get_json(session, "/bars", {**base_params, "offset": offset})
        page_items = page.get("items", [])
        items.extend(page_items)
        if len(page_items) < _PAGE_LIMIT:
            break
        offset += _PAGE_LIMIT

    # The API returns bars newest-first; indicators require oldest-first.
    items.sort(key=lambda item: item["bar_date"])
    bars = [Bar.from_payload(item) for item in items]
    return SymbolBars(symbol_id=symbol_id, ticker=ticker, bars=bars)
