"""Parameter-sweep helpers: grid expansion + child-run materialization."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Iterator
from typing import Any


class GridError(ValueError):
    pass


def _expand_value_spec(name: str, spec: Any) -> list:
    """Turn one grid entry into a concrete list of values.

    Supports:
        [1, 2, 3]                                  -> [1, 2, 3]
        {"start": 5, "stop": 30, "step": 5}        -> [5, 10, 15, 20, 25, 30]
        scalar                                     -> [scalar]
    """
    if isinstance(spec, list):
        if not spec:
            raise GridError(f"empty list for parameter {name!r}")
        return list(spec)
    if isinstance(spec, dict):
        try:
            start = spec["start"]
            stop = spec["stop"]
        except KeyError as exc:
            raise GridError(f"range spec for {name!r} needs 'start' and 'stop'") from exc
        step = spec.get("step", 1)
        if step == 0:
            raise GridError(f"step must be non-zero for {name!r}")
        values: list = []
        if step > 0:
            value = start
            while value <= stop:
                values.append(value)
                value = round(value + step, 12) if isinstance(value, float) else value + step
        else:
            value = start
            while value >= stop:
                values.append(value)
                value = round(value + step, 12) if isinstance(value, float) else value + step
        if not values:
            raise GridError(f"empty range for {name!r}: {spec}")
        return values
    return [spec]


def expand_grid(grid: dict[str, Any]) -> list[dict[str, Any]]:
    """Cartesian product of all parameter axes. Returns a deterministic list of
    dicts (sorted by key, then by value)."""
    if not grid:
        return [{}]
    keys = sorted(grid.keys())
    value_lists: list[list] = [_expand_value_spec(key, grid[key]) for key in keys]
    combos: list[dict[str, Any]] = []
    for combo in itertools.product(*value_lists):
        combos.append(dict(zip(keys, combo)))
    return combos


def grid_size(grid: dict[str, Any]) -> int:
    """How many child runs would `expand_grid(grid)` produce?"""
    if not grid:
        return 1
    total = 1
    for key in grid:
        total *= len(_expand_value_spec(key, grid[key]))
    return total


def iter_combos(grid: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Streaming alternative to expand_grid for very large grids."""
    if not grid:
        yield {}
        return
    keys = sorted(grid.keys())
    value_lists = [_expand_value_spec(key, grid[key]) for key in keys]
    for combo in itertools.product(*value_lists):
        yield dict(zip(keys, combo))


def merge_params(base: dict[str, Any], combo: Iterable[tuple[str, Any]] | dict[str, Any]) -> dict:
    """Combine the sweep's base_params with one combo."""
    merged = dict(base)
    if isinstance(combo, dict):
        merged.update(combo)
    else:
        merged.update(dict(combo))
    return merged
