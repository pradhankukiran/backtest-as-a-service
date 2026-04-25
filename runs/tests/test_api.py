"""Tests for the runs REST API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from bars.models import Symbol
from runs.models import BacktestRun, EquityPoint, RunMetrics, Strategy, Trade
from runs.strategies.builtin import SMA_CROSSOVER


@pytest.fixture
def admin_client(db, client):
    user = get_user_model().objects.create_superuser(
        username="admin",
        email="admin@example.test",
        password="password",
    )
    client.force_login(user)
    return client


@pytest.fixture
def strategy(db):
    return Strategy.objects.create(
        name=SMA_CROSSOVER.name,
        slug=SMA_CROSSOVER.slug,
        entrypoint=SMA_CROSSOVER.entrypoint,
        code=SMA_CROSSOVER.code,
        params_schema=SMA_CROSSOVER.params_schema,
    )


@pytest.fixture
def symbol(db):
    return Symbol.objects.create(ticker="DEMO")


def test_post_run_creates_and_queues_task(admin_client, strategy, symbol):
    payload = {
        "strategy": strategy.slug,
        "symbols": [symbol.ticker],
        "timeframe": "1d",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "initial_capital": 10000,
        "commission_bps": 20,
        "params": {"sma_short": 10, "sma_long": 30},
    }
    with patch("runs.api.run_backtest.delay") as delay:
        response = admin_client.post(
            reverse("backtestrun-list"),
            data=payload,
            content_type="application/json",
        )

    assert response.status_code == 202, response.content
    run_id = response.json()["id"]
    assert BacktestRun.objects.filter(id=run_id).exists()
    delay.assert_called_once_with(run_id)


def test_list_runs_includes_metrics(admin_client, strategy, symbol):
    run = BacktestRun.objects.create(
        strategy=strategy,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_capital=Decimal("10000"),
        commission_bps=20,
        status=BacktestRun.Status.SUCCEEDED,
    )
    run.symbols.add(symbol)
    RunMetrics.objects.create(run=run, return_pct=12.5, sharpe_ratio=1.1, trade_count=4)

    response = admin_client.get(reverse("backtestrun-list"))
    assert response.status_code == 200
    rows = response.json()
    if isinstance(rows, dict):
        rows = rows.get("results", rows)
    assert any(r["id"] == run.id and r["return_pct"] == 12.5 for r in rows)


def test_equity_curve_endpoint(admin_client, strategy, symbol):
    run = BacktestRun.objects.create(
        strategy=strategy,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        initial_capital=Decimal("10000"),
        commission_bps=20,
    )
    run.symbols.add(symbol)
    EquityPoint.objects.bulk_create(
        [
            EquityPoint(
                run=run,
                ts=f"2024-01-0{i}T00:00:00Z",
                equity=Decimal("10000") + i,
                drawdown_pct=0.0,
            )
            for i in (1, 2, 3, 4)
        ]
    )

    response = admin_client.get(reverse("backtestrun-equity-curve", kwargs={"pk": run.id}))
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 4
    assert rows[0]["ts"].startswith("2024-01-01")
    assert float(rows[-1]["equity"]) > float(rows[0]["equity"])


def test_trades_endpoint(admin_client, strategy, symbol):
    run = BacktestRun.objects.create(
        strategy=strategy,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        initial_capital=Decimal("10000"),
        commission_bps=20,
    )
    run.symbols.add(symbol)
    Trade.objects.create(
        run=run,
        symbol=symbol,
        side="long",
        qty=Decimal("10"),
        entry_ts="2024-01-02T00:00:00Z",
        entry_price=Decimal("100"),
        exit_ts="2024-01-10T00:00:00Z",
        exit_price=Decimal("110"),
        pnl=Decimal("100"),
        return_pct=10.0,
    )

    response = admin_client.get(reverse("backtestrun-trades", kwargs={"pk": run.id}))
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "DEMO"
    assert rows[0]["side"] == "long"


def test_rerun_endpoint_queues_task(admin_client, strategy, symbol):
    run = BacktestRun.objects.create(
        strategy=strategy,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        initial_capital=Decimal("10000"),
        commission_bps=20,
    )
    run.symbols.add(symbol)

    with patch("runs.api.run_backtest.delay") as delay:
        response = admin_client.post(reverse("backtestrun-rerun", kwargs={"pk": run.id}))

    assert response.status_code == 202
    delay.assert_called_once_with(run.id)
