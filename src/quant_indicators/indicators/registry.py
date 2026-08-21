"""Indicator registry.

Indicators register themselves at import time via `@register`. The compute
job and CLI ask the registry for the enabled set, so the pipeline never needs
to know about individual indicators.
"""

from __future__ import annotations

from typing import Callable, Iterable

from quant_indicators.indicators.base import Indicator

_REGISTRY: dict[str, Indicator] = {}


def register(indicator_cls: type[Indicator]) -> type[Indicator]:
    """Class decorator that instantiates and registers an indicator."""
    instance = indicator_cls()
    if not instance.code:
        raise ValueError(f"{indicator_cls.__name__} must define a non-empty code")
    if instance.code in _REGISTRY:
        raise ValueError(f"duplicate indicator code: {instance.code}")
    _REGISTRY[instance.code] = instance
    return indicator_cls


def all_indicators() -> list[Indicator]:
    """Return every registered indicator, ordered by code."""
    _ensure_loaded()
    return [_REGISTRY[code] for code in sorted(_REGISTRY)]


def get_indicators(codes: Iterable[str] | None = None) -> list[Indicator]:
    """Return the requested indicators (all when codes is None).

    Raises KeyError if any requested code is unknown.
    """
    _ensure_loaded()
    if codes is None:
        return all_indicators()
    selected: list[Indicator] = []
    for code in codes:
        if code not in _REGISTRY:
            raise KeyError(f"unknown indicator code: {code}")
        selected.append(_REGISTRY[code])
    return selected


def get_indicator(code: str) -> Indicator:
    _ensure_loaded()
    return _REGISTRY[code]


_LOADED = False


def _ensure_loaded() -> None:
    """Import indicator modules so their `@register` decorators run once."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    # Importing these modules populates the registry as a side effect.
    from quant_indicators.indicators import (  # noqa: F401
        averages,
        core,
        intraday,
        levels,
        momentum,
        trend,
        volatility,
        volume,
    )


def _reset_for_tests() -> None:
    """Clear registry state (test helper)."""
    global _LOADED
    _REGISTRY.clear()
    _LOADED = False
