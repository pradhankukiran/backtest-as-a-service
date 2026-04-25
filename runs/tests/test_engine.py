"""End-to-end tests for the backtest engine on synthetic bars."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from runs.engine import EngineResult, run_backtest_engine
from runs.strategies.builtin import SMA_CROSSOVER


def _synthetic_bars(n: int = 200, seed: int = 7) -> pd.DataFrame:
    """Generate a deterministic walk + small drift so SMA crossover triggers trades."""
    rng = np.random.default_rng(seed)
    drift = 0.001
    returns = rng.normal(loc=drift, scale=0.02, size=n)
    price = 100 * np.exp(np.cumsum(returns))
    high = price * (1 + rng.uniform(0, 0.01, n))
    low = price * (1 - rng.uniform(0, 0.01, n))
    open_ = np.r_[price[0], price[:-1]]
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": price, "Volume": volume},
        index=idx,
    )


def test_run_backtest_engine_smoke():
    df = _synthetic_bars(n=200)
    result = run_backtest_engine(
        code=SMA_CROSSOVER.code,
        entrypoint=SMA_CROSSOVER.entrypoint,
        df=df,
        cash=10_000,
        commission_bps=20,
        params={"sma_short": 5, "sma_long": 20},
    )
    assert isinstance(result, EngineResult)
    assert "Sharpe Ratio" in result.metrics
    assert "Equity Final [$]" in result.metrics
    assert isinstance(result.equity_curve, list)
    assert len(result.equity_curve) > 0
    assert all("ts" in pt and "equity" in pt for pt in result.equity_curve)
    assert result.params == {"sma_short": 5, "sma_long": 20}
    if result.trades:
        first = result.trades[0]
        assert first["side"] in ("long", "short")
        assert first["qty"] > 0
        assert first["entry_ts"].tzinfo is not None


def test_run_backtest_engine_rejects_empty_dataframe():
    df = pd.DataFrame()
    with pytest.raises(ValueError, match="empty"):
        run_backtest_engine(
            code=SMA_CROSSOVER.code,
            entrypoint=SMA_CROSSOVER.entrypoint,
            df=df,
            cash=10_000,
            commission_bps=20,
        )


def test_run_backtest_engine_load_bars_dataframe_uses_orm(monkeypatch):
    from runs.engine import load_bars_dataframe

    captured = {}

    class _DummyQS:
        def filter(self, **kwargs):
            captured.update(kwargs)
            return self

        def order_by(self, *args, **kwargs):  # noqa: ARG002
            return self

        def values(self, *args, **kwargs):  # noqa: ARG002
            return [
                {
                    "ts": datetime(2024, 1, 1, tzinfo=timezone.utc),
                    "open": 1,
                    "high": 2,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 100,
                }
            ]

    monkeypatch.setattr("runs.engine.Bar.objects", _DummyQS())

    class _Sym:
        ticker = "TEST"

    df = load_bars_dataframe(
        _Sym(),
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 12, 31, tzinfo=timezone.utc),
    )
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert captured["timeframe"] == "1d"
