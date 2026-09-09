#!/bin/bash
set -e

# Uvicorn flags shared by both halves of the ASGI deployment.
#
# --forwarded-allow-ips: --proxy-headers alone only trusts 127.0.0.1, and behind
# traefik the peer is another container, so every request would be attributed to
# the proxy's address. Nothing but traefik can reach these ports.
# --ws-max-size: one setting for what daphne split into --websocket-max-message-size
# and --websocket-max-frame-size. VOTEIT_APP_STATE_BUNDLE_BYTES stays well under it.
UVICORN_COMMON=(
  --host 0.0.0.0 --port 8000
  --proxy-headers --forwarded-allow-ips='*'
  --ws-max-size 5242880
)

if [[ "$1" == "run" ]]; then
  echo "Starting uvicorn (http)"
  exec ./wait-for-it.sh db:5432 -s -- \
    ./wait-for-it.sh redis:6379 -s -- \
    uvicorn "${UVICORN_COMMON[@]}" --access-log "${@:2}" project.asgi:application
elif [[ "$1" == "run-ws" ]]; then
  # Same image and same ASGI application as `run`; traefik decides which process
  # gets which path. What differs is the tuning: websockets are long-lived, so
  # they need keepalive pings and a longer window to drain on shutdown, and the
  # access log would otherwise emit one line per connection for no benefit.
  echo "Starting uvicorn (websocket)"
  exec ./wait-for-it.sh db:5432 -s -- \
    ./wait-for-it.sh redis:6379 -s -- \
    uvicorn "${UVICORN_COMMON[@]}" --no-access-log \
      --ws-ping-interval 10 --ws-ping-timeout 20 \
      --timeout-graceful-shutdown 20 \
      "${@:2}" project.asgi:application
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
