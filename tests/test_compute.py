"""Tests for the indicator compute job (fixture / dry-run, no database)."""

from __future__ import annotations

from pathlib import Path

from quant_indicators.compute.job import ComputeOptions, IndicatorComputeJob

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bars"


def test_compute_fixture_dry_run_produces_values():
    job = IndicatorComputeJob(engine=None)
    options = ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True)
    summary = job.run(options)

    assert summary.symbols_requested >= 1
    assert summary.symbols_succeeded == summary.symbols_requested
    assert summary.symbols_failed == 0
    assert summary.values_upserted > 0
    assert summary.status == "ok"


def test_compute_fixture_respects_indicator_selection():
    job = IndicatorComputeJob(engine=None)
    options = ComputeOptions(
        fixture_path=str(FIXTURE_DIR),
        dry_run=True,
        indicator_codes=["sma_50"],
    )
    summary = job.run(options)
    assert summary.indicators_run == 1
    assert summary.values_upserted > 0


def test_compute_fixture_date_window_limits_rows():
    job = IndicatorComputeJob(engine=None)
    full = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))

    # Restricting to a single far-future date should yield zero rows.
    from datetime import date

    windowed = job.run(
        ComputeOptions(
            fixture_path=str(FIXTURE_DIR),
            dry_run=True,
            from_date=date(2999, 1, 1),
            to_date=date(2999, 12, 31),
        )
    )
    assert windowed.values_upserted == 0
    assert full.values_upserted > windowed.values_upserted


def test_summary_format_line():
    job = IndicatorComputeJob(engine=None)
    summary = job.run(ComputeOptions(fixture_path=str(FIXTURE_DIR), dry_run=True))
    line = summary.format_line()
    assert "compute_summary" in line
    assert "values_upserted=" in line
