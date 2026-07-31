"""Momentum and oscillator indicators.

Stochastic, Stochastic RSI, Williams %R, CCI, ROC, Momentum, MFI, CMO, PPO,
TSI, Awesome Oscillator and the Ultimate Oscillator. All are pure-Python and
emit None-free points aligned to the bars they are defined for.
"""

from __future__ import annotations

from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators._math import (
    ema,
    ema_of,
    highest,
    lowest,
    sma,
    wilder_rma,
)
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


def _rsi_series(closes: Sequence[float], period: int) -> list[float | None]:
    """RSI aligned to `closes` (None until enough lookback). Shared helper."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains[i] = max(delta, 0.0)
        losses[i] = max(-delta, 0.0)
    avg_gain = wilder_rma(gains[1:], period)
    avg_loss = wilder_rma(losses[1:], period)
    for j in range(len(avg_gain)):
        g = avg_gain[j]
        loss = avg_loss[j]
        if g is None or loss is None:
            continue
        if loss == 0:
            out[j + 1] = 100.0
        else:
            rs = g / loss
            out[j + 1] = 100.0 - (100.0 / (1.0 + rs))
    return out


# ── Stochastic Oscillator ────────────────────────────────────────────────────

@register
class Stochastic(Indicator):
    code = "stoch_14_3"
    display_name = "Stochastic Oscillator (14, 3)"
    version = "1"
    input_series = "hlc"
    outputs = ["k", "d"]
    min_periods = 16
    description = "Fast %K over 14 bars with a 3-bar SMA %D signal line."

    k_period = 14
    d_period = 3

    @property
    def params(self) -> dict[str, object]:
        return {"k_period": self.k_period, "d_period": self.d_period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        hh = highest(highs, self.k_period)
        ll = lowest(lows, self.k_period)
        k_line: list[float | None] = [None] * n
        for i in range(n):
            if hh[i] is None or ll[i] is None:
                continue
            span = hh[i] - ll[i]
            k_line[i] = 100.0 * (bars[i].close - ll[i]) / span if span > 0 else 50.0
        defined = [(i, v) for i, v in enumerate(k_line) if v is not None]
        d_line: list[float | None] = [None] * n
        if len(defined) >= self.d_period:
            d_vals = sma([v for _, v in defined], self.d_period)
            for idx, (i, _) in enumerate(defined):
                d_line[i] = d_vals[idx]
        points: list[IndicatorPoint] = []
        for i in range(n):
            if k_line[i] is None:
                continue
            points.append(
                IndicatorPoint(bar_date=bars[i].bar_date, values={"k": k_line[i], "d": d_line[i]})
            )
        return points


# ── Stochastic RSI ───────────────────────────────────────────────────────────

@register
class StochasticRSI(Indicator):
    code = "stochrsi_14"
    display_name = "Stochastic RSI (14)"
    version = "1"
    input_series = "close"
    outputs = ["stochrsi", "k", "d"]
    min_periods = 32
    description = "Stochastic of the 14-day RSI with 3-bar %K/%D smoothing."

    rsi_period = 14
    stoch_period = 14
    k_period = 3
    d_period = 3

    @property
    def params(self) -> dict[str, object]:
        return {
            "rsi_period": self.rsi_period,
            "stoch_period": self.stoch_period,
            "k_period": self.k_period,
            "d_period": self.d_period,
        }

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        closes = [b.close for b in bars]
        rsi = _rsi_series(closes, self.rsi_period)
        rsi_defined = [(i, v) for i, v in enumerate(rsi) if v is not None]
        if len(rsi_defined) < self.stoch_period:
            return []
        rsi_vals = [v for _, v in rsi_defined]
        hh = highest(rsi_vals, self.stoch_period)
        ll = lowest(rsi_vals, self.stoch_period)
        stoch: list[float | None] = [None] * n
        for idx, (i, _) in enumerate(rsi_defined):
            if hh[idx] is None or ll[idx] is None:
                continue
            span = hh[idx] - ll[idx]
            stoch[i] = 100.0 * (rsi_vals[idx] - ll[idx]) / span if span > 0 else 0.0
        stoch_defined = [(i, v) for i, v in enumerate(stoch) if v is not None]
        k_line: list[float | None] = [None] * n
        if len(stoch_defined) >= self.k_period:
            k_vals = sma([v for _, v in stoch_defined], self.k_period)
            for idx, (i, _) in enumerate(stoch_defined):
                k_line[i] = k_vals[idx]
        k_defined = [(i, v) for i, v in enumerate(k_line) if v is not None]
        d_line: list[float | None] = [None] * n
        if len(k_defined) >= self.d_period:
            d_vals = sma([v for _, v in k_defined], self.d_period)
            for idx, (i, _) in enumerate(k_defined):
                d_line[i] = d_vals[idx]
        points: list[IndicatorPoint] = []
        for i in range(n):
            if stoch[i] is None:
                continue
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={"stochrsi": stoch[i], "k": k_line[i], "d": d_line[i]},
                )
            )
        return points


# ── Williams %R ──────────────────────────────────────────────────────────────

@register
class WilliamsR(Indicator):
    code = "willr_14"
    display_name = "Williams %R (14)"
    version = "1"
    input_series = "hlc"
    min_periods = 14
    description = "14-day Williams %R momentum oscillator (range -100..0)."

    period = 14

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        hh = highest(highs, self.period)
        ll = lowest(lows, self.period)
        points: list[IndicatorPoint] = []
        for i in range(n):
            if hh[i] is None or ll[i] is None:
                continue
            span = hh[i] - ll[i]
            value = -100.0 * (hh[i] - bars[i].close) / span if span > 0 else 0.0
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Commodity Channel Index ──────────────────────────────────────────────────

@register
class CCI(Indicator):
    code = "cci_20"
    display_name = "CCI (20)"
    version = "1"
    input_series = "hlc"
    min_periods = 20
    description = "20-day Commodity Channel Index of typical price."

    period = 20
    constant = 0.015

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period, "constant": self.constant}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        tp = [(b.high + b.low + b.close) / 3.0 for b in bars]
        tp_sma = sma(tp, self.period)
        points: list[IndicatorPoint] = []
        for i in range(self.period - 1, n):
            window = tp[i - self.period + 1 : i + 1]
            mean = tp_sma[i]
            mad = sum(abs(v - mean) for v in window) / self.period
            if mad == 0:
                continue
            value = (tp[i] - mean) / (self.constant * mad)
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Rate of Change ───────────────────────────────────────────────────────────

@register
class ROC(Indicator):
    code = "roc_12"
    display_name = "ROC (12)"
    version = "1"
    input_series = "close"
    min_periods = 13
    description = "12-day rate of change of close (percent)."

    period = 12

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        points: list[IndicatorPoint] = []
        for i in range(self.period, n):
            prev = bars[i - self.period].close
            if prev == 0:
                continue
            value = 100.0 * (bars[i].close - prev) / prev
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Momentum ─────────────────────────────────────────────────────────────────

@register
class Momentum(Indicator):
    code = "mom_10"
    display_name = "Momentum (10)"
    version = "1"
    input_series = "close"
    min_periods = 11
    description = "10-day price momentum (close minus close 10 bars ago)."

    period = 10

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        points: list[IndicatorPoint] = []
        for i in range(self.period, n):
            value = bars[i].close - bars[i - self.period].close
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Money Flow Index ─────────────────────────────────────────────────────────

@register
class MFI(Indicator):
    code = "mfi_14"
    display_name = "Money Flow Index (14)"
    version = "1"
    input_series = "hlcv"
    min_periods = 15
    description = "14-day Money Flow Index (volume-weighted RSI of typical price)."

    period = 14

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < self.period + 1:
            return []
        tp = [(b.high + b.low + b.close) / 3.0 for b in bars]
        raw_flow = [tp[i] * bars[i].volume for i in range(n)]
        pos = [0.0] * n
        neg = [0.0] * n
        for i in range(1, n):
            if tp[i] > tp[i - 1]:
                pos[i] = raw_flow[i]
            elif tp[i] < tp[i - 1]:
                neg[i] = raw_flow[i]
        points: list[IndicatorPoint] = []
        for i in range(self.period, n):
            pos_sum = sum(pos[i - self.period + 1 : i + 1])
            neg_sum = sum(neg[i - self.period + 1 : i + 1])
            if neg_sum == 0:
                value = 100.0
            else:
                ratio = pos_sum / neg_sum
                value = 100.0 - (100.0 / (1.0 + ratio))
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Chande Momentum Oscillator ───────────────────────────────────────────────

@register
class CMO(Indicator):
    code = "cmo_14"
    display_name = "Chande Momentum Oscillator (14)"
    version = "1"
    input_series = "close"
    min_periods = 15
    description = "14-day Chande Momentum Oscillator (range -100..100)."

    period = 14

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < self.period + 1:
            return []
        gains = [0.0] * n
        losses = [0.0] * n
        for i in range(1, n):
            delta = bars[i].close - bars[i - 1].close
            gains[i] = max(delta, 0.0)
            losses[i] = max(-delta, 0.0)
        points: list[IndicatorPoint] = []
        for i in range(self.period, n):
            up = sum(gains[i - self.period + 1 : i + 1])
            down = sum(losses[i - self.period + 1 : i + 1])
            total = up + down
            value = 100.0 * (up - down) / total if total > 0 else 0.0
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Percentage Price Oscillator ──────────────────────────────────────────────

@register
class PPO(Indicator):
    code = "ppo"
    display_name = "PPO (12, 26, 9)"
    version = "1"
    input_series = "close"
    outputs = ["ppo", "signal", "histogram"]
    min_periods = 26
    description = "Percentage Price Oscillator with a 9-day signal line."

    fast = 12
    slow = 26
    signal_period = 9

    @property
    def params(self) -> dict[str, object]:
        return {"fast": self.fast, "slow": self.slow, "signal": self.signal_period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        closes = [b.close for b in bars]
        ema_fast = ema(closes, self.fast)
        ema_slow = ema(closes, self.slow)
        ppo_line: list[float | None] = [None] * n
        for i in range(n):
            if ema_fast[i] is not None and ema_slow[i] is not None and ema_slow[i] != 0:
                ppo_line[i] = 100.0 * (ema_fast[i] - ema_slow[i]) / ema_slow[i]
        signal_line = ema_of(ppo_line, self.signal_period)
        points: list[IndicatorPoint] = []
        for i in range(n):
            if ppo_line[i] is None:
                continue
            sig = signal_line[i]
            hist = (ppo_line[i] - sig) if sig is not None else None
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={"ppo": ppo_line[i], "signal": sig, "histogram": hist},
                )
            )
        return points


# ── True Strength Index ──────────────────────────────────────────────────────

@register
class TSI(Indicator):
    code = "tsi"
    display_name = "True Strength Index (25, 13)"
    version = "1"
    input_series = "close"
    min_periods = 39
    description = "True Strength Index: double-smoothed momentum (25 then 13)."

    long_period = 25
    short_period = 13

    @property
    def params(self) -> dict[str, object]:
        return {"long": self.long_period, "short": self.short_period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < 2:
            return []
        momentum: list[float | None] = [None] * n
        abs_momentum: list[float | None] = [None] * n
        for i in range(1, n):
            change = bars[i].close - bars[i - 1].close
            momentum[i] = change
            abs_momentum[i] = abs(change)
        smooth1 = ema_of(momentum, self.long_period)
        smooth2 = ema_of(smooth1, self.short_period)
        abs_smooth1 = ema_of(abs_momentum, self.long_period)
        abs_smooth2 = ema_of(abs_smooth1, self.short_period)
        points: list[IndicatorPoint] = []
        for i in range(n):
            if smooth2[i] is None or abs_smooth2[i] is None or abs_smooth2[i] == 0:
                continue
            value = 100.0 * smooth2[i] / abs_smooth2[i]
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points


# ── Awesome Oscillator ───────────────────────────────────────────────────────

@register
class AwesomeOscillator(Indicator):
    code = "ao"
    display_name = "Awesome Oscillator (5, 34)"
    version = "1"
    input_series = "hl"
    min_periods = 34
    description = "SMA(5) minus SMA(34) of the median price (high+low)/2."

    fast = 5
    slow = 34

    @property
    def params(self) -> dict[str, object]:
        return {"fast": self.fast, "slow": self.slow}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        median = [(b.high + b.low) / 2.0 for b in bars]
        fast = sma(median, self.fast)
        slow = sma(median, self.slow)
        points: list[IndicatorPoint] = []
        for i in range(n):
            if fast[i] is not None and slow[i] is not None:
                points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=fast[i] - slow[i]))
        return points


# ── Ultimate Oscillator ──────────────────────────────────────────────────────

@register
class UltimateOscillator(Indicator):
    code = "uo"
    display_name = "Ultimate Oscillator (7, 14, 28)"
    version = "1"
    input_series = "hlc"
    min_periods = 29
    description = "Ultimate Oscillator blending buying pressure over 7/14/28 bars."

    short = 7
    medium = 14
    long = 28

    @property
    def params(self) -> dict[str, object]:
        return {"short": self.short, "medium": self.medium, "long": self.long}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n < self.long + 1:
            return []
        bp = [0.0] * n
        tr = [0.0] * n
        for i in range(1, n):
            prev_close = bars[i - 1].close
            true_low = min(bars[i].low, prev_close)
            true_high = max(bars[i].high, prev_close)
            bp[i] = bars[i].close - true_low
            tr[i] = true_high - true_low
        points: list[IndicatorPoint] = []
        for i in range(self.long, n):
            def avg(period: int) -> float | None:
                bp_sum = sum(bp[i - period + 1 : i + 1])
                tr_sum = sum(tr[i - period + 1 : i + 1])
                return bp_sum / tr_sum if tr_sum > 0 else None

            a_short = avg(self.short)
            a_medium = avg(self.medium)
            a_long = avg(self.long)
            if a_short is None or a_medium is None or a_long is None:
                continue
            value = 100.0 * (4.0 * a_short + 2.0 * a_medium + a_long) / 7.0
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=value))
        return points
