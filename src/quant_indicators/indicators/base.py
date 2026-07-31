"""Pluggable indicator interface and result types.

An indicator consumes an ordered list of daily bars and produces one
`IndicatorPoint` per date it can compute. Indicators are registered in
`registry.py` and discovered by the compute job, so adding a new indicator
means writing a class and registering it — not editing the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from quant_indicators.bars.models import Bar


@dataclass(frozen=True)
class IndicatorPoint:
    """A single computed indicator observation for one bar_date.

    Use `value` for single-output indicators (e.g. SMA) and `values` for
    multi-output indicators (e.g. MACD -> macd/signal/histogram). Exactly one
    of the two is typically populated.
    """

    bar_date: date
    value: float | None = None
    values: dict[str, float] | None = None


@dataclass(frozen=True)
class IndicatorSpec:
    """Static metadata describing an indicator, mirrored to the database."""

    code: str
    display_name: str
    version: str
    input_series: str
    outputs: list[str]
    params: dict[str, object]
    min_periods: int
    description: str


class Indicator(ABC):
    """Base class for all indicators.

    Subclasses declare their identity/params via class attributes and
    implement `compute`. Keep `compute` pure: given the same bars it must
    return the same points (idempotency depends on it).
    """

    #: Stable, unique short code stored on every value row (e.g. "sma_50").
    code: str = ""
    #: Human-friendly name.
    display_name: str = ""
    #: Bump when the math or params change so old/new values can coexist.
    version: str = "1"
    #: Which input series the indicator reads; documentation only.
    input_series: str = "close"
    #: Names of the keys produced in `IndicatorPoint.values` (empty => single).
    outputs: list[str] = []
    #: Minimum number of bars required before the first point is produced.
    min_periods: int = 1
    #: One-line description.
    description: str = ""

    @property
    def params(self) -> dict[str, object]:
        """Parameters that define this indicator instance (for metadata)."""
        return {}

    def spec(self) -> IndicatorSpec:
        return IndicatorSpec(
            code=self.code,
            display_name=self.display_name,
            version=self.version,
            input_series=self.input_series,
            outputs=list(self.outputs),
            params=dict(self.params),
            min_periods=self.min_periods,
            description=self.description,
        )

    @abstractmethod
    def compute(self, bars: Sequence[Bar]) -> list[IndicatorPoint]:
        """Compute points for the given ascending-by-date bars."""
        raise NotImplementedError
