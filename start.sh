#!/bin/sh
set -eu

ROLE="${BACKTESTER_ROLE:-web}"
PORT="${PORT:-8000}"

case "$ROLE" in
  web)
    python manage.py migrate --noinput
    exec gunicorn backtester.wsgi:application --bind "0.0.0.0:${PORT}"
    ;;
  worker)
    exec celery -A backtester worker --loglevel=info --concurrency=2
    ;;
  beat)
    exec celery -A backtester beat --loglevel=info
    ;;
  *)
    echo "Unknown BACKTESTER_ROLE: ${ROLE} (expected web|worker|beat)" >&2
    exit 1
    ;;
esac
