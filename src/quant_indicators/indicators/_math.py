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
