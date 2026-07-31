"""Extended moving-average family: WMA, HMA, DEMA, TEMA and VWMA.

These complement the simple/exponential averages in ``core`` with weighted
and adaptive smoothers commonly used for trend following.
"""

from __future__ import annotations

from math import sqrt
from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators._math import ema, ema_of, wma
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


# ── Weighted Moving Average ──────────────────────────────────────────────────

@register
class WMA20(Indicator):
    code = "wma_20"
    display_name = "WMA (20)"
    version = "1"
    input_series = "close"
    min_periods = 20
    description = "20-day linearly weighted moving average of close."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        series = wma(closes, self.window)
        return [
            IndicatorPoint(bar_date=bars[i].bar_date, value=series[i])
            for i in range(len(bars))
            if series[i] is not None
        ]


# ── Hull Moving Average ──────────────────────────────────────────────────────

@register
class HMA20(Indicator):
    code = "hma_20"
    display_name = "HMA (20)"
    version = "1"
    input_series = "close"
    min_periods = 23  # window + ceil(sqrt(window)) - 1
    description = "20-day Hull moving average (fast, low-lag WMA blend)."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        half = max(1, self.window // 2)
        sqrt_len = max(1, int(round(sqrt(self.window))))
        wma_half = wma(closes, half)
        wma_full = wma(closes, self.window)
        raw: list[float | None] = [None] * len(closes)
        for i in range(len(closes)):
            if wma_half[i] is not None and wma_full[i] is not None:
                raw[i] = 2.0 * wma_half[i] - wma_full[i]
        # WMA over the raw series (skip its leading None prefix).
        defined = [(i, v) for i, v in enumerate(raw) if v is not None]
        points: list[IndicatorPoint] = []
        if len(defined) < sqrt_len:
            return points
        smoothed = wma([v for _, v in defined], sqrt_len)
        for k, (i, _) in enumerate(defined):
            if smoothed[k] is not None:
                points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=smoothed[k]))
        return points


# ── Double / Triple EMA ──────────────────────────────────────────────────────

@register
class DEMA20(Indicator):
    code = "dema_20"
    display_name = "DEMA (20)"
    version = "1"
    input_series = "close"
    min_periods = 39
    description = "20-day double exponential moving average (2*EMA - EMA(EMA))."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        ema1 = ema(closes, self.window)
        ema2 = ema_of(ema1, self.window)
        points: list[IndicatorPoint] = []
        for i in range(len(bars)):
            if ema1[i] is not None and ema2[i] is not None:
                points.append(
                    IndicatorPoint(bar_date=bars[i].bar_date, value=2.0 * ema1[i] - ema2[i])
                )
        return points


@register
class TEMA20(Indicator):
    code = "tema_20"
    display_name = "TEMA (20)"
    version = "1"
    input_series = "close"
    min_periods = 58
    description = "20-day triple exponential moving average (3*EMA - 3*EMA2 + EMA3)."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        ema1 = ema(closes, self.window)
        ema2 = ema_of(ema1, self.window)
        ema3 = ema_of(ema2, self.window)
        points: list[IndicatorPoint] = []
        for i in range(len(bars)):
            if ema1[i] is not None and ema2[i] is not None and ema3[i] is not None:
                value = 3.0 * ema1[i] - 3.0 * ema2[i] + ema3[i]
                points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Volume-Weighted Moving Average ───────────────────────────────────────────

@register
class VWMA20(Indicator):
    code = "vwma_20"
    display_name = "VWMA (20)"
    version = "1"
    input_series = "cv"
    min_periods = 20
    description = "20-day volume-weighted moving average of close."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        w = self.window
        points: list[IndicatorPoint] = []
        if n < w:
            return points
        for i in range(w - 1, n):
            window_bars = bars[i - w + 1 : i + 1]
            vol_sum = sum(b.volume for b in window_bars)
            if vol_sum <= 0:
                continue
            pv = sum(b.close * b.volume for b in window_bars)
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=pv / vol_sum))
        return points
