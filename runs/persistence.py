"""Persist EngineResult into the runs tables (Trade, EquityPoint, RunMetrics)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction

from .engine import METRIC_KEYS, EngineResult
from .models import BacktestRun, EquityPoint, RunMetrics, Trade


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


@transaction.atomic
def save_run_results(run: BacktestRun, result: EngineResult) -> None:
    """Persist all artefacts (trades, equity points, metrics) for `run`."""
    Trade.objects.filter(run=run).delete()
    EquityPoint.objects.filter(run=run).delete()

    primary_symbol = run.symbols.first()

    trade_objs = [
        Trade(
            run=run,
            symbol=primary_symbol,
            side=t["side"],
            qty=_to_decimal(t["qty"]),
            entry_ts=t["entry_ts"],
            entry_price=_to_decimal(t["entry_price"]),
            exit_ts=t["exit_ts"],
            exit_price=_to_decimal(t["exit_price"]),
            pnl=_to_decimal(t["pnl"]),
            return_pct=t["return_pct"],
            commission_paid=_to_decimal(t["commission_paid"]) or Decimal(0),
            duration_seconds=t["duration_seconds"],
            tag=t["tag"],
        )
        for t in result.trades
    ]
    if trade_objs:
        Trade.objects.bulk_create(trade_objs, batch_size=1000)

    equity_objs = [
        EquityPoint(
            run=run,
            ts=point["ts"],
            equity=_to_decimal(point["equity"]),
            drawdown_pct=point["drawdown_pct"],
            drawdown_duration_days=point["drawdown_duration_days"],
        )
        for point in result.equity_curve
    ]
    if equity_objs:
        EquityPoint.objects.bulk_create(equity_objs, batch_size=1000)

    metrics_kwargs: dict[str, Any] = {"raw": result.metrics}
    for stat_key, model_field in METRIC_KEYS.items():
        if stat_key not in result.metrics:
            continue
        value = result.metrics[stat_key]
        if model_field == "trade_count":
            metrics_kwargs[model_field] = int(value or 0)
        elif model_field in {"final_equity", "peak_equity", "commissions_paid"}:
            metrics_kwargs[model_field] = _to_decimal(value)
        else:
            metrics_kwargs[model_field] = value

    RunMetrics.objects.update_or_create(run=run, defaults=metrics_kwargs)
