"""Tests for the indicator registry."""

from __future__ import annotations

import pytest

from quant_indicators.indicators import registry


def test_registry_loads_all_indicators():
    indicators = registry.all_indicators()
    codes = {ind.code for ind in indicators}
    expected = {
        "sma_20", "sma_50", "sma_200",
        "ema_12", "ema_26",
        "rsi_14", "macd", "atr_14", "bbands_20_2", "obv",
        "adx_14",
        "support_resistance_20", "support_resistance_252", "volume_shelf_60",
    }
    assert expected.issubset(codes)


def test_registry_codes_are_unique():
    indicators = registry.all_indicators()
    codes = [ind.code for ind in indicators]
    assert len(codes) == len(set(codes))


def test_get_indicators_subset():
    selected = registry.get_indicators(["sma_50", "rsi_14"])
    assert [i.code for i in selected] == ["sma_50", "rsi_14"]


def test_get_indicators_unknown_raises():
    with pytest.raises(KeyError):
        registry.get_indicators(["does_not_exist"])


def test_get_indicators_none_returns_all():
    assert registry.get_indicators(None) == registry.all_indicators()


def test_specs_have_required_metadata():
    for ind in registry.all_indicators():
        spec = ind.spec()
        assert spec.code
        assert spec.display_name
        assert spec.version
        assert spec.min_periods >= 1
