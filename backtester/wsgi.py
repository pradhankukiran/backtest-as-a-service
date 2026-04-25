"""WSGI entry point for backtest-as-a-service."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backtester.settings")

application = get_wsgi_application()
