"""ASGI entry point for backtest-as-a-service."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backtester.settings")

application = get_asgi_application()
