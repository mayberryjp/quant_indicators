"""Volatility and channel indicators.

Keltner Channels, Donchian Channels, historical volatility, the Ulcer Index
and rolling standard deviation of close.
"""

from __future__ import annotations

from math import log, sqrt
from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators._math import ema, highest, lowest, rolling_std
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


def _atr(bars: Sequence[Bar], period: int) -> list[float | None]:
    """Wilder ATR aligned to bars (shared helper)."""
    from quant_indicators.indicators._math import wilder_rma

    n = len(bars)
    if n == 0:
        return []
    true_range = [bars[0].high - bars[0].low]
    for i in range(1, n):
        prev_close = bars[i - 1].close
        true_range.append(
            max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - prev_close),
                abs(bars[i].low - prev_close),
            )
        )
    return wilder_rma(true_range, period)


# ── Keltner Channels ─────────────────────────────────────────────────────────

@register
class KeltnerChannels(Indicator):
    code = "keltner_20"
    display_name = "Keltner Channels (20, 2)"
    version = "1"
    input_series = "hlc"
    outputs = ["middle", "upper", "lower"]
    min_periods = 20
    description = "EMA(20) center with bands at +/- 2 ATR(20)."

    window = 20
    atr_period = 20
    multiplier = 2.0

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window, "atr_period": self.atr_period, "multiplier": self.multiplier}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        closes = [b.close for b in bars]
        middle = ema(closes, self.window)
        atr = _atr(bars, self.atr_period)
        points: list[IndicatorPoint] = []
        for i in range(n):
            if middle[i] is None or atr[i] is None:
                continue
            offset = self.multiplier * atr[i]
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "middle": middle[i],
                        "upper": middle[i] + offset,
                        "lower": middle[i] - offset,
                    },
                )
            )
        return points


# ── Donchian Channels ────────────────────────────────────────────────────────

@register
class DonchianChannels(Indicator):
    code = "donchian_20"
    display_name = "Donchian Channels (20)"
    version = "1"
    input_series = "hl"
    outputs = ["upper", "lower", "middle"]
    min_periods = 20
    description = "20-day highest high / lowest low channel with midline."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        upper = highest(highs, self.window)
        lower = lowest(lows, self.window)
        points: list[IndicatorPoint] = []
        for i in range(n):
            if upper[i] is None or lower[i] is None:
                continue
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "upper": upper[i],
                        "lower": lower[i],
                        "middle": (upper[i] + lower[i]) / 2.0,
                    },
                )
            )
        return points


# ── Historical Volatility ────────────────────────────────────────────────────

@register
class HistoricalVolatility(Indicator):
    code = "hv_20"
    display_name = "Historical Volatility (20)"
    version = "1"
    input_series = "close"
    min_periods = 21
    description = "Annualized 20-day standard deviation of daily log returns (percent)."

    period = 20
    trading_days = 252

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period, "trading_days": self.trading_days}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < self.period + 1:
            return []
        log_returns: list[float | None] = [None]
        for i in range(1, n):
            prev = bars[i - 1].close
            if prev <= 0 or bars[i].close <= 0:
                log_returns.append(None)
            else:
                log_returns.append(log(bars[i].close / prev))
        annual = sqrt(self.trading_days)
        points: list[IndicatorPoint] = []
        for i in range(self.period, n):
            window = log_returns[i - self.period + 1 : i + 1]
            if any(v is None for v in window):
                continue
            mean = sum(window) / self.period
            var = sum((v - mean) ** 2 for v in window) / self.period
            value = sqrt(var) * annual * 100.0
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Ulcer Index ──────────────────────────────────────────────────────────────

@register
class UlcerIndex(Indicator):
    code = "ulcer_14"
    display_name = "Ulcer Index (14)"
    version = "1"
    input_series = "close"
    min_periods = 14
    description = "14-day Ulcer Index: RMS of percentage drawdowns from the rolling high."

    period = 14

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        closes = [b.close for b in bars]
        points: list[IndicatorPoint] = []
        for i in range(self.period - 1, n):
            window = closes[i - self.period + 1 : i + 1]
            sq_sum = 0.0
            for k, close in enumerate(window):
                peak = max(window[: k + 1])
                drawdown = 100.0 * (close - peak) / peak if peak > 0 else 0.0
                sq_sum += drawdown * drawdown
            value = sqrt(sq_sum / self.period)
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Rolling Standard Deviation ───────────────────────────────────────────────

@register
class StdDev20(Indicator):
    code = "stddev_20"
    display_name = "Std Dev (20)"
    version = "1"
    input_series = "close"
    min_periods = 20
    description = "20-day rolling population standard deviation of close."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        series = rolling_std(closes, self.window)
        return [
            IndicatorPoint(bar_date=bars[i].bar_date, value=series[i])
            for i in range(len(bars))
            if series[i] is not None
        ]
