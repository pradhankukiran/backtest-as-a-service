<div align="center">

# Backtest-as-a-Service

**Self-hosted Django + Postgres + Celery service that runs Python trading strategies against historical OHLCV bars and produces metrics, equity curves, trade lists, and parameter sweeps.**

[![Python](https://img.shields.io/badge/python-3.12+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-5.2-092E20.svg?style=flat-square&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.15-A30000.svg?style=flat-square)](https://www.django-rest-framework.org/)
[![Celery](https://img.shields.io/badge/celery-5.4-37814A.svg?style=flat-square&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![PostgreSQL](https://img.shields.io/badge/postgres-16-336791.svg?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![TimescaleDB](https://img.shields.io/badge/timescaleDB-2.x-FDB515.svg?style=flat-square&logo=timescale&logoColor=black)](https://www.timescale.com/)
[![Redis](https://img.shields.io/badge/redis-7-DC382D.svg?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![backtesting.py](https://img.shields.io/badge/backtesting.py-0.6.5-059669.svg?style=flat-square)](https://github.com/kernc/backtesting.py)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![uv](https://img.shields.io/badge/uv-managed-261230.svg?style=flat-square&logo=astral&logoColor=white)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64.svg?style=flat-square&logo=ruff&logoColor=black)](https://docs.astral.sh/ruff/)
[![pytest](https://img.shields.io/badge/tests-36%20passing-15803d.svg?style=flat-square&logo=pytest&logoColor=white)](https://docs.pytest.org/)

</div>

Submit a Python `Strategy` class, a date range, a starting capital, and a list
of symbols — Backtest-as-a-Service runs the simulation in a sandboxed Celery
worker, persists every trade and equity point, and shows you Sharpe ratio,
drawdown, and an equity curve. Parameter sweeps fan out across hundreds of
combinations in parallel via a Celery `chord(group, callback)`.

Single-operator, technical project. Not a SaaS.

---

## Features

- **`backtesting.py` 0.6.5 engine** — proven library; we wrap it, persist results, and add async + multi-strategy + UI on top
- **TimescaleDB hypertables** for OHLCV bars and equity curves — fast range scans on millions of rows, automatic chunking
- **yfinance bar ingestion** with exponential-backoff retry, NaN/Inf filtering, idempotent `bulk_create(update_conflicts=True)` upserts
- **Sandboxed strategy execution** — AST pre-pass rejects `os` / `subprocess` / `eval` / file IO before code runs; user code only executes on a dedicated Celery queue consumed by a hardened worker container
- **Parameter sweeps** — one `POST /api/sweeps/` fans out to N child runs via Celery chord; finalize callback aggregates the result; comparison view ranks by Sharpe and ★-marks the winner
- **Built-in example strategy** — SMA crossover ships in `runs/strategies/builtin.py`; `python manage.py install_builtin_strategies` seeds it
- **REST API** with Swagger UI at `/api/docs/`, plus a minimal HTML console (landing, run list, run detail with TradingView Lightweight Charts equity curve, sweep comparison table)
- **Operator UI** via Django Admin reskinned with `django-unfold` (emerald palette, sidebar nav, light theme, no border-radius)
- **Retention policy** — weekly Celery beat task drops `EquityPoint` and `Trade` rows for `SUCCEEDED` runs older than 90 days; summaries stay
- **One-command deploy** with Docker Compose (web + worker + worker-untrusted + beat + TimescaleDB + Redis)

## Architecture

```text
              +---------------------+
   user --->  | POST /api/runs/     | --> creates BacktestRun row
              | POST /api/sweeps/   |     dispatches Celery task
              +---------+-----------+
                        |
                        v
                  +-----------+        +----------+
                  |  Redis    |  <-->  |  Celery  |
                  | (broker)  |        |  beat    |
                  +-----+-----+        +----------+
                        |
            +-----------+-----------+
            |                       |
            v                       v
    +--------------+         +-------------------+
    | worker       |         | worker-untrusted  |
    | (default Q)  |         | (untrusted Q)     |
    | ingest, opt, |         | run_backtest only |
    | finalize,    |         | hardened: cap_drop|
    | cleanup      |         | read_only, ulimit |
    +------+-------+         +---------+---------+
           |                           |
           +-------------+-------------+
                         |
                         v
                +------------------+
                |   TimescaleDB    |  <--  bars (hypertable)
                |   PostgreSQL 16  |  <--  equity points (hypertable)
                +------------------+      runs, trades, metrics, sweeps
```

## Tech Stack

| Layer            | Components                                                                              |
| ---------------- | --------------------------------------------------------------------------------------- |
| Control plane    | Python 3.12, Django 5.2, Django REST Framework 3.15, drf-spectacular, django-filter     |
| Async pipeline   | Celery 5.4 (worker, beat, chord fan-out), Redis 7                                       |
| Datastore        | PostgreSQL 16 + TimescaleDB extension; SQLite fallback for local-only dev               |
| Backtest engine  | [`backtesting.py`](https://github.com/kernc/backtesting.py) 0.6.5, pandas 2.x, numpy    |
| Data ingestion   | yfinance for free historical bars (Polygon / Alpaca pluggable)                          |
| Admin theme      | `django-unfold` (Tailwind-based reskin), Material Symbols icons                         |
| UI charting      | TradingView Lightweight Charts v5 (vanilla JS, no build step)                           |
| Tooling          | `uv` (deps), `ruff` (lint), `pytest` + `pytest-django` (36 tests), Docker & Compose     |
| API surface      | OpenAPI 3 schema at `/api/schema/`, Swagger UI at `/api/docs/`                          |

## Quick Start (Docker)

```bash
docker compose up --build
```

In another terminal, seed an admin user, the SMA-crossover strategy, and a year of AAPL bars:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py install_builtin_strategies
docker compose exec web python manage.py ingest_bars AAPL --create-missing --days-back 365
```

Open the console at <http://localhost:8000/>. Login: whatever superuser you just made.

| Service           | Port | Purpose                                                            |
| ----------------- | ---- | ------------------------------------------------------------------ |
| web               | 8000 | Django (admin, API, public UI)                                     |
| db                | 5432 | TimescaleDB on PostgreSQL 16                                       |
| redis             | 6379 | Celery broker + result backend                                     |
| worker            | —    | Default queue: ingestion, sweep orchestration, finalize, cleanup   |
| worker-untrusted  | —    | `untrusted` queue: only `run_backtest` runs here, hardened         |
| beat              | —    | Cron: nightly bar ingest at 02:00 UTC, weekly cleanup Sundays 03:00 |

## Sending your first backtest

Once a strategy and at least one symbol with bars exist, fire a run from the shell:

```bash
curl -b session.cookie -X POST http://localhost:8000/api/runs/ \
  -H 'Content-Type: application/json' \
  -H "X-CSRFToken: $CSRF" \
  -d '{
    "strategy": "sma-crossover",
    "symbols": ["AAPL"],
    "start_date": "2025-04-25",
    "end_date":   "2026-04-24",
    "initial_capital": 10000,
    "commission_bps": 20,
    "params": {"sma_short": 10, "sma_long": 30}
  }'
```

The response is the run's detail payload (status `pending`); the `untrusted`
worker picks it up immediately and within a second or two `status` flips to
`succeeded` with `metrics` populated. Browse the result at
**`/runs/<id>/`** — equity curve, metrics grid, and trade table.

## Parameter sweeps

`POST /api/sweeps/` fans out one strategy across many parameter combinations:

```json
{
  "strategy": "sma-crossover",
  "symbols": ["AAPL"],
  "start_date": "2023-01-01",
  "end_date":   "2024-01-01",
  "initial_capital": 10000,
  "commission_bps": 20,
  "grid": {
    "sma_short": [5, 10, 15, 20],
    "sma_long":  {"start": 30, "stop": 70, "step": 10}
  }
}
```

→ 4 × 5 = **20 child runs** materialized as `BacktestRun` rows linked to a
parent `ParameterSweep`, dispatched as a Celery `chord(group, callback)`.
Each child runs as an independent task; failures don't kill the rest of
the sweep. The `finalize_sweep` callback flips the parent to
`succeeded` / `partial` / `failed` based on child outcomes.

Compare results at **`/sweeps/<id>/`** — sortable table of `(params, return,
Sharpe, max DD, trades, final equity)`. The best Sharpe row is ★-marked.
Programmatic access: `GET /api/sweeps/<id>/comparison/` for the same data
as JSON, ready for charting / heatmapping.

Grid syntax accepts:

| Form   | Example                                | Expands to                |
| ------ | -------------------------------------- | ------------------------- |
| List   | `[5, 10, 15]`                          | three explicit values     |
| Range  | `{"start": 5, "stop": 30, "step": 5}` | `[5,10,15,20,25,30]`      |
| Scalar | `42`                                   | one value (constant)      |

## Sandboxing

User-supplied strategy code only ever runs on the `untrusted` Celery queue,
which is consumed by a dedicated `worker-untrusted` container. The mapping
is enforced both centrally (`CELERY_TASK_ROUTES`) and on the task itself
(`@shared_task(queue="untrusted")`) — belt-and-braces, since misrouting is
a security hazard.

The `worker-untrusted` container runs hardened:

- `cap_drop: ["ALL"]`, `security_opt: no-new-privileges`
- `read_only: true` filesystem with a 64 MB tmpfs for `/tmp`
- `pids_limit: 256`, `mem_limit: 1g`, `cpus: "1.0"`
- `--max-tasks-per-child=1` so each strategy run is a fresh process

Before any code runs, an AST pre-pass rejects forbidden imports (`os`,
`subprocess`, `socket`, …) and forbidden builtin names (`eval`, `exec`,
`compile`, `open`, `__import__`). For real isolation against malicious
strategies, attach `worker-untrusted` to an `internal: true` Docker
network with no external egress, or move the worker behind gVisor /
Firecracker microVMs.

## REST API

Documented via Swagger at <http://localhost:8000/api/docs/>. Key endpoints:

| Endpoint                            | Verbs                  | Notes                                                                        |
| ----------------------------------- | ---------------------- | ---------------------------------------------------------------------------- |
| `/api/symbols/`                     | GET, POST              | Manage tradable symbols                                                      |
| `/api/bars/`                        | GET (read-only)        | Browse stored OHLCV bars                                                     |
| `/api/strategies/`                  | GET, POST, PATCH, DELETE | Strategy CRUD; lookup by `slug`                                            |
| `/api/runs/`                        | GET, **POST**          | POST creates a run AND queues `run_backtest` immediately (returns 202)       |
| `/api/runs/<id>/`                   | GET, PATCH, DELETE     | Run detail with embedded metrics                                             |
| `/api/runs/<id>/equity-curve/`      | GET                    | Equity points; powers the chart                                              |
| `/api/runs/<id>/trades/`            | GET                    | All trades for a run                                                         |
| `/api/runs/<id>/rerun/`             | POST                   | Re-queue an existing run                                                     |
| `/api/sweeps/`                      | GET, **POST**          | POST creates a sweep AND fans out via Celery chord (returns 202)             |
| `/api/sweeps/<id>/`                 | GET, PATCH, DELETE     | Sweep detail with embedded counters                                          |
| `/api/sweeps/<id>/comparison/`      | GET                    | Flat JSON of `(params, metrics)` for every child run                         |
| `/api/sweeps/<id>/rerun/`           | POST                   | Re-fan out the sweep                                                         |

## Configuration

All settings are env-var driven via `django-environ`. See [`.env.example`](./.env.example).

| Variable                                | Purpose                                                       |
| --------------------------------------- | ------------------------------------------------------------- |
| `SECRET_KEY`                            | Django secret key                                             |
| `DEBUG`                                 | Toggle Django debug mode                                      |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Standard Django host / CSRF settings                          |
| `DATABASE_URL`                          | Postgres URL; SQLite fallback for tests                       |
| `REDIS_URL`                             | Redis URL used by Celery broker and result backend            |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Override broker / backend independently if needed         |

## Project layout

```text
backtest-as-a-service/
├── manage.py
├── pyproject.toml                       # uv-managed deps
├── start.sh                             # role dispatcher (web | worker | worker-untrusted | beat)
├── Dockerfile                           # single image, role chosen via $BACKTESTER_ROLE
├── docker-compose.yml                   # timescale + redis + web + worker + worker-untrusted + beat
├── backtester/                          # Django project package
│   ├── settings.py                      # routes run_backtest to "untrusted" queue + UNFOLD config
│   ├── urls.py                          # /admin, /healthz, /api/, /, /runs/, /sweeps/
│   ├── celery.py
│   ├── wsgi.py
│   └── asgi.py
├── bars/                                # data plane
│   ├── models.py                        # Symbol, Bar
│   ├── ingestion.py                     # fetch_daily_bars + upsert_bars + ingest_symbol
│   ├── tasks.py                         # ingest_bars + ingest_all_active_bars
│   ├── api.py                           # SymbolViewSet, BarViewSet
│   ├── admin.py                         # via unfold.admin.ModelAdmin
│   ├── management/commands/ingest_bars.py
│   └── migrations/
│       ├── 0001_initial.py
│       └── 0002_timescaledb_hypertable.py   # converts bars_bar to hypertable on Postgres
├── runs/                                # execution plane
│   ├── models.py                        # Strategy, BacktestRun, Trade, EquityPoint, RunMetrics, ParameterSweep
│   ├── sandbox.py                       # AST audit + load_strategy_class
│   ├── engine.py                        # backtesting.py wrapper + result serializer
│   ├── persistence.py                   # bulk-create trades/equity, upsert metrics
│   ├── sweeps.py                        # grid expansion (list / range / scalar / cartesian product)
│   ├── tasks.py                         # run_backtest, optimize, finalize_sweep, cleanup_stale_runs
│   ├── api.py                           # StrategyViewSet, BacktestRunViewSet, ParameterSweepViewSet
│   ├── views.py                         # HTML pages: runs list/detail, sweeps list/detail
│   ├── admin.py                         # via unfold.admin.ModelAdmin + custom UserAdmin
│   ├── strategies/builtin.py            # SMA crossover example
│   ├── management/commands/install_builtin_strategies.py
│   ├── static/runs/admin-overrides.css  # zero border-radius, hide gear icon, emerald wordmark
│   └── migrations/
│       ├── 0001_initial.py
│       ├── 0002_timescaledb_hypertable.py
│       └── 0003_parametersweep_backtestrun_sweep_and_more.py
└── templates/
    ├── base.html                        # nav + emerald CSS variables
    ├── landing.html
    └── runs/
        ├── list.html
        ├── detail.html                  # equity curve via Lightweight Charts v5
        ├── sweep_list.html
        └── sweep_detail.html            # comparison table, ★ on best Sharpe
```

## Local development

Native Python workflow with [`uv`](https://github.com/astral-sh/uv):

```bash
uv sync --dev                                  # install deps
uv run python manage.py migrate                # apply migrations
uv run python manage.py createsuperuser        # create admin user
uv run python manage.py install_builtin_strategies
uv run python manage.py ingest_bars AAPL --create-missing --days-back 365
uv run python manage.py runserver              # start web
uv run celery -A backtester worker -Q default -n default@%h --loglevel=info
uv run celery -A backtester worker -Q untrusted -n untrusted@%h --max-tasks-per-child=1 --loglevel=info
uv run celery -A backtester beat --loglevel=info
```

## Testing & quality

```bash
uv run ruff check .                    # lint
uv run python manage.py check          # Django system check
uv run pytest                          # 36 tests
docker compose config                  # validate compose stack
```

The suite covers ingestion (5), sandbox (7), engine (3), task (2), API (5), sweeps (9), cleanup (2), and full end-to-end runs against synthetic + real data.

## Roadmap

This is a single-operator project. Multi-tenant orgs, billing, team roles
are out of scope.

**Done**

- TimescaleDB-backed bar store + nightly yfinance ingestion
- `backtesting.py` engine wrapper, result serializer, persistence
- AST-audited strategy sandbox + Celery `untrusted` queue + hardened worker container
- Parameter sweeps via Celery chord with finalize callback
- REST API + minimal HTML UI with Lightweight Charts equity curve
- `django-unfold` admin reskin (emerald, sidebar nav, no border-radius)
- Retention / cleanup task

**Next**

- Polygon / Alpaca data sources behind the same `bars.ingestion` interface
- Walk-forward analysis (split a date range into train/test windows, run a sweep on each)
- Live paper-trading mode via Alpaca's paper API
- Drawdown overlay + benchmark comparison line on the equity chart
- Production hardening: `internal: true` Docker network for `worker-untrusted`, gVisor / Firecracker per-job
- CI: GitHub Actions running `ruff` + `pytest` + Docker compose health check

---

`backtesting.py` 0.6.5 is licensed under AGPL-3.0 — fine for single-user / private use; if this is ever turned into a hosted SaaS, the strategy-execution layer must be source-disclosed to anyone who can interact with it.
