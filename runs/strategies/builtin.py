"""Built-in example strategies. Source kept as a string so it can be loaded by
the sandbox just like user-supplied strategies (no special-case path).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinStrategy:
    name: str
    slug: str
    description: str
    entrypoint: str
    params_schema: dict
    code: str


SMA_CROSSOVER = BuiltinStrategy(
    name="SMA Crossover",
    slug="sma-crossover",
    description=(
        "Buy when the short SMA crosses above the long SMA; close the position "
        "when it crosses back below. Classic trend-following baseline."
    ),
    entrypoint="SmaCross",
    params_schema={
        "sma_short": {"type": "int", "default": 10, "min": 2, "max": 200},
        "sma_long": {"type": "int", "default": 30, "min": 5, "max": 400},
    },
    code='''\
import pandas as pd
from backtesting import Strategy
from backtesting.lib import crossover


def SMA(values, n):
    return pd.Series(values).rolling(n).mean()


class SmaCross(Strategy):
    sma_short = 10
    sma_long = 30

    def init(self):
        close = self.data.Close
        self.sma_s = self.I(SMA, close, self.sma_short)
        self.sma_l = self.I(SMA, close, self.sma_long)

    def next(self):
        if crossover(self.sma_s, self.sma_l):
            self.buy()
        elif crossover(self.sma_l, self.sma_s):
            self.position.close()
''',
)


BUILTINS: list[BuiltinStrategy] = [SMA_CROSSOVER]
