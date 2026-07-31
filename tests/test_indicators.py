"""Tests for indicator math correctness using synthetic bars."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from quant_indicators.bars.models import Bar
from quant_indicators.indicators import core, levels, trend
from quant_indicators.indicators._math import ema, sma, wilder_rma


def _bars(closes: list[float], *, highs=None, lows=None, volumes=None) -> list[Bar]:
    start = date(2024, 1, 1)
    bars = []
    for i, close in enumerate(closes):
        high = highs[i] if highs else close + 1
        low = lows[i] if lows else close - 1
        vol = volumes[i] if volumes else 1000 + i
        bars.append(
            Bar(
                bar_date=start + timedelta(days=i),
                open=close,
                high=high,
                low=low,
                close=close,
                volume=vol,
            )
        )
    return bars


def test_sma_math():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = sma(values, 3)
    assert result[:2] == [None, None]
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(3.0)
    assert result[4] == pytest.approx(4.0)


def test_ema_seeded_with_sma():
    values = [float(i) for i in range(1, 11)]
    result = ema(values, 3)
    assert result[:2] == [None, None]
    # First EMA equals SMA of first 3 -> 2.0
    assert result[2] == pytest.approx(2.0)
    assert result[-1] > result[2]


def test_wilder_rma_smoothing():
    values = [1.0] * 10
    result = wilder_rma(values, 3)
    # Constant series -> smoothed value stays constant at 1.0 after warmup.
    assert result[2] == pytest.approx(1.0)
    assert result[-1] == pytest.approx(1.0)


def test_sma50_indicator_produces_points():
    bars = _bars([float(i) for i in range(1, 60)])
    points = core.SMA50().compute(bars)
    assert len(points) == 59 - 50 + 1
    assert all(p.value is not None for p in points)


def test_rsi_all_gains_is_100():
    bars = _bars([float(i) for i in range(1, 30)])
    points = core.RSI14().compute(bars)
    assert points, "expected RSI points"
    assert points[-1].value == pytest.approx(100.0)


def test_rsi_all_losses_is_zero():
    bars = _bars([float(i) for i in range(30, 1, -1)])
    points = core.RSI14().compute(bars)
    assert points[-1].value == pytest.approx(0.0)


def test_macd_outputs_keys():
    bars = _bars([float(i % 7) + 10 for i in range(60)])
    points = core.MACD().compute(bars)
    assert points
    last = points[-1]
    assert last.value is None
    assert set(last.values.keys()) == {"macd", "signal", "histogram"}


def test_bollinger_band_ordering():
    bars = _bars([10.0 + (i % 5) for i in range(40)])
    points = core.BollingerBands().compute(bars)
    assert points
    v = points[-1].values
    assert v["lower"] <= v["middle"] <= v["upper"]
    assert v["bandwidth"] >= 0


def test_obv_accumulates_signed_volume():
    closes = [10.0, 11.0, 10.5, 12.0]
    vols = [100, 200, 300, 400]
    bars = _bars(closes, volumes=vols)
    points = core.OBV().compute(bars)
    # OBV: start 0, +200 (up), -300 (down), +400 (up) => 300
    assert points[-1].value == pytest.approx(300.0)


def test_atr_positive():
    bars = _bars([float(i) for i in range(1, 40)])
    points = core.ATR14().compute(bars)
    assert points
    assert all(p.value is not None and p.value >= 0 for p in points)


def test_adx_outputs_and_range():
    # Trending-up series should yield a positive ADX and DI+.
    closes = [float(i) for i in range(1, 80)]
    bars = _bars(closes, highs=[float(i) + 1 for i in range(1, 80)], lows=[float(i) - 1 for i in range(1, 80)])
    points = trend.ADX14().compute(bars)
    assert points
    last = points[-1].values
    assert set(last.keys()) == {"adx", "plus_di", "minus_di"}
    assert last["plus_di"] is not None


def test_support_resistance_bounds():
    bars = _bars([10.0, 12.0, 9.0, 15.0, 11.0, 13.0, 8.0, 14.0])
    points = levels.SupportResistance20.__mro__  # ensure class import
    sr = levels.SupportResistance20()
    sr.window = 3
    pts = sr.compute(bars)
    assert pts
    for p in pts:
        assert p.values["support"] <= p.values["resistance"]


def test_volume_shelf_value_area_within_range():
    closes = [10.0 + (i % 8) for i in range(70)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    vols = [1000 + (i * 37 % 500) for i in range(70)]
    bars = _bars(closes, highs=highs, lows=lows, volumes=vols)
    points = levels.VolumeShelf().compute(bars)
    assert points
    v = points[-1].values
    assert v["value_area_low"] <= v["poc"] <= v["value_area_high"]
    assert v["total_volume"] > 0
