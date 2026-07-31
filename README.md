# quant_indicators

Daily technical-indicator pipeline for Alpaca bars. It reads OHLCV daily bars
produced by [`quant_daily_bars`](https://github.com/mayberryjp/quant_daily_bars)
from Postgres, computes a pluggable set of technical indicators for every
ticker, stores them idempotently, and exposes a read-only HTTP API to retrieve
them.

## Architecture

```
market_data.daily_bars ──▶ compute job ──▶ indicators.indicator_values ──▶ retrieval API
   (owned by                (registry of                (this service's           (Bottle + waitress)
    quant_daily_bars)        indicators)                 own schema)
```

The service runs in a single container orchestrated by `supervisord`:

| Program                 | Responsibility                                            |
| ----------------------- | --------------------------------------------------------- |
| `db-migrate`            | `alembic upgrade head` on startup (one-shot).             |
| `indicators-compute`    | Recompute indicators on a schedule (`COMPUTE_INTERVAL`).  |
| `quant-indicators-api`  | Serve the retrieval API (`API_PORT`, default 8001).       |

## Schema

All state lives in a dedicated `indicators` Postgres schema with its own Alembic
version table (`indicators.alembic_version_indicators`), so it never collides
with the `market_data` schema owned by `quant_daily_bars`.

- `indicator_definitions` — registry metadata (code, version, outputs, params).
- `indicator_runs` — one row per compute run, with heartbeat and counts.
- `indicator_values` — computed values, unique per
  `(symbol_id, bar_date, indicator_code, indicator_version, adjustment_type)`.

Single-output indicators (e.g. SMA) write the `value` column; multi-output
indicators (e.g. MACD) write a JSON object to `values_json`.

## Indicators

Indicators are pluggable: subclass `Indicator`, decorate with `@register`, and
the compute job and CLI pick them up automatically — no pipeline changes.

| Code                       | Description                                             |
| -------------------------- | ------------------------------------------------------ |
| `sma_20` / `sma_50` / `sma_200` | Simple moving averages                            |
| `ema_12` / `ema_26`        | Exponential moving averages (SMA-seeded)               |
| `rsi_14`                   | Relative Strength Index (Wilder)                       |
| `macd`                     | MACD line / signal / histogram                         |
| `atr_14`                   | Average True Range                                     |
| `bbands_20_2`              | Bollinger Bands (middle/upper/lower/bandwidth)         |
| `obv`                      | On-Balance Volume                                      |
| `adx_14`                   | ADX with +DI / -DI                                     |
| `support_resistance_20` / `support_resistance_252` | Rolling low/high levels        |
| `volume_shelf_60`          | Volume-by-price POC and 70% value area                 |

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

This starts Postgres, runs migrations, computes indicators, and serves the API
on `http://localhost:8001`.

## Local development

```bash
python -m venv .venv
.venv/Scripts/activate        # or: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Tests run without a database or network — indicator math, the registry, the
compute job (fixture / dry-run mode), the CLI, and the API (injected fake
engine) are all covered.

## CLI

```bash
python -m quant_indicators.cli db upgrade
python -m quant_indicators.cli db verify
python -m quant_indicators.cli indicators list
python -m quant_indicators.cli indicators sync-definitions

# One-shot compute over a date range for specific tickers
python -m quant_indicators.cli indicators compute \
    --from-date 2024-01-01 --to-date 2024-03-31 --tickers AAPL,MSFT

# Continuous daily recompute (used by supervisord)
python -m quant_indicators.cli indicators compute --schedule 86400

# Compute from a bars fixture without touching the database
python -m quant_indicators.cli indicators compute --fixture tests/fixtures/bars --dry-run

python -m quant_indicators.cli indicators run-summary --latest
```

`--lookback-days` (default `400`) loads extra history before `--from-date` so
long-window indicators such as `sma_200` warm up correctly.

## Retrieval API

| Method / Route                          | Description                              |
| --------------------------------------- | ---------------------------------------- |
| `GET /health`                           | Liveness probe.                          |
| `GET /ready`                            | Readiness: DB migrated to expected schema. |
| `GET /indicators`                       | List registered/active indicator definitions. |
| `GET /indicators/values`                | Query values (`ticker`, `indicator`, `from`, `to`, `adjustment_type`, `limit`, `offset`). |
| `GET /indicators/values/latest/<ticker>`| Latest value per indicator for a ticker. |
| `GET /indicators/coverage`              | Per-ticker/indicator point counts and date span. |
| `GET /runs`                             | Recent compute runs.                     |
| `GET /runs/latest`                      | Most recent run.                         |
| `GET /runs/<id>`                        | A specific run.                          |

## Configuration

See `.env.example`. Key variables:

| Variable                    | Default                          | Purpose                             |
| --------------------------- | -------------------------------- | ----------------------------------- |
| `DATABASE_URL`              | `postgresql+psycopg://quant:...` | Postgres connection.                |
| `BARS_SCHEMA` / `BARS_TABLE`| `market_data` / `daily_bars`     | Where input bars are read from.     |
| `INDICATOR_ADJUSTMENT_TYPE` | `unadjusted`                     | Default price series.               |
| `INDICATOR_LOOKBACK_DAYS`   | `400`                            | Warm-up history before start date.  |
| `COMPUTE_INTERVAL`          | `86400`                          | Seconds between scheduled computes. |
| `API_LISTEN_ADDRESS` / `API_PORT` | `0.0.0.0` / `8001`         | API bind address.                   |
