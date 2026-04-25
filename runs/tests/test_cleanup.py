"""Tests for the cleanup_stale_runs task."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from bars.models import Symbol
from runs.models import BacktestRun, EquityPoint, Strategy, Trade
from runs.strategies.builtin import SMA_CROSSOVER
from runs.tasks import cleanup_stale_runs


@pytest.fixture
def strategy(db):
    return Strategy.objects.create(
        name=SMA_CROSSOVER.name,
        slug="cleanup-strategy",
        entrypoint=SMA_CROSSOVER.entrypoint,
        code=SMA_CROSSOVER.code,
    )


@pytest.fixture
def symbol(db):
    return Symbol.objects.create(ticker="OLD")


def _make_run(strategy, symbol, *, finished_days_ago: int, status):
    run = BacktestRun.objects.create(
        strategy=strategy,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        initial_capital=Decimal("10000"),
        commission_bps=20,
        status=status,
        finished_at=timezone.now() - timedelta(days=finished_days_ago),
    )
    run.symbols.add(symbol)
    EquityPoint.objects.create(
        run=run,
        ts=timezone.now() - timedelta(days=finished_days_ago),
        equity=Decimal("10000"),
    )
    Trade.objects.create(
        run=run,
        symbol=symbol,
        side="long",
        qty=Decimal("1"),
        entry_ts=timezone.now() - timedelta(days=finished_days_ago),
        entry_price=Decimal("100"),
    )
    return run


@pytest.mark.django_db
def test_cleanup_drops_old_succeeded_runs_only(strategy, symbol):
    old_ok = _make_run(strategy, symbol, finished_days_ago=120, status=BacktestRun.Status.SUCCEEDED)
    fresh_ok = _make_run(strategy, symbol, finished_days_ago=30, status=BacktestRun.Status.SUCCEEDED)
    old_failed = _make_run(strategy, symbol, finished_days_ago=120, status=BacktestRun.Status.FAILED)

    result = cleanup_stale_runs(older_than_days=90)

    assert result["runs_pruned"] == 1
    assert result["equity_points_deleted"] == 1
    assert result["trades_deleted"] == 1

    assert not EquityPoint.objects.filter(run=old_ok).exists()
    assert not Trade.objects.filter(run=old_ok).exists()
    # the BacktestRun row itself stays
    assert BacktestRun.objects.filter(id=old_ok.id).exists()

    assert EquityPoint.objects.filter(run=fresh_ok).exists()
    assert EquityPoint.objects.filter(run=old_failed).exists()


@pytest.mark.django_db
def test_cleanup_returns_zero_when_nothing_stale(strategy, symbol):
    _make_run(strategy, symbol, finished_days_ago=10, status=BacktestRun.Status.SUCCEEDED)
    result = cleanup_stale_runs(older_than_days=90)
    assert result == {"runs_pruned": 0, "equity_points_deleted": 0, "trades_deleted": 0}
