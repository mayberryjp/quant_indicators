"""Reusable numeric helpers for indicator math (pure Python, no numpy).

All functions return a list aligned 1:1 with the input series, using None for
positions where the value is not yet defined (insufficient lookback).
"""

from __future__ import annotations

from math import sqrt
from typing import Sequence


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """Simple moving average with the given period."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    window_sum = sum(values[0:period])
    out[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """Exponential moving average, seeded with the SMA of the first `period`."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[0:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def wilder_rma(values: Sequence[float], period: int) -> list[float | None]:
    """Wilder's smoothing (RMA), used by RSI, ATR and ADX."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    seed = sum(values[0:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def rolling_std(values: Sequence[float], period: int) -> list[float | None]:
    """Rolling population standard deviation over the given period."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        mean = sum(window) / period
        var = sum((v - mean) ** 2 for v in window) / period
        out[i] = sqrt(var)
    return out


def wma(values: Sequence[float], period: int) -> list[float | None]:
    """Linearly weighted moving average (most recent bar has the highest weight)."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    denom = period * (period + 1) / 2.0
    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        weighted = sum((k + 1) * window[k] for k in range(period))
        out[i] = weighted / denom
    return out


def highest(values: Sequence[float], period: int) -> list[float | None]:
    """Rolling maximum over the given period."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        out[i] = max(values[i - period + 1 : i + 1])
    return out


def lowest(values: Sequence[float], period: int) -> list[float | None]:
    """Rolling minimum over the given period."""
    n = len(values)
    out: list[float | None] = [None] * n
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        out[i] = min(values[i - period + 1 : i + 1])
    return out


def ema_of(series: Sequence[float | None], period: int) -> list[float | None]:
    """EMA of a series that may start with a contiguous run of ``None``.

    Useful for chaining EMAs (DEMA/TEMA/TRIX/PPO signal) where the input is
    itself an indicator output with leading ``None`` padding.
    """
    out: list[float | None] = [None] * len(series)
    defined = [(i, v) for i, v in enumerate(series) if v is not None]
    if len(defined) < period:
        return out
    values = [v for _, v in defined]
    smoothed = ema(values, period)
    for k, (i, _) in enumerate(defined):
        out[i] = smoothed[k]
    return out
