"""Trend-strength indicators: ADX / DI+ / DI-."""

from __future__ import annotations

from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators._math import wilder_rma
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


@register
class ADX14(Indicator):
    code = "adx_14"
    display_name = "ADX (14)"
    version = "1"
    input_series = "hlc"
    outputs = ["adx", "plus_di", "minus_di"]
    min_periods = 28
    description = "Average Directional Index with +DI / -DI (Wilder, period 14)."

    period = 14

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < self.period + 1:
            return []

        plus_dm = [0.0] * n
        minus_dm = [0.0] * n
        true_range = [0.0] * n
        for i in range(1, n):
            up_move = bars[i].high - bars[i - 1].high
            down_move = bars[i - 1].low - bars[i].low
            plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
            prev_close = bars[i - 1].close
            true_range[i] = max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - prev_close),
                abs(bars[i].low - prev_close),
            )

        # Smooth the per-bar directional movement and true range (drop index 0).
        tr_s = wilder_rma(true_range[1:], self.period)
        plus_s = wilder_rma(plus_dm[1:], self.period)
        minus_s = wilder_rma(minus_dm[1:], self.period)

        plus_di: list[float | None] = [None] * n
        minus_di: list[float | None] = [None] * n
        dx: list[float | None] = [None] * n
        for j in range(len(tr_s)):
            tr = tr_s[j]
            if tr is None or tr == 0:
                continue
            bar_index = j + 1
            p = 100.0 * (plus_s[j] / tr) if plus_s[j] is not None else None
            m = 100.0 * (minus_s[j] / tr) if minus_s[j] is not None else None
            plus_di[bar_index] = p
            minus_di[bar_index] = m
            if p is not None and m is not None and (p + m) != 0:
                dx[bar_index] = 100.0 * abs(p - m) / (p + m)

        # ADX is the Wilder average of DX over `period`.
        dx_defined = [(i, v) for i, v in enumerate(dx) if v is not None]
        adx: list[float | None] = [None] * n
        if len(dx_defined) >= self.period:
            values = [v for _, v in dx_defined]
            adx_series = wilder_rma(values, self.period)
            for k, (i, _) in enumerate(dx_defined):
                adx[i] = adx_series[k]

        points: list[IndicatorPoint] = []
        for i in range(n):
            if plus_di[i] is None and minus_di[i] is None and adx[i] is None:
                continue
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "adx": adx[i],
                        "plus_di": plus_di[i],
                        "minus_di": minus_di[i],
                    },
                )
            )
        return points
