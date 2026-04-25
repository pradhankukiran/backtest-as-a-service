# backtest-as-a-service

Self-hosted Django + Postgres + Celery service that runs user-supplied Python trading
strategies against historical OHLCV bars and produces metrics (Sharpe, drawdown,
trade list, equity curve). Backtests run as Celery jobs; parameter sweeps fan out
across a worker pool.

Single-user, technical project — not a SaaS.

## Stack

- Python 3.12 / Django 5.x / Django REST Framework
- PostgreSQL + TimescaleDB extension (hypertables for bars and equity curves)
- Redis + Celery (worker, beat scheduler, group fan-out)
- [`backtesting.py`](https://github.com/kernc/backtesting.py) as the strategy execution engine
- yfinance / Alpaca for historical bar data
- TradingView Lightweight Charts for the UI

## Build phases

1. Project skeleton + data models (this repo's starting point)
2. Bar ingestion pipeline (yfinance → Postgres)
3. Backtest execution engine (Celery → backtesting.py → results)
4. REST API + minimal UI
5. Parameter sweeps
6. Sandboxing hardening + cleanup
