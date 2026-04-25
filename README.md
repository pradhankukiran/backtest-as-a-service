# backtest-as-a-service

Self-hosted Django + Postgres + Celery service that runs user-supplied Python trading
strategies against historical OHLCV bars and produces metrics (Sharpe, drawdown,
trade list, equity curve). Backtests run as Celery jobs; parameter sweeps fan out
across a worker pool. Single-user, technical project — not a SaaS.

## Stack

- Python 3.12 / Django 5.2 / Django REST Framework
- PostgreSQL + TimescaleDB extension (hypertables for `bars_bar` and `runs_equitypoint`)
- Redis + Celery (worker, beat scheduler, group fan-out)
- [`backtesting.py`](https://github.com/kernc/backtesting.py) 0.6.5 as the strategy execution engine
- yfinance for free historical bar data (Polygon/Alpaca pluggable later)

## Project layout

```
backtest-as-a-service/
├── manage.py
├── pyproject.toml             # uv-managed deps
├── start.sh                   # role dispatcher (web | worker | beat)
├── Dockerfile                 # single image, role chosen via $BACKTESTER_ROLE
├── docker-compose.yml         # timescale + redis + web + worker + beat
├── backtester/                # Django project package
│   ├── settings.py
│   ├── urls.py                # /admin, /healthz, /api/schema, /api/docs
│   ├── celery.py
│   ├── wsgi.py
│   └── asgi.py
├── bars/                      # data plane
│   ├── models.py              # Symbol, Bar
│   ├── admin.py
│   └── migrations/
│       ├── 0001_initial.py
│       └── 0002_timescaledb_hypertable.py   # converts bars_bar to hypertable on Postgres
└── runs/                      # execution plane
    ├── models.py              # Strategy, BacktestRun, Trade, EquityPoint, RunMetrics
    ├── admin.py
    └── migrations/
        ├── 0001_initial.py
        └── 0002_timescaledb_hypertable.py   # converts runs_equitypoint to hypertable
```

## Build phases

1. **Project skeleton + data models** — done
2. **Bar ingestion pipeline** (yfinance → Postgres) — done
3. Backtest execution engine (Celery → backtesting.py → results) — next
4. REST API + minimal UI
5. Parameter sweeps
6. Sandboxing hardening + cleanup

### Bar ingestion

- `bars.ingestion.fetch_daily_bars(ticker, start, end)` — yfinance pull with
  exponential-backoff retry, returns clean list-of-dicts.
- `bars.ingestion.upsert_bars(symbol, rows)` — Django 5 `bulk_create` with
  `update_conflicts=True` against the `(symbol, ts, timeframe)` unique key.
  Handles NaN/Inf, normalizes tz to UTC, dedupes within a batch.
- Celery task: `bars.ingest_bars(ticker, days_back=...)`, with autoretry on
  RuntimeError and exponential backoff capped at 600s.
- Beat schedule: `bars.ingest_all_active_bars(days_back=5)` runs nightly at
  02:00 UTC for every active Symbol.
- Admin actions: select Symbols → "Ingest last 30 days" or "Backfill 365 days".
- Management command: `python manage.py ingest_bars AAPL MSFT --start 2020-01-01`
  (or `--all`, `--days-back N`, `--create-missing`).

## Local development

```bash
uv sync --dev
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Or via Docker (full stack with TimescaleDB + Redis):

```bash
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Then visit `http://localhost:8000/admin/`.

## Environment

Copy `.env.example` to `.env` and tweak. Key vars:

- `DATABASE_URL` — Postgres URL (defaults to local SQLite if unset). For TimescaleDB
  features, point at a Postgres instance with the `timescaledb` extension.
- `REDIS_URL` — Celery broker / result backend.
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` — standard Django.

## Notes

- The TimescaleDB hypertable migrations are no-ops on SQLite (so the test runner works
  without TimescaleDB). They activate automatically when running migrations against
  a Postgres + TimescaleDB instance.
- `backtesting.py` 0.6.5 is AGPL-3.0 — fine for single-user / private use; if this is
  ever turned into a hosted SaaS, the strategy-execution layer must be source-disclosed
  to anyone who can interact with it.
