"""End-to-end test of the run_backtest Celery task against synthetic bars."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pytest

from bars.models import Bar, Symbol
from runs.models import BacktestRun, EquityPoint, RunMetrics, Strategy, Trade
from runs.strategies.builtin import SMA_CROSSOVER
from runs.tasks import run_backtest


def _seed_synthetic_bars(symbol: Symbol, n: int = 200) -> tuple[date, date]:
    rng = np.random.default_rng(7)
    drift = 0.001
    returns = rng.normal(loc=drift, scale=0.02, size=n)
    price = 100 * np.exp(np.cumsum(returns))
    high = price * (1 + rng.uniform(0, 0.01, n))
    low = price * (1 - rng.uniform(0, 0.01, n))
    open_ = np.r_[price[0], price[:-1]]
    volume = rng.integers(1_000_000, 5_000_000, n)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)

    rows = [
        Bar(
            symbol=symbol,
            ts=start + timedelta(days=i),
            timeframe="1d",
            open=Decimal(str(round(float(open_[i]), 4))),
            high=Decimal(str(round(float(high[i]), 4))),
            low=Decimal(str(round(float(low[i]), 4))),
            close=Decimal(str(round(float(price[i]), 4))),
            volume=Decimal(str(int(volume[i]))),
        )
        for i in range(n)
    ]
    Bar.objects.bulk_create(rows)
    return rows[0].ts.date(), rows[-1].ts.date()


@pytest.mark.django_db
def test_run_backtest_end_to_end():
    symbol = Symbol.objects.create(ticker="DEMO", name="Demo Synthetic")
    start_date, end_date = _seed_synthetic_bars(symbol, n=200)

    strategy = Strategy.objects.create(
        name=SMA_CROSSOVER.name,
        slug="sma-crossover-test",
        entrypoint=SMA_CROSSOVER.entrypoint,
        code=SMA_CROSSOVER.code,
        params_schema=SMA_CROSSOVER.params_schema,
    )

    run = BacktestRun.objects.create(
        strategy=strategy,
        start_date=start_date,
        end_date=end_date,
        initial_capital=Decimal("10000"),
        commission_bps=20,
        params={"sma_short": 5, "sma_long": 20},
    )
    run.symbols.add(symbol)

    result = run_backtest(run.id)

    run.refresh_from_db()
    assert run.status == BacktestRun.Status.SUCCEEDED, run.error
    assert result["status"] == BacktestRun.Status.SUCCEEDED
    assert run.duration_ms is not None and run.duration_ms >= 0
    assert run.error == ""

    metrics = RunMetrics.objects.get(run=run)
    assert metrics.return_pct is not None
    assert metrics.final_equity is not None
    assert metrics.trade_count >= 0
    assert metrics.raw  # the full stats dict

    assert EquityPoint.objects.filter(run=run).count() > 0
    if metrics.trade_count > 0:
        first_trade = Trade.objects.filter(run=run).earliest("entry_ts")
        assert first_trade.symbol == symbol
        assert first_trade.entry_price > 0


@pytest.mark.django_db
def test_run_backtest_marks_failed_when_no_bars():
    symbol = Symbol.objects.create(ticker="EMPTY")
    strategy = Strategy.objects.create(
        name=SMA_CROSSOVER.name,
        slug="sma-crossover-empty",
        entrypoint=SMA_CROSSOVER.entrypoint,
        code=SMA_CROSSOVER.code,
    )
    run = BacktestRun.objects.create(
        strategy=strategy,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        initial_capital=Decimal("10000"),
        commission_bps=20,
    )
    run.symbols.add(symbol)

    result = run_backtest(run.id)
    run.refresh_from_db()

    assert run.status == BacktestRun.Status.FAILED
    assert "No bars" in run.error
    assert result["status"] == BacktestRun.Status.FAILED
