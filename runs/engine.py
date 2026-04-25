"""Backtest execution engine: load bars, run backtesting.py, serialize results."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from backtesting import Backtest

from bars.models import Bar, Symbol

from .sandbox import load_strategy_class

# Map backtesting.py stat keys onto RunMetrics fields. Unknown keys land in `raw`.
METRIC_KEYS = {
    "Return [%]": "return_pct",
    "Buy & Hold Return [%]": "buy_hold_return_pct",
    "Return (Ann.) [%]": "annualized_return_pct",
    "CAGR [%]": "cagr_pct",
    "Volatility (Ann.) [%]": "volatility_pct",
    "Sharpe Ratio": "sharpe_ratio",
    "Sortino Ratio": "sortino_ratio",
    "Calmar Ratio": "calmar_ratio",
    "Alpha [%]": "alpha_pct",
    "Beta": "beta",
    "Max. Drawdown [%]": "max_drawdown_pct",
    "Avg. Drawdown [%]": "avg_drawdown_pct",
    "Max. Drawdown Duration": "max_drawdown_duration_days",
    "Avg. Drawdown Duration": "avg_drawdown_duration_days",
    "# Trades": "trade_count",
    "Win Rate [%]": "win_rate_pct",
    "Best Trade [%]": "best_trade_pct",
    "Worst Trade [%]": "worst_trade_pct",
    "Avg. Trade [%]": "avg_trade_pct",
    "Profit Factor": "profit_factor",
    "Expectancy [%]": "expectancy_pct",
    "SQN": "sqn",
    "Kelly Criterion": "kelly_criterion",
    "Equity Final [$]": "final_equity",
    "Equity Peak [$]": "peak_equity",
    "Commissions [$]": "commissions_paid",
    "Exposure Time [%]": "exposure_time_pct",
}


@dataclass(frozen=True)
class EngineResult:
    metrics: dict[str, Any]
    trades: list[dict]
    equity_curve: list[dict]
    params: dict = field(default_factory=dict)


def load_bars_dataframe(
    symbol: Symbol,
    start: datetime,
    end: datetime,
    *,
    timeframe: str = "1d",
) -> pd.DataFrame:
    """Pull bars from Postgres into a `backtesting.py`-shaped DataFrame.

    Returns an empty DataFrame if no bars exist in the range.
    """
    qs = (
        Bar.objects.filter(symbol=symbol, ts__gte=start, ts__lte=end, timeframe=timeframe)
        .order_by("ts")
        .values("ts", "open", "high", "low", "close", "volume")
    )
    df = pd.DataFrame.from_records(qs)
    if df.empty:
        return df
    df = df.rename(
        columns={
            "ts": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.set_index("Date")
    for col in ("Open", "High", "Low", "Close", "Volume"):
        df[col] = df[col].astype(float)
    return df


def _coerce(value: Any) -> Any:
    """Convert values into JSON-/DB-safe primitives. NaN/Inf -> None."""
    if value is None:
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "total_seconds"):  # pd.Timedelta
        return value.total_seconds() / 86400  # report as days
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().isoformat()
    if hasattr(value, "item"):  # numpy scalars
        return _coerce(value.item())
    return value


def _serialize_metrics(stats: pd.Series) -> dict[str, Any]:
    """Flatten the stats Series into a plain dict, dropping internal keys."""
    return {key: _coerce(stats[key]) for key in stats.index if not key.startswith("_")}


def _serialize_trades(stats: pd.Series) -> list[dict]:
    trades_df: pd.DataFrame = stats.get("_trades")
    if trades_df is None or trades_df.empty:
        return []

    out: list[dict] = []
    for row in trades_df.itertuples(index=False):
        size = float(row.Size)
        side = "long" if size > 0 else "short"
        entry_ts = pd.Timestamp(row.EntryTime)
        exit_ts = pd.Timestamp(row.ExitTime) if pd.notna(row.ExitTime) else None
        duration = (
            int(row.Duration.total_seconds())
            if hasattr(row, "Duration") and hasattr(row.Duration, "total_seconds")
            else None
        )
        commission = float(getattr(row, "Commission", 0)) if pd.notna(getattr(row, "Commission", 0)) else 0
        out.append(
            {
                "side": side,
                "qty": abs(size),
                "entry_ts": _aware_utc(entry_ts),
                "entry_price": float(row.EntryPrice),
                "exit_ts": _aware_utc(exit_ts) if exit_ts is not None else None,
                "exit_price": float(row.ExitPrice) if pd.notna(row.ExitPrice) else None,
                "pnl": float(row.PnL) if pd.notna(row.PnL) else None,
                "return_pct": float(row.ReturnPct) if pd.notna(row.ReturnPct) else None,
                "commission_paid": commission,
                "duration_seconds": duration,
                "tag": str(row.Tag) if pd.notna(getattr(row, "Tag", None)) else "",
            }
        )
    return out


def _serialize_equity(stats: pd.Series) -> list[dict]:
    eq_df: pd.DataFrame = stats.get("_equity_curve")
    if eq_df is None or eq_df.empty:
        return []

    out: list[dict] = []
    for ts, row in eq_df.iterrows():
        ts = pd.Timestamp(ts)
        dd_dur = row.get("DrawdownDuration")
        if hasattr(dd_dur, "total_seconds"):
            dd_dur_days = dd_dur.total_seconds() / 86400
        else:
            dd_dur_days = None
        equity = float(row["Equity"])
        drawdown = float(row["DrawdownPct"]) if pd.notna(row.get("DrawdownPct")) else None
        out.append(
            {
                "ts": _aware_utc(ts),
                "equity": equity,
                "drawdown_pct": drawdown,
                "drawdown_duration_days": dd_dur_days,
            }
        )
    return out


def _aware_utc(ts: pd.Timestamp) -> datetime:
    py = ts.to_pydatetime()
    if py.tzinfo is None:
        py = py.replace(tzinfo=timezone.utc)
    return py.astimezone(timezone.utc)


def run_backtest_engine(
    *,
    code: str,
    entrypoint: str,
    df: pd.DataFrame,
    cash: float,
    commission_bps: int,
    params: dict | None = None,
) -> EngineResult:
    """Execute one backtest end-to-end. Returns serialized results.

    Raises:
        StrategySandboxError on bad strategy code.
        ValueError if the DataFrame is empty.
    """
    if df.empty:
        raise ValueError("Cannot backtest on an empty DataFrame")

    StrategyClass = load_strategy_class(code, entrypoint=entrypoint)

    bt = Backtest(
        df,
        StrategyClass,
        cash=cash,
        commission=commission_bps / 10_000,
        finalize_trades=True,
    )
    stats = bt.run(**(params or {}))

    return EngineResult(
        metrics=_serialize_metrics(stats),
        trades=_serialize_trades(stats),
        equity_curve=_serialize_equity(stats),
        params=dict(params or {}),
    )
