"""Celery application for backtest-as-a-service."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backtester.settings")

app = Celery("backtester")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
