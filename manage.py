#!/usr/bin/env python
"""Django management entry point."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backtester.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Run `uv sync --dev` to install dependencies."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
