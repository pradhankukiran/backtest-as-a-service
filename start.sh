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
    exec celery -A backtester worker -Q default -n default@%h \
      --loglevel=info --concurrency=4
    ;;
  worker-and-beat)
    # Runs both the default-queue worker and the beat scheduler in one
    # container. Use on resource-constrained deploys where a separate beat
    # service isn't practical. Only ONE worker-and-beat instance must run
    # cluster-wide so the schedule doesn't double-fire.
    exec celery -A backtester worker -Q default -n default@%h \
      --beat --loglevel=info --concurrency=4
    ;;
  worker-untrusted)
    # Consumes ONLY the 'untrusted' queue. User-supplied strategy code runs
    # here. --max-tasks-per-child=1 means each task runs in a fresh process,
    # so leaked file descriptors / globals can't carry between user runs.
    exec celery -A backtester worker -Q untrusted -n untrusted@%h \
      --loglevel=info --concurrency=2 --max-tasks-per-child=1
    ;;
  beat)
    exec celery -A backtester beat --loglevel=info
    ;;
  *)
    echo "Unknown BACKTESTER_ROLE: ${ROLE} (expected web|worker|worker-untrusted|beat)" >&2
    exit 1
    ;;
esac
