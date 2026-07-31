"""Volume-based indicators.

Accumulation/Distribution Line, Chaikin Money Flow, Chaikin Oscillator,
Force Index, Ease of Movement, Price Volume Trend and a volume SMA.
"""

from __future__ import annotations

from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators._math import ema_of, sma
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


def _money_flow_volume(bars: Sequence[Bar]) -> list[float]:
    """Accumulation/distribution money-flow volume per bar."""
    out: list[float] = []
    for b in bars:
        span = b.high - b.low
        if span > 0:
            multiplier = ((b.close - b.low) - (b.high - b.close)) / span
        else:
            multiplier = 0.0
        out.append(multiplier * b.volume)
    return out


# ── Accumulation / Distribution Line ─────────────────────────────────────────

@register
class AccumulationDistribution(Indicator):
    code = "adl"
    display_name = "Accumulation/Distribution Line"
    version = "1"
    input_series = "hlcv"
    min_periods = 1
    description = "Cumulative money-flow volume (Chaikin A/D line)."

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        mfv = _money_flow_volume(bars)
        points: list[IndicatorPoint] = []
        total = 0.0
        for i, b in enumerate(bars):
            total += mfv[i]
            points.append(IndicatorPoint(bar_date=b.bar_date, value=total))
        return points


# ── Chaikin Money Flow ───────────────────────────────────────────────────────

@register
class ChaikinMoneyFlow(Indicator):
    code = "cmf_20"
    display_name = "Chaikin Money Flow (20)"
    version = "1"
    input_series = "hlcv"
    min_periods = 20
    description = "20-day sum of money-flow volume divided by volume."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        w = self.window
        if n < w:
            return []
        mfv = _money_flow_volume(bars)
        points: list[IndicatorPoint] = []
        for i in range(w - 1, n):
            vol_sum = sum(bars[j].volume for j in range(i - w + 1, i + 1))
            if vol_sum <= 0:
                continue
            mfv_sum = sum(mfv[i - w + 1 : i + 1])
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=mfv_sum / vol_sum))
        return points


# ── Chaikin Oscillator ───────────────────────────────────────────────────────

@register
class ChaikinOscillator(Indicator):
    code = "chaikin_osc"
    display_name = "Chaikin Oscillator (3, 10)"
    version = "1"
    input_series = "hlcv"
    min_periods = 10
    description = "EMA(3) minus EMA(10) of the Accumulation/Distribution line."

    fast = 3
    slow = 10

    @property
    def params(self) -> dict[str, object]:
        return {"fast": self.fast, "slow": self.slow}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        mfv = _money_flow_volume(bars)
        adl: list[float] = []
        total = 0.0
        for value in mfv:
            total += value
            adl.append(total)
        ema_fast = ema_of(adl, self.fast)
        ema_slow = ema_of(adl, self.slow)
        points: list[IndicatorPoint] = []
        for i in range(len(bars)):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                points.append(
                    IndicatorPoint(bar_date=bars[i].bar_date, value=ema_fast[i] - ema_slow[i])
                )
        return points


# ── Force Index ──────────────────────────────────────────────────────────────

@register
class ForceIndex(Indicator):
    code = "force_index_13"
    display_name = "Force Index (13)"
    version = "1"
    input_series = "cv"
    min_periods = 14
    description = "13-day EMA of price change times volume."

    period = 13

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < 2:
            return []
        raw: list[float | None] = [None]
        for i in range(1, n):
            raw.append((bars[i].close - bars[i - 1].close) * bars[i].volume)
        smoothed = ema_of(raw, self.period)
        return [
            IndicatorPoint(bar_date=bars[i].bar_date, value=smoothed[i])
            for i in range(n)
            if smoothed[i] is not None
        ]


# ── Ease of Movement ─────────────────────────────────────────────────────────

@register
class EaseOfMovement(Indicator):
    code = "eom_14"
    display_name = "Ease of Movement (14)"
    version = "1"
    input_series = "hlv"
    min_periods = 15
    description = "14-day SMA of single-period Ease of Movement."

    period = 14
    scale = 100_000_000.0

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period, "scale": self.scale}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < 2:
            return []
        emv: list[float | None] = [None]
        for i in range(1, n):
            midpoint_move = (bars[i].high + bars[i].low) / 2.0 - (
                bars[i - 1].high + bars[i - 1].low
            ) / 2.0
            span = bars[i].high - bars[i].low
            if span <= 0 or bars[i].volume <= 0:
                emv.append(0.0)
            else:
                box_ratio = (bars[i].volume / self.scale) / span
                emv.append(midpoint_move / box_ratio if box_ratio != 0 else 0.0)
        defined = [(i, v) for i, v in enumerate(emv) if v is not None]
        points: list[IndicatorPoint] = []
        if len(defined) < self.period:
            return points
        smoothed = sma([v for _, v in defined], self.period)
        for k, (i, _) in enumerate(defined):
            if smoothed[k] is not None:
                points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=smoothed[k]))
        return points


# ── Price Volume Trend ───────────────────────────────────────────────────────

@register
class PriceVolumeTrend(Indicator):
    code = "pvt"
    display_name = "Price Volume Trend"
    version = "1"
    input_series = "cv"
    min_periods = 1
    description = "Cumulative volume weighted by fractional close change."

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n == 0:
            return []
        total = 0.0
        points = [IndicatorPoint(bar_date=bars[0].bar_date, value=0.0)]
        for i in range(1, n):
            prev = bars[i - 1].close
            if prev != 0:
                total += ((bars[i].close - prev) / prev) * bars[i].volume
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=total))
        return points


# ── Volume SMA ───────────────────────────────────────────────────────────────

@register
class VolumeSMA(Indicator):
    code = "vol_sma_20"
    display_name = "Volume SMA (20)"
    version = "1"
    input_series = "volume"
    min_periods = 20
    description = "20-day simple moving average of volume."

    window = 20

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        volumes = [float(b.volume) for b in bars]
        series = sma(volumes, self.window)
        return [
            IndicatorPoint(bar_date=bars[i].bar_date, value=series[i])
            for i in range(len(bars))
            if series[i] is not None
        ]
