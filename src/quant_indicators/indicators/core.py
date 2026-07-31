"""Core price/momentum/volatility indicators.

Implements: SMA (20/50/200), EMA (12/26), RSI(14), MACD(12,26,9),
ATR(14), Bollinger Bands(20,2) and OBV. Each is registered so the compute
job can discover it without any pipeline changes.
"""

from __future__ import annotations

from typing import Sequence

from quant_indicators.bars.models import Bar
from quant_indicators.indicators._math import ema, rolling_std, sma, wilder_rma
from quant_indicators.indicators.base import Indicator, IndicatorPoint
from quant_indicators.indicators.registry import register


# ── Simple Moving Average ────────────────────────────────────────────────────

class _SMA(Indicator):
    window: int = 20
    version = "1"
    input_series = "close"
    outputs: list[str] = []

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        series = sma(closes, self.window)
        return [
            IndicatorPoint(bar_date=bars[i].bar_date, value=series[i])
            for i in range(len(bars))
            if series[i] is not None
        ]


@register
class SMA10(_SMA):
    window = 10
    code = "sma_10"
    display_name = "SMA (10)"
    min_periods = 10
    description = "10-day simple moving average of close."


@register
class SMA20(_SMA):
    window = 20
    code = "sma_20"
    display_name = "SMA (20)"
    min_periods = 20
    description = "20-day simple moving average of close."


@register
class SMA50(_SMA):
    window = 50
    code = "sma_50"
    display_name = "SMA (50)"
    min_periods = 50
    description = "50-day simple moving average of close."


@register
class SMA100(_SMA):
    window = 100
    code = "sma_100"
    display_name = "SMA (100)"
    min_periods = 100
    description = "100-day simple moving average of close."


@register
class SMA200(_SMA):
    window = 200
    code = "sma_200"
    display_name = "SMA (200)"
    min_periods = 200
    description = "200-day simple moving average of close."


# ── Exponential Moving Average ───────────────────────────────────────────────

class _EMA(Indicator):
    window: int = 12
    version = "1"
    input_series = "close"

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        series = ema(closes, self.window)
        return [
            IndicatorPoint(bar_date=bars[i].bar_date, value=series[i])
            for i in range(len(bars))
            if series[i] is not None
        ]


@register
class EMA9(_EMA):
    window = 9
    code = "ema_9"
    display_name = "EMA (9)"
    min_periods = 9
    description = "9-day exponential moving average of close."


@register
class EMA12(_EMA):
    window = 12
    code = "ema_12"
    display_name = "EMA (12)"
    min_periods = 12
    description = "12-day exponential moving average of close."


@register
class EMA26(_EMA):
    window = 26
    code = "ema_26"
    display_name = "EMA (26)"
    min_periods = 26
    description = "26-day exponential moving average of close."


@register
class EMA50(_EMA):
    window = 50
    code = "ema_50"
    display_name = "EMA (50)"
    min_periods = 50
    description = "50-day exponential moving average of close."


@register
class EMA200(_EMA):
    window = 200
    code = "ema_200"
    display_name = "EMA (200)"
    min_periods = 200
    description = "200-day exponential moving average of close."


# ── RSI ──────────────────────────────────────────────────────────────────────

@register
class RSI14(Indicator):
    code = "rsi_14"
    display_name = "RSI (14)"
    version = "1"
    input_series = "close"
    min_periods = 15
    description = "14-day Relative Strength Index (Wilder smoothing)."

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

        # Wilder smoothing over deltas starting at index 1.
        avg_gain = wilder_rma(gains[1:], self.period)
        avg_loss = wilder_rma(losses[1:], self.period)

        points: list[IndicatorPoint] = []
        for j in range(len(avg_gain)):
            g = avg_gain[j]
            loss = avg_loss[j]
            if g is None or loss is None:
                continue
            bar_index = j + 1
            if loss == 0:
                rsi = 100.0
            else:
                rs = g / loss
                rsi = 100.0 - (100.0 / (1.0 + rs))
            points.append(IndicatorPoint(bar_date=bars[bar_index].bar_date, value=rsi))
        return points


