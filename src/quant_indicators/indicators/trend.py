"""Trend indicators: ADX/DI, Aroon, Vortex, TRIX, DPO and Parabolic SAR."""

from __future__ import annotations

from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators._math import ema, ema_of, sma, wilder_rma
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


# ── Aroon ────────────────────────────────────────────────────────────────────

@register
class Aroon(Indicator):
    code = "aroon_25"
    display_name = "Aroon (25)"
    version = "1"
    input_series = "hl"
    outputs = ["aroon_up", "aroon_down", "oscillator"]
    min_periods = 26
    description = "Aroon Up/Down and oscillator over a 25-bar lookback."

    period = 25

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        p = self.period
        if n < p + 1:
            return []
        points: list[IndicatorPoint] = []
        for i in range(p, n):
            window = bars[i - p : i + 1]  # p + 1 bars including current
            highs = [b.high for b in window]
            lows = [b.low for b in window]
            # Bars since the most recent extreme (0 = current bar).
            high_idx = max(range(len(window)), key=lambda k: highs[k])
            low_idx = min(range(len(window)), key=lambda k: lows[k])
            since_high = (len(window) - 1) - high_idx
            since_low = (len(window) - 1) - low_idx
            aroon_up = 100.0 * (p - since_high) / p
            aroon_down = 100.0 * (p - since_low) / p
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "aroon_up": aroon_up,
                        "aroon_down": aroon_down,
                        "oscillator": aroon_up - aroon_down,
                    },
                )
            )
        return points


# ── Vortex Indicator ─────────────────────────────────────────────────────────

@register
class Vortex(Indicator):
    code = "vortex_14"
    display_name = "Vortex Indicator (14)"
    version = "1"
    input_series = "hlc"
    outputs = ["plus_vi", "minus_vi"]
    min_periods = 15
    description = "14-day Vortex +VI / -VI trend indicator."

    period = 14

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        p = self.period
        if n < p + 1:
            return []
        plus_vm = [0.0] * n
        minus_vm = [0.0] * n
        true_range = [0.0] * n
        for i in range(1, n):
            plus_vm[i] = abs(bars[i].high - bars[i - 1].low)
            minus_vm[i] = abs(bars[i].low - bars[i - 1].high)
            prev_close = bars[i - 1].close
            true_range[i] = max(
                bars[i].high - bars[i].low,
                abs(bars[i].high - prev_close),
                abs(bars[i].low - prev_close),
            )
        points: list[IndicatorPoint] = []
        for i in range(p, n):
            tr_sum = sum(true_range[i - p + 1 : i + 1])
            if tr_sum <= 0:
                continue
            plus_vi = sum(plus_vm[i - p + 1 : i + 1]) / tr_sum
            minus_vi = sum(minus_vm[i - p + 1 : i + 1]) / tr_sum
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={"plus_vi": plus_vi, "minus_vi": minus_vi},
                )
            )
        return points


# ── TRIX ─────────────────────────────────────────────────────────────────────

@register
class TRIX(Indicator):
    code = "trix_15"
    display_name = "TRIX (15)"
    version = "1"
    input_series = "close"
    min_periods = 46
    description = "1-day percent change of a triple-smoothed EMA(15) of close."

    period = 15

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        closes = [b.close for b in bars]
        ema1 = ema(closes, self.period)
        ema2 = ema_of(ema1, self.period)
        ema3 = ema_of(ema2, self.period)
        points: list[IndicatorPoint] = []
        for i in range(1, n):
            prev = ema3[i - 1]
            cur = ema3[i]
            if prev is None or cur is None or prev == 0:
                continue
            points.append(
                IndicatorPoint(bar_date=bars[i].bar_date, value=100.0 * (cur - prev) / prev)
            )
        return points


# ── Detrended Price Oscillator ───────────────────────────────────────────────

@register
class DPO(Indicator):
    code = "dpo_20"
    display_name = "Detrended Price Oscillator (20)"
    version = "1"
    input_series = "close"
    min_periods = 21
    description = "Close shifted back (period/2 + 1) minus the 20-day SMA."

    period = 20

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        closes = [b.close for b in bars]
        ma = sma(closes, self.period)
        shift = self.period // 2 + 1
        points: list[IndicatorPoint] = []
        for i in range(n):
            if ma[i] is None or i - shift < 0:
                continue
            points.append(
                IndicatorPoint(bar_date=bars[i].bar_date, value=closes[i - shift] - ma[i])
            )
        return points


# ── Parabolic SAR ────────────────────────────────────────────────────────────

@register
class ParabolicSAR(Indicator):
    code = "psar"
    display_name = "Parabolic SAR (0.02, 0.2)"
    version = "1"
    input_series = "hl"
    outputs = ["sar", "trend"]
    min_periods = 2
    description = "Parabolic Stop-and-Reverse with acceleration 0.02 (step) up to 0.2."

    af_start = 0.02
    af_step = 0.02
    af_max = 0.2

    @property
    def params(self) -> dict[str, object]:
        return {"af_start": self.af_start, "af_step": self.af_step, "af_max": self.af_max}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < 2:
            return []
        # Seed trend from the first two bars.
        uptrend = bars[1].close >= bars[0].close
        af = self.af_start
        ep = bars[0].high if uptrend else bars[0].low
        sar = bars[0].low if uptrend else bars[0].high
        points: list[IndicatorPoint] = []
        for i in range(1, n):
            prev_sar = sar
            sar = prev_sar + af * (ep - prev_sar)
            if uptrend:
                # SAR cannot exceed the prior two lows.
                sar = min(sar, bars[i - 1].low, bars[i - 2].low if i >= 2 else bars[i - 1].low)
                if bars[i].low < sar:
                    # Reverse to downtrend.
                    uptrend = False
                    sar = ep
                    ep = bars[i].low
                    af = self.af_start
                else:
                    if bars[i].high > ep:
                        ep = bars[i].high
                        af = min(af + self.af_step, self.af_max)
            else:
                sar = max(sar, bars[i - 1].high, bars[i - 2].high if i >= 2 else bars[i - 1].high)
                if bars[i].high > sar:
                    uptrend = True
                    sar = ep
                    ep = bars[i].high
                    af = self.af_start
                else:
                    if bars[i].low < ep:
                        ep = bars[i].low
                        af = min(af + self.af_step, self.af_max)
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={"sar": sar, "trend": 1.0 if uptrend else -1.0},
                )
            )
        return points
