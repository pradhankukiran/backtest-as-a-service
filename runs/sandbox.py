"""Strategy code loader.

Phase 3 sandbox: an AST pre-pass that rejects obvious unsafe imports and
dangerous builtin names, plus plain `exec` into a fresh namespace. This is a
sanity layer, not a security boundary — the user (single operator) is trusted.

Phase 6 will lift strategy execution into a separate worker queue running in a
Docker container with no network or DB credentials; THAT is the real isolation
layer. The `audit_strategy_source` function here just catches accidental misuse
("oh, I imported `os` to read a file") with a clear error early.
"""

from __future__ import annotations

import ast
from typing import Any

from backtesting import Strategy

ALLOWED_TOP_LEVEL_MODULES = frozenset(
    {
        "backtesting",
        "pandas",
        "numpy",
        "math",
        "statistics",
        "decimal",
        "datetime",
        "collections",
        "itertools",
        "functools",
    }
)

DENIED_BUILTIN_NAMES = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "input",
        "breakpoint",
    }
)


class StrategySandboxError(Exception):
    pass


def _check_imports(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_TOP_LEVEL_MODULES:
                    raise StrategySandboxError(f"import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root and root not in ALLOWED_TOP_LEVEL_MODULES:
                raise StrategySandboxError(f"import from not allowed: {module}")


def _check_builtin_names(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in DENIED_BUILTIN_NAMES:
            raise StrategySandboxError(f"builtin name not allowed: {node.id}")


def audit_strategy_source(source: str) -> ast.Module:
    """Parse user code and reject obvious red flags. Raises StrategySandboxError."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise StrategySandboxError(f"syntax error: {exc}") from exc
    _check_imports(tree)
    _check_builtin_names(tree)
    return tree


def load_strategy_class(source: str, entrypoint: str = "Strategy") -> type:
    """Audit, compile, and exec `source`; return the named Strategy subclass.

    If `entrypoint` is the default "Strategy" and the module defines exactly
    one Strategy subclass, that class is returned (so users don't have to name
    the class exactly "Strategy").
    """
    audit_strategy_source(source)

    namespace: dict[str, Any] = {}
    try:
        compiled = compile(source, "<strategy>", "exec")
        exec(compiled, namespace)  # noqa: S102
    except Exception as exc:
        raise StrategySandboxError(f"strategy load failed: {exc}") from exc

    cls = namespace.get(entrypoint)
    if cls is None:
        candidates = [
            value
            for value in namespace.values()
            if isinstance(value, type) and issubclass(value, Strategy) and value is not Strategy
        ]
        if len(candidates) == 1:
            cls = candidates[0]
        elif len(candidates) > 1:
            names = [c.__name__ for c in candidates]
            raise StrategySandboxError(
                f"multiple Strategy subclasses; specify entrypoint: {names}"
            )
        else:
            raise StrategySandboxError(
                f"no class named {entrypoint!r} and no Strategy subclass found"
            )

    if not (isinstance(cls, type) and issubclass(cls, Strategy)):
        raise StrategySandboxError(f"{entrypoint!r} is not a backtesting.Strategy subclass")
    return cls
