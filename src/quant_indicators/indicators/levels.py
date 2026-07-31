"""Level indicators: rolling support/resistance and volume shelves.

These describe price structure rather than a single oscillator value, so they
emit multi-output points (support/resistance, or volume-by-price levels).
"""

from __future__ import annotations

from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


class _SupportResistance(Indicator):
    window: int = 20
    version = "1"
    input_series = "hl"
    outputs = ["support", "resistance", "close_position"]

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        w = self.window
        if n < w:
            return []
        points: list[IndicatorPoint] = []
        for i in range(w - 1, n):
            window_bars = bars[i - w + 1 : i + 1]
            support = min(b.low for b in window_bars)
            resistance = max(b.high for b in window_bars)
            span = resistance - support
            # Where the current close sits within the range (0=support, 1=resistance).
            close_position = (bars[i].close - support) / span if span > 0 else None
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "support": support,
                        "resistance": resistance,
                        "close_position": close_position,
                    },
                )
            )
        return points


@register
class SupportResistance20(_SupportResistance):
    window = 20
    code = "support_resistance_20"
    display_name = "Support/Resistance (20)"
    min_periods = 20
    description = "Rolling 20-day low/high support and resistance levels."


@register
class SupportResistance50(_SupportResistance):
    window = 50
    code = "support_resistance_50"
    display_name = "Support/Resistance (50)"
    min_periods = 50
    description = "Rolling 50-day low/high support and resistance levels."


@register
class SupportResistance100(_SupportResistance):
    window = 100
    code = "support_resistance_100"
    display_name = "Support/Resistance (100)"
    min_periods = 100
    description = "Rolling 100-day low/high support and resistance levels."


@register
class SupportResistance252(_SupportResistance):
    window = 252
    code = "support_resistance_252"
    display_name = "Support/Resistance (252)"
    min_periods = 252
    description = "Rolling 252-day (approx. 1y) low/high support and resistance."


@register
class VolumeShelf(Indicator):
    code = "volume_shelf_60"
    display_name = "Volume Shelf (60, 24 bins)"
    version = "1"
    input_series = "hlcv"
    outputs = ["poc", "value_area_low", "value_area_high", "total_volume"]
    min_periods = 60
    description = (
        "Volume-by-price over a rolling 60-day window: point of control (POC) "
        "and the 70% value area derived from 24 price bins."
    )

    window = 60
    bins = 24
    value_area_pct = 0.70

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window, "bins": self.bins, "value_area_pct": self.value_area_pct}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        w = self.window
        if n < w:
            return []
        points: list[IndicatorPoint] = []
        for i in range(w - 1, n):
            window_bars = bars[i - w + 1 : i + 1]
            low = min(b.low for b in window_bars)
            high = max(b.high for b in window_bars)
            price_span = high - low
            if price_span <= 0:
                continue

            bin_volume = [0.0] * self.bins
            bin_width = price_span / self.bins
            for b in window_bars:
                typical = (b.high + b.low + b.close) / 3.0
                idx = int((typical - low) / bin_width)
                if idx >= self.bins:
                    idx = self.bins - 1
                elif idx < 0:
                    idx = 0
                bin_volume[idx] += b.volume

            total_volume = sum(bin_volume)
            poc_idx = max(range(self.bins), key=lambda k: bin_volume[k])
            poc_price = low + (poc_idx + 0.5) * bin_width

            va_low_idx, va_high_idx = self._value_area(bin_volume, poc_idx, total_volume)
            value_area_low = low + va_low_idx * bin_width
            value_area_high = low + (va_high_idx + 1) * bin_width

            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "poc": poc_price,
                        "value_area_low": value_area_low,
                        "value_area_high": value_area_high,
                        "total_volume": total_volume,
                    },
                )
            )
        return points

    def _value_area(self, bin_volume: list[float], poc_idx: int, total_volume: float) -> tuple[int, int]:
        """Grow outward from the POC until `value_area_pct` of volume is covered."""
        target = total_volume * self.value_area_pct
        covered = bin_volume[poc_idx]
        low_idx = poc_idx
        high_idx = poc_idx
        last = len(bin_volume) - 1
        while covered < target and (low_idx > 0 or high_idx < last):
            below = bin_volume[low_idx - 1] if low_idx > 0 else -1.0
            above = bin_volume[high_idx + 1] if high_idx < last else -1.0
            if above >= below:
                high_idx += 1
                covered += max(above, 0.0)
            else:
                low_idx -= 1
                covered += max(below, 0.0)
        return low_idx, high_idx


# ── Pivot Points ─────────────────────────────────────────────────────────────

@register
class PivotPoints(Indicator):
    code = "pivot_points"
    display_name = "Pivot Points (Classic)"
    version = "1"
    input_series = "hlc"
    outputs = ["pivot", "r1", "r2", "r3", "s1", "s2", "s3"]
    min_periods = 2
    description = "Classic floor-trader pivot, resistance and support levels from the prior bar."

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        points: list[IndicatorPoint] = []
        for i in range(1, len(bars)):
            prev = bars[i - 1]
            high, low, close = prev.high, prev.low, prev.close
            pivot = (high + low + close) / 3.0
            rng = high - low
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "pivot": pivot,
                        "r1": 2.0 * pivot - low,
                        "r2": pivot + rng,
                        "r3": high + 2.0 * (pivot - low),
                        "s1": 2.0 * pivot - high,
                        "s2": pivot - rng,
                        "s3": low - 2.0 * (high - pivot),
                    },
                )
            )
        return points


@register
class FibonacciPivots(Indicator):
    code = "pivot_fib"
    display_name = "Pivot Points (Fibonacci)"
    version = "1"
    input_series = "hlc"
    outputs = ["pivot", "r1", "r2", "r3", "s1", "s2", "s3"]
    min_periods = 2
    description = "Fibonacci pivot levels (0.382/0.618/1.0 of range) from the prior bar."

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        points: list[IndicatorPoint] = []
        for i in range(1, len(bars)):
            prev = bars[i - 1]
            high, low, close = prev.high, prev.low, prev.close
            pivot = (high + low + close) / 3.0
            rng = high - low
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "pivot": pivot,
                        "r1": pivot + 0.382 * rng,
                        "r2": pivot + 0.618 * rng,
                        "r3": pivot + 1.0 * rng,
                        "s1": pivot - 0.382 * rng,
                        "s2": pivot - 0.618 * rng,
                        "s3": pivot - 1.0 * rng,
                    },
                )
            )
        return points
