"""CLI implementation for quant_indicators."""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


EXPECTED_SCHEMA_VERSION = "0003_flatten_output_rows"
EXPECTED_TABLES = (
    "indicator_definitions",
    "indicator_runs",
    "indicator_values",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://quant:quant_dev_password@localhost:5432/quant",
    )


def _alembic_config() -> object:
    from alembic.config import Config

    config = Config(str(_repo_root() / "alembic.ini"))
    config.set_main_option("script_location", str(_repo_root() / "alembic"))
    return config


def _engine() -> object:
    try:
        from sqlalchemy import create_engine
    except ModuleNotFoundError as exc:
        raise SystemExit("SQLAlchemy is required for database commands") from exc
    return create_engine(_database_url(), pool_pre_ping=True)


def _adjustment_type_default() -> str:
    return os.environ.get("INDICATOR_ADJUSTMENT_TYPE", "unadjusted")


def _lookback_default() -> int:
    try:
        return int(os.environ.get("INDICATOR_LOOKBACK_DAYS", "400"))
    except ValueError:
        return 400


def _timezone_default() -> str:
    return os.environ.get("COMPUTE_SCHEDULE_TIMEZONE", "UTC").strip() or "UTC"


def _parse_daily_at(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise SystemExit(f"--daily-at must be HH:MM, got {value!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise SystemExit(f"--daily-at must be HH:MM, got {value!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise SystemExit(f"--daily-at must be HH:MM within 00:00-23:59, got {value!r}")
    return hour, minute


def _load_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"unknown timezone {name!r}") from exc


def _seconds_until(hour: int, minute: int, tz: ZoneInfo) -> tuple[float, datetime]:
    now = datetime.now(tz)
    target = datetime.combine(now.date(), dt_time(hour, minute), tzinfo=tz)
    if target <= now:
        target = datetime.combine(now.date() + timedelta(days=1), dt_time(hour, minute), tzinfo=tz)
    return max((target - now).total_seconds(), 0.0), target


# ── db commands ─────────────────────────────────────────────────────────────

def db_upgrade(_args: argparse.Namespace) -> None:
    from alembic import command
    command.upgrade(_alembic_config(), "head")


def db_downgrade_base(_args: argparse.Namespace) -> None:
    from alembic import command
    command.downgrade(_alembic_config(), "base")


def db_verify(_args: argparse.Namespace) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(_database_url(), pool_pre_ping=True)
    expected_table_names = tuple(sorted(EXPECTED_TABLES))

    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
        schema_version = connection.execute(
            text("SELECT version_num FROM indicators.alembic_version_indicators")
        ).scalar_one()
        tables = connection.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'indicators'
                  AND table_type = 'BASE TABLE'
                  AND table_name != 'alembic_version_indicators'
                ORDER BY table_name
            """)
        ).scalars().all()
        definitions = connection.execute(
            text("SELECT count(*) FROM indicators.indicator_definitions")
        ).scalar_one()

    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise SystemExit(
            f"schema_version={schema_version} expected={EXPECTED_SCHEMA_VERSION}"
        )
    if tuple(tables) != expected_table_names:
        raise SystemExit(f"tables={','.join(tables)} expected={','.join(expected_table_names)}")

    print(
        "postgres=ok "
        f"schema_version={schema_version} "
        f"tables={len(tables)} "
        f"indicator_definitions={definitions}"
    )


# ── indicators commands ─────────────────────────────────────────────────────


def indicators_list(_args: argparse.Namespace) -> None:
    from quant_indicators.indicators.registry import all_indicators

    indicators = all_indicators()
    print(f"registered_indicators={len(indicators)}")
    for indicator in indicators:
        spec = indicator.spec()
        outputs = ",".join(spec.outputs) if spec.outputs else "value"
        print(
            f"  {spec.code:<24} v{spec.version} "
            f"min_periods={spec.min_periods:<4} outputs={outputs:<40} {spec.display_name}"
        )


def indicators_sync_definitions(_args: argparse.Namespace) -> None:
    from quant_indicators.compute.job import IndicatorComputeJob

    job = IndicatorComputeJob(engine=_engine())
    count = job.sync_definitions()
    print(f"sync_definitions  synced={count}")


def _selected_codes(args: argparse.Namespace) -> list[str] | None:
    raw = getattr(args, "indicators", None)
    if not raw:
        return None
    return [c.strip() for c in raw.split(",") if c.strip()]


def indicators_compute(args: argparse.Namespace) -> None:
    from quant_indicators.compute.job import ComputeOptions, IndicatorComputeJob

    interval = getattr(args, "schedule", None)
    daily_at = getattr(args, "daily_at", None)
    if daily_at and interval is not None:
        raise SystemExit("--daily-at and --schedule are mutually exclusive")

    run_once = interval is None and not daily_at
    codes = _selected_codes(args)
    log = logging.getLogger(__name__)

    schedule_hour = schedule_minute = 0
    tz = None
    if daily_at:
        schedule_hour, schedule_minute = _parse_daily_at(daily_at)
        tz = _load_timezone(getattr(args, "timezone", None) or _timezone_default())

    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None

    while True:
        if tz is not None:
            delay, target = _seconds_until(schedule_hour, schedule_minute, tz)
            log.info("next compute at %s (in %d seconds)", target.isoformat(), int(delay))
            time.sleep(delay)

        engine = None if (args.dry_run and args.fixture) else _engine()
        try:
            options = ComputeOptions(
                tickers=tickers,
                adjustment_type=args.adjustment_type,
                indicator_codes=codes,
                lookback_days=args.lookback_days,
                fixture_path=args.fixture,
                dry_run=args.dry_run,
            )

            log.info(
                "computing current indicator values  adjustment=%s  lookback=%dd",
                options.adjustment_type, options.lookback_days,
            )

            job = IndicatorComputeJob(engine=engine)
            try:
                summary = job.run(options)
                print(summary.format_line())
                for w in summary.warnings:
                    print(f"  WARNING: {w}")
                for f in summary.failures[:10]:
                    print(f"  FAILURE: {f}")
                if summary.status == "failed" and run_once:
                    raise SystemExit(1)
            except SystemExit:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"ERROR: {exc}")
                if run_once:
                    raise SystemExit(1) from exc
        finally:
            if engine is not None:
                engine.dispose()

        if run_once:
            break
        if tz is None:
            log.info("next compute in %d seconds", interval)
            time.sleep(interval)


def indicators_run_summary(args: argparse.Namespace) -> None:
    from quant_indicators.compute.job import IndicatorComputeJob

    if not args.latest:
        raise SystemExit("only --latest is currently supported")

    job = IndicatorComputeJob(engine=_engine())
    row = job.latest_run_summary()
    if row is None:
        print("indicator_run_summary=empty")
        return
    print(
        "indicator_run_summary=ok "
        f"run_id={row['id']} "
        f"mode={row['mode']} "
        f"status={row['status']} "
        f"symbols_requested={row['symbols_requested']} "
        f"symbols_succeeded={row['symbols_succeeded']} "
        f"symbols_failed={row['symbols_failed']} "
        f"indicators_run={row['indicators_run']} "
        f"values_upserted={row['values_upserted']} "
        f"errors={row['errors']}"
    )


# ── parser ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m quant_indicators.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # db subcommands
    db_parser = subparsers.add_parser("db")
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)

    upgrade_parser = db_subparsers.add_parser("upgrade")
    upgrade_parser.set_defaults(func=db_upgrade)

    verify_parser = db_subparsers.add_parser("verify")
    verify_parser.set_defaults(func=db_verify)

    downgrade_parser = db_subparsers.add_parser("downgrade-base")
    downgrade_parser.set_defaults(func=db_downgrade_base)

    # indicators subcommands
    ind_parser = subparsers.add_parser("indicators")
    ind_subparsers = ind_parser.add_subparsers(dest="indicators_command", required=True)

    list_parser = ind_subparsers.add_parser("list", help="List registered indicators.")
    list_parser.set_defaults(func=indicators_list)

    sync_parser = ind_subparsers.add_parser(
        "sync-definitions", help="Upsert registry metadata into indicator_definitions."
    )
    sync_parser.set_defaults(func=indicators_sync_definitions)

    compute_parser = ind_subparsers.add_parser(
        "compute", help="Compute and store the current value of each indicator per ticker."
    )
    compute_parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers (default: all with bars).")
    compute_parser.add_argument("--indicators", type=str, default=None, help="Comma-separated indicator codes (default: all registered).")
    compute_parser.add_argument("--adjustment-type", choices=("unadjusted", "split_adjusted"), default=_adjustment_type_default())
    compute_parser.add_argument("--lookback-days", type=int, default=_lookback_default(), help="Recent history (calendar days) loaded per symbol to warm up indicators.")
    compute_parser.add_argument("--fixture", help="Path to a bars fixture file or directory.")
    compute_parser.add_argument("--dry-run", action="store_true", help="Compute without database writes (fixture mode).")
    compute_parser.add_argument("--schedule", type=int, metavar="SECONDS", help="Run continuously, sleeping SECONDS between compute cycles.")
    compute_parser.add_argument("--daily-at", type=str, default=None, metavar="HH:MM", help="Run once per day at this wall-clock time.")
    compute_parser.add_argument("--timezone", type=str, default=_timezone_default(), metavar="TZ", help="IANA timezone for --daily-at (default: COMPUTE_SCHEDULE_TIMEZONE or UTC).")
    compute_parser.set_defaults(func=indicators_compute)

    run_summary_parser = ind_subparsers.add_parser("run-summary")
    run_summary_parser.add_argument("--latest", action="store_true", required=True)
    run_summary_parser.set_defaults(func=indicators_run_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0
