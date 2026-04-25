"""Tests for grid expansion and sweep fan-out."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from bars.models import Symbol
from runs.models import BacktestRun, ParameterSweep, Strategy
from runs.strategies.builtin import SMA_CROSSOVER
from runs.sweeps import GridError, expand_grid, grid_size, merge_params
from runs.tasks import finalize_sweep, optimize


def test_expand_grid_empty():
    assert expand_grid({}) == [{}]


def test_expand_grid_lists():
    grid = {"a": [1, 2], "b": ["x", "y", "z"]}
    combos = expand_grid(grid)
    assert len(combos) == 6
    assert {"a": 1, "b": "x"} in combos
    assert {"a": 2, "b": "z"} in combos


def test_expand_grid_range():
    combos = expand_grid({"sma_short": {"start": 5, "stop": 15, "step": 5}})
    assert combos == [{"sma_short": 5}, {"sma_short": 10}, {"sma_short": 15}]


def test_expand_grid_mixed_with_scalar():
    combos = expand_grid({"x": [1, 2], "tag": "v1"})
    assert combos == [{"tag": "v1", "x": 1}, {"tag": "v1", "x": 2}]


def test_grid_size_matches_expand_length():
    grid = {
        "sma_short": [5, 10, 15],
        "sma_long": {"start": 20, "stop": 60, "step": 10},
    }
    assert grid_size(grid) == 3 * 5
    assert len(expand_grid(grid)) == grid_size(grid)


def test_expand_grid_rejects_empty_list():
    with pytest.raises(GridError):
        expand_grid({"x": []})


def test_expand_grid_rejects_zero_step():
    with pytest.raises(GridError):
        expand_grid({"x": {"start": 0, "stop": 10, "step": 0}})


def test_merge_params_combines_base_and_combo():
    base = {"capital": 10000, "fee": 0.001}
    combo = {"sma_short": 10}
    out = merge_params(base, combo)
    assert out == {"capital": 10000, "fee": 0.001, "sma_short": 10}
    # base unchanged
    assert "sma_short" not in base


@pytest.fixture
def sweep_factory(db):
    def _make(**overrides) -> ParameterSweep:
        strategy = Strategy.objects.create(
            name=SMA_CROSSOVER.name,
            slug=overrides.pop("slug", "sweep-strategy"),
            entrypoint=SMA_CROSSOVER.entrypoint,
            code=SMA_CROSSOVER.code,
        )
        symbol = Symbol.objects.create(ticker=overrides.pop("ticker", "SWEEP"))
        sweep = ParameterSweep.objects.create(
            strategy=strategy,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=Decimal("10000"),
            commission_bps=20,
            grid={"sma_short": [5, 10], "sma_long": [30]},
            **overrides,
        )
        sweep.symbols.add(symbol)
        return sweep

    return _make


@pytest.mark.django_db
def test_optimize_creates_children_and_dispatches_chord(sweep_factory):
    sweep = sweep_factory()

    with patch("runs.tasks.chord") as chord_mock:
        chord_mock.return_value.apply_async.return_value = None
        result = optimize(sweep.id)

    sweep.refresh_from_db()
    assert sweep.status == ParameterSweep.Status.RUNNING
    assert sweep.children_total == 2
    children = list(BacktestRun.objects.filter(sweep=sweep).order_by("id"))
    assert len(children) == 2
    expected_params = [{"sma_short": 5, "sma_long": 30}, {"sma_short": 10, "sma_long": 30}]
    assert [c.params for c in children] == expected_params
    assert result["children_queued"] == 2
    chord_mock.return_value.apply_async.assert_called_once()


@pytest.mark.django_db
def test_finalize_sweep_marks_succeeded_when_all_children_pass(sweep_factory):
    sweep = sweep_factory()
    sweep.children_total = 3
    sweep.status = ParameterSweep.Status.RUNNING
    from django.utils import timezone

    sweep.started_at = timezone.now()
    sweep.save()

    child_results = [
        {"run_id": 1, "status": BacktestRun.Status.SUCCEEDED},
        {"run_id": 2, "status": BacktestRun.Status.SUCCEEDED},
        {"run_id": 3, "status": BacktestRun.Status.SUCCEEDED},
    ]
    finalize_sweep(child_results, sweep.id)

    sweep.refresh_from_db()
    assert sweep.status == ParameterSweep.Status.SUCCEEDED
    assert sweep.children_succeeded == 3
    assert sweep.children_failed == 0
    assert sweep.duration_ms is not None and sweep.duration_ms >= 0


@pytest.mark.django_db
def test_finalize_sweep_marks_partial_when_some_fail(sweep_factory):
    sweep = sweep_factory()
    sweep.children_total = 3
    sweep.status = ParameterSweep.Status.RUNNING
    from django.utils import timezone

    sweep.started_at = timezone.now()
    sweep.save()

    child_results = [
        {"run_id": 1, "status": BacktestRun.Status.SUCCEEDED},
        {"run_id": 2, "status": BacktestRun.Status.FAILED},
        {"run_id": 3, "status": BacktestRun.Status.FAILED},
    ]
    finalize_sweep(child_results, sweep.id)

    sweep.refresh_from_db()
    assert sweep.status == ParameterSweep.Status.PARTIAL
    assert sweep.children_succeeded == 1
    assert sweep.children_failed == 2


@pytest.mark.django_db
def test_finalize_sweep_marks_failed_when_all_fail(sweep_factory):
    sweep = sweep_factory()
    sweep.children_total = 2
    sweep.status = ParameterSweep.Status.RUNNING
    from django.utils import timezone

    sweep.started_at = timezone.now()
    sweep.save()

    child_results = [
        {"run_id": 1, "status": BacktestRun.Status.FAILED},
        {"run_id": 2, "status": BacktestRun.Status.FAILED},
    ]
    finalize_sweep(child_results, sweep.id)

    sweep.refresh_from_db()
    assert sweep.status == ParameterSweep.Status.FAILED
    assert sweep.children_succeeded == 0
    assert sweep.children_failed == 2
