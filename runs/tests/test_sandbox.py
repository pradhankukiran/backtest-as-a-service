"""Tests for the strategy sandbox loader."""

from __future__ import annotations

import pytest
from backtesting import Strategy

from runs.sandbox import StrategySandboxError, audit_strategy_source, load_strategy_class
from runs.strategies.builtin import SMA_CROSSOVER


def test_audit_rejects_disallowed_import():
    src = "import os\n"
    with pytest.raises(StrategySandboxError, match="import not allowed"):
        audit_strategy_source(src)


def test_audit_rejects_disallowed_from_import():
    src = "from subprocess import run\n"
    with pytest.raises(StrategySandboxError, match="import from not allowed"):
        audit_strategy_source(src)


def test_audit_rejects_eval_name():
    src = "x = eval('1+1')\n"
    with pytest.raises(StrategySandboxError, match="builtin name not allowed: eval"):
        audit_strategy_source(src)


def test_audit_allows_backtesting_imports():
    src = (
        "from backtesting import Strategy\n"
        "from backtesting.lib import crossover\n"
        "import pandas as pd\n"
        "import numpy as np\n"
    )
    audit_strategy_source(src)


def test_load_strategy_class_returns_subclass():
    cls = load_strategy_class(SMA_CROSSOVER.code, entrypoint=SMA_CROSSOVER.entrypoint)
    assert isinstance(cls, type)
    assert issubclass(cls, Strategy)
    assert cls.__name__ == "SmaCross"


def test_load_strategy_class_auto_detects_single_subclass():
    src = (
        "from backtesting import Strategy\n"
        "class MyStrat(Strategy):\n"
        "    def init(self):\n"
        "        pass\n"
        "    def next(self):\n"
        "        pass\n"
    )
    cls = load_strategy_class(src)
    assert cls.__name__ == "MyStrat"


def test_load_strategy_class_rejects_when_no_subclass_found():
    src = "x = 1\n"
    with pytest.raises(StrategySandboxError, match="no class named"):
        load_strategy_class(src)
