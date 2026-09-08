"""Daily bar input models for indicator computation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Bar:
    """A single daily OHLCV bar used as indicator input.

    Prices are carried as floats for computation. The authoritative values are
    owned by the quant_daily_bars service and fetched over its HTTP API;
    conversion happens once at load time.
    """

    bar_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None

    @classmethod
    def from_payload(cls, item: dict) -> "Bar":
        """Build a Bar from a bars API item or fixture payload."""
        return cls(
            bar_date=date.fromisoformat(item["bar_date"]),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=int(item["volume"]),
            vwap=float(item["vwap"]) if item.get("vwap") is not None else None,
        )


@dataclass(frozen=True)
class SymbolBars:
    """All loaded bars for a single symbol, ordered by bar_date ascending."""

    symbol_id: int
    ticker: str
    bars: list[Bar]