# ── MACD ─────────────────────────────────────────────────────────────────────

@register
class MACD(Indicator):
    code = "macd"
    display_name = "MACD (12, 26, 9)"
    version = "1"
    input_series = "close"
    outputs = ["macd", "signal", "histogram"]
    min_periods = 26
    description = "MACD line (EMA12-EMA26), signal (EMA9 of MACD) and histogram."

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

        macd_line: list[float | None] = [None] * n
        for i in range(n):
            if ema_fast[i] is not None and ema_slow[i] is not None:
                macd_line[i] = ema_fast[i] - ema_slow[i]

        defined = [(i, v) for i, v in enumerate(macd_line) if v is not None]
        signal_line: list[float | None] = [None] * n
        if len(defined) >= self.signal_period:
            values = [v for _, v in defined]
            sig = ema(values, self.signal_period)
            for k, (i, _) in enumerate(defined):
                signal_line[i] = sig[k]

        points: list[IndicatorPoint] = []
        for i in range(n):
            if macd_line[i] is None:
                continue
            sig_val = signal_line[i]
            hist = (macd_line[i] - sig_val) if sig_val is not None else None
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={"macd": macd_line[i], "signal": sig_val, "histogram": hist},
                )
            )
        return points


# ── ATR ──────────────────────────────────────────────────────────────────────

@register
class ATR14(Indicator):
    code = "atr_14"
    display_name = "ATR (14)"
    version = "1"
    input_series = "hlc"
    min_periods = 14
    description = "14-day Average True Range (Wilder smoothing)."

    period = 14

    @property
    def params(self) -> dict[str, object]:
        return {"period": self.period}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
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
        series = wilder_rma(true_range, self.period)
        return [
            IndicatorPoint(bar_date=bars[i].bar_date, value=series[i])
            for i in range(n)
            if series[i] is not None
        ]


# ── Bollinger Bands ──────────────────────────────────────────────────────────

@register
class BollingerBands(Indicator):
    code = "bbands_20_2"
    display_name = "Bollinger Bands (20, 2)"
    version = "1"
    input_series = "close"
    outputs = ["middle", "upper", "lower", "bandwidth"]
    min_periods = 20
    description = "20-day SMA with bands at +/- 2 population standard deviations."

    window = 20
    num_std = 2.0

    @property
    def params(self) -> dict[str, object]:
        return {"window": self.window, "num_std": self.num_std}

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        closes = [b.close for b in bars]
        mid = sma(closes, self.window)
        std = rolling_std(closes, self.window)
        points: list[IndicatorPoint] = []
        for i in range(len(bars)):
            if mid[i] is None or std[i] is None:
                continue
            upper = mid[i] + self.num_std * std[i]
            lower = mid[i] - self.num_std * std[i]
            bandwidth = (upper - lower) / mid[i] if mid[i] else None
            points.append(
                IndicatorPoint(
                    bar_date=bars[i].bar_date,
                    values={
                        "middle": mid[i],
                        "upper": upper,
                        "lower": lower,
                        "bandwidth": bandwidth,
                    },
                )
            )
        return points


# ── OBV ──────────────────────────────────────────────────────────────────────

@register
class OBV(Indicator):
    code = "obv"
    display_name = "On-Balance Volume"
    version = "1"
    input_series = "cv"
    min_periods = 1
    description = "Cumulative volume signed by day-over-day close direction."

    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        n = len(bars)
        if n == 0:
            return []
        obv = 0.0
        points = [IndicatorPoint(bar_date=bars[0].bar_date, value=0.0)]
        for i in range(1, n):
            if bars[i].close > bars[i - 1].close:
                obv += bars[i].volume
            elif bars[i].close < bars[i - 1].close:
                obv -= bars[i].volume
            points.append(IndicatorPoint(bar_date=bars[i].bar_date, value=obv))
        return points
