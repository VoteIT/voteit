#!/bin/bash
set -e
#find /data  -not -user voteit -exec chown voteit:voteit {} \+

if [[ "$1" == "run" ]]; then
  echo "Starting Daphne"
  exec ./wait-for-it.sh db:5432 -s -- \
    ./wait-for-it.sh redis:6379 -s -- \
    daphne --access-log - -p 8000 -b 0.0.0.0 --ping-interval 10 --proxy-headers voteit_project.routing:application
elif [[ "$1" == "worker" ]]; then
  if [[ ! $2 ]]; then
    $2 = default
    echo "Queue set to default"
  fi
  echo "Starting worker with scheduler and queue(s) " "${@:2}"
  exec ./wait-for-it.sh db:5432 -s -- \
    ./wait-for-it.sh redis:6379 -s -- \
    ./manage.py rqworker --with-scheduler "${@:2}"
elif [[ "$1" == "shell" ]]; then
  exec ./manage.py shell "${@:2}"
elif [[ "$1" == "manage" ]]; then
  exec ./manage.py "${@:2}"
else
  #Something else?
  exec "$@"
fi
