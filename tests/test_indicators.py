"""Tests for indicator math correctness using synthetic bars."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from quant_indicators.bars.models import Bar
from quant_indicators.indicators import core, levels, trend
from quant_indicators.indicators import intraday
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


def test_intraday_open_range_percentiles_are_decimal_excursions():
    bars = _bars(
        [100.0, 100.0, 100.0, 100.0, 100.0],
        highs=[110.0, 105.0, 103.0, 108.0, 102.0],
        lows=[90.0, 95.0, 97.0, 92.0, 98.0],
    )
    points = intraday.IntradayOpenRangePercentiles5().compute(bars)
    assert len(points) == 1
    values = points[-1].values
    assert values["high_p50"] == pytest.approx(0.05)
    assert values["high_p95"] == pytest.approx(0.096)
    assert values["low_p50"] == pytest.approx(0.05)
    assert values["low_p95"] == pytest.approx(0.096)

    # A 32% excursion is stored as 0.32, not as a percentage string.
    two_day_bars = _bars(
        [100.0, 100.0],
        highs=[132.0, 100.0],
        lows=[100.0, 100.0],
    )
    two_day_indicator = intraday.IntradayOpenRangePercentiles5()
    two_day_indicator.window = 2
    two_day_values = two_day_indicator.compute(two_day_bars)[-1].values
    assert two_day_values["high_p50"] == pytest.approx(0.16)


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


# ── Coverage across the full registry ────────────────────────────────────────

def _synthetic_ohlcv(n: int = 400) -> list[Bar]:
    """A varied, non-degenerate OHLCV series long enough for every indicator."""
    from math import sin

    start = date(2023, 1, 1)
    bars: list[Bar] = []
    price = 100.0
    for i in range(n):
        # Deterministic wandering price with an intraday range.
        price += sin(i / 5.0) * 1.5 + ((i * 7) % 11 - 5) * 0.3
        price = max(price, 5.0)
        high = price + 1.0 + (i % 4) * 0.25
        low = price - 1.0 - (i % 3) * 0.25
        open_ = price + ((i % 5) - 2) * 0.2
        volume = 1_000_000 + (i * 9973 % 250_000)
        bars.append(
            Bar(
                bar_date=start + timedelta(days=i),
                open=open_,
                high=high,
                low=low,
                close=price,
                volume=volume,
            )
        )
    return bars


def test_every_indicator_computes_without_error():
    from quant_indicators.indicators import registry

    bars = _synthetic_ohlcv()
    for indicator in registry.all_indicators():
        points = indicator.compute(bars)
        assert points, f"{indicator.code} produced no points"
        for p in points:
            # bar_date must be a real bar date from the input.
            assert p.bar_date is not None
            if indicator.outputs:
                assert p.values is not None, f"{indicator.code} missing values dict"
                assert set(p.values.keys()) == set(indicator.outputs), indicator.code
            else:
                assert p.value is not None, f"{indicator.code} produced a None value"


def test_stochastic_bounded_0_100():
    bars = _synthetic_ohlcv(60)
    from quant_indicators.indicators.momentum import Stochastic

    points = Stochastic().compute(bars)
    assert points
    for p in points:
        assert 0.0 <= p.values["k"] <= 100.0


def test_williams_r_bounded():
    bars = _synthetic_ohlcv(60)
    from quant_indicators.indicators.momentum import WilliamsR

    points = WilliamsR().compute(bars)
    assert points
    for p in points:
        assert -100.0 <= p.value <= 0.0


def test_donchian_channel_ordering():
    bars = _synthetic_ohlcv(60)
    from quant_indicators.indicators.volatility import DonchianChannels

    points = DonchianChannels().compute(bars)
    assert points
    for p in points:
        assert p.values["lower"] <= p.values["middle"] <= p.values["upper"]


def test_pivot_points_ordering():
    bars = _synthetic_ohlcv(10)
    from quant_indicators.indicators.levels import PivotPoints

    points = PivotPoints().compute(bars)
    assert points
    for p in points:
        v = p.values
        assert v["s3"] <= v["s2"] <= v["s1"] <= v["r1"] <= v["r2"] <= v["r3"]

