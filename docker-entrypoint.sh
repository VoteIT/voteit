#!/bin/bash
set -e

if [[ "$1" == "run" ]]; then
  echo "Starting Daphne"
  exec ./wait-for-it.sh db:5432 -s -- \
    ./wait-for-it.sh redis:6379 -s -- \
    daphne --access-log - -p 8000 -b 0.0.0.0 --ping-interval 10 --proxy-headers --websocket-max-message-size 5242880 --websocket-max-frame-size 5242880 project.asgi:application
elif [[ "$1" == "worker" ]]; then
  QUEUES=("${@:2}")
  if [[ ${#QUEUES[@]} -eq 0 ]]; then
    QUEUES=("default")
    echo "Queue set to default"
  fi
  echo "Starting worker with scheduler and queue(s): ${QUEUES[*]}"
  exec ./wait-for-it.sh db:5432 -s -- \
    ./wait-for-it.sh redis:6379 -s -- \
    ./manage.py rqworker --with-scheduler "${QUEUES[@]}"
elif [[ "$1" == "shell" ]]; then
  exec ./manage.py shell "${@:2}"
elif [[ "$1" == "manage" ]]; then
  exec ./manage.py "${@:2}"
else
  #Something else?
  exec "$@"
fi
