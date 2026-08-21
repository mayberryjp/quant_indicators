"""Intraday open-relative range percentile indicators."""

from __future__ import annotations

from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


_PERCENTILES = (0.95, 0.75, 0.50, 0.25)


def _percentile(values: Sequence[float], quantile: float) -> float:
    """Return a linearly interpolated percentile, like NumPy's linear method."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class _IntradayOpenRangePercentiles(Indicator):
    version = "1"
    input_series = "ohl"
    outputs = [
        "high_p95", "high_p75", "high_p50", "high_p25",
        "low_p95", "low_p75", "low_p50", "low_p25",
    ]

    window: int = 5

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window, "percentiles": [95, 75, 50, 25]}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        points: list[IndicatorPoint] = []
        for i in range(self.window - 1, len(bars)):
            window_bars = bars[i - self.window + 1 : i + 1]
            if any(bar.open <= 0 for bar in window_bars):
                continue
            high_moves = [(bar.high - bar.open) / bar.open for bar in window_bars]
            low_moves = [(bar.open - bar.low) / bar.open for bar in window_bars]
            values = {}
            for quantile in _PERCENTILES:
                suffix = f"p{int(quantile * 100)}"
                values[f"high_{suffix}"] = _percentile(high_moves, quantile)
                values[f"low_{suffix}"] = _percentile(low_moves, quantile)
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, values=values))
        return points


def _make_intraday_indicator(window: int, code: str, display_name: str):
    return register(
        type(
            f"IntradayOpenRangePercentiles{window}",
            (_IntradayOpenRangePercentiles,),
            {
                "__module__": __name__,
                "window": window,
                "code": code,
                "display_name": display_name,
                "min_periods": window,
                "description": (
                    f"Trailing {window}-trading-day percentiles of positive "
                    "open-to-high and open-to-low intraday excursions, stored as decimals."
                ),
            },
        )
    )


for _window in (5, 20, 30, 45, 60, 90, 180, 365):
    globals()[f"IntradayOpenRangePercentiles{_window}"] = _make_intraday_indicator(
        _window,
        f"intraday_open_range_{_window}",
        f"Intraday Open Range Percentiles ({_window})",
    )
