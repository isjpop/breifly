#!/bin/sh
# Apply pending database migrations, then run the container command.
set -e
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  flask --app app.wsgi db upgrade
fi
exec "$@"
