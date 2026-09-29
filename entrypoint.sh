#!/bin/sh
set -e
flask db upgrade
# --workers 1: the weather-ingestion scheduler (app/scheduler.py) runs
# in-process via APScheduler. More than one worker would each start their
# own copy and duplicate every fetch, since there's no cross-process
# coordination.
exec gunicorn --bind "0.0.0.0:${PORT:-5000}" --workers 1 wsgi:app
