#!/usr/bin/env bash
# Upgrade the compose `db` service from Postgres 14 to 18 by dump and restore.
#
# Expects the layout from backend/compose.yaml: a `db` service with
#   ./volumes/postgres -> /var/lib/postgresql/data
#   ./volumes/backup   -> /var/backup
# and POSTGRES_VERSION=14... in .env next to the compose file. Any of the
# names docker compose looks for works (compose.yaml, compose.yml, ...).
#
# How to run it on a server (staging first, then production):
#   1. Copy this script into the directory that holds the compose file and .env.
#   2. Take your usual external backup or snapshot as an extra safety net.
#   3. bash upgrade-postgres-14-to-18.sh        (add --yes to skip the prompt)
#   4. Check the site.
#   5. A few days later remove the leftovers the script lists at the end.
#
# What it does:
#   1. Preflight checks. Nothing is changed if any of them fail.
#   2. Stops every service except db, so nothing writes during the dump.
#   3. Dumps roles and the postgres database to volumes/backup/pg14-upgrade-<ts>/
#      and records exact row counts for every table.
#   4. Stops db, renames volumes/postgres to volumes/postgres14_old, deletes
#      the throwaway db-test volume if there is one, sets
#      POSTGRES_VERSION=18 in .env and changes the data mount to
#      /var/lib/postgresql. The 18 image keeps its data in
#      /var/lib/postgresql/18/docker and refuses to start with the old mount.
#   5. Starts Postgres 18 on an empty data directory.
#   6. Restores the dump in a single transaction and rebuilds statistics.
#   7. Compares row counts with the ones from step 3.
#   8. Starts everything.
#
# If anything fails from step 4 on, the script puts the 14 data, .env and
# compose file back and starts the old setup again. The failed 18 data is kept
# in volumes/postgres18_failed for inspection. The dump folder is always kept.

set -Eeuo pipefail

DATA_DIR=volumes/postgres
OLD_DIR=volumes/postgres14_old
FAILED_DIR=volumes/postgres18_failed
DUMP_NAME=pg14-upgrade-$(date +%Y%m%d-%H%M%S)
DUMP_CONT=/var/backup/$DUMP_NAME        # inside the db container
DUMP_HOST=                              # same folder on the host, set in preflight

# pre:  nothing changed yet (app may be stopped)
# swap: data directory and config are being swapped; failure means rollback
# done: 18 is verified
PHASE=init
ASSUME_YES=0

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
die() { log "ERROR: $*"; exit 1; }

dc() { docker compose "$@"; }
# Host path mounted at $1 in the running db container.
mount_src() {
    docker inspect -f "{{range .Mounts}}{{if eq .Destination \"$1\"}}{{.Source}}{{end}}{{end}}" \
        "$(dc ps -q db)"
}
# Resolve symlinks via the parent; the data dir itself is usually not enterable.
phys() { echo "$(cd "$(dirname "$1")" && pwd -P)/$(basename "$1")"; }
# Run SQL in the db container and print bare values.
q() { dc exec -T db psql -U postgres -d postgres -XAtq -v ON_ERROR_STOP=1 -c "$1"; }

COUNTS_SQL="
SELECT format('%I.%I', table_schema, table_name) || ' ' ||
       (xpath('/row/c/text()', query_to_xml(
           format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
           false, true, '')))[1]::text
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1;"

LOCALE_SQL="SELECT pg_encoding_to_char(encoding) || ' ' || datcollate || ' ' || datctype
FROM pg_database WHERE datname = 'postgres';"

on_exit() {
    local status=$?
    trap - EXIT INT TERM
    [[ $status -eq 0 || $PHASE == "done" ]] && return
    set +e
    case $PHASE in
        pre)
            log "Failed before anything was changed. Starting all services again."
            dc up -d
            ;;
        swap)
            log "Failed during the upgrade. Rolling back to Postgres 14."
            dc down
            if [[ -d $OLD_DIR ]]; then
                if [[ -e $DATA_DIR ]]; then
                    rm -rf "$FAILED_DIR.prev" 2>/dev/null
                    [[ -e $FAILED_DIR ]] && mv "$FAILED_DIR" "$FAILED_DIR.prev"
                    mv "$DATA_DIR" "$FAILED_DIR"
                fi
                mv "$OLD_DIR" "$DATA_DIR"
            fi
            [[ -f .env.pg14.bak ]] && mv .env.pg14.bak .env
            [[ -f $CF.pg14.bak ]] && mv "$CF.pg14.bak" "$CF"
            dc up -d
            log "Rollback done. Postgres 14 is running on the original data."
            [[ -d $FAILED_DIR ]] && log "The failed 18 data is in $FAILED_DIR."
            ;;
    esac
    [[ -n $DUMP_HOST && -d $DUMP_HOST ]] && log "Dump and log: $DUMP_HOST"
    exit "$status"
}
trap on_exit EXIT
trap 'log "Interrupted."; exit 130' INT TERM

[[ ${1:-} == --yes ]] && ASSUME_YES=1

# ---------------------------------------------------------------- 1. preflight
log "1/8 Preflight checks"
# Same lookup order as docker compose. Not COMPOSE_FILE: compose reads that.
CF=
for f in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do
    [[ -f $f ]] && { CF=$f; break; }
done
[[ -n $CF && -f .env ]] || die "Run this from the directory with the compose file and .env."
[[ -z ${POSTGRES_VERSION:-} ]] || die "POSTGRES_VERSION is set in your shell and would override .env. Unset it first."
grep -Eq '^POSTGRES_VERSION=14' .env || die ".env does not have POSTGRES_VERSION=14..."
grep -Eq '^POSTGRES_PASSWORD=.+' .env || die "POSTGRES_PASSWORD is empty in .env. Postgres 18 needs it to initialise."
for p in "$OLD_DIR" .env.pg14.bak "$CF.pg14.bak"; do
    [[ ! -e $p ]] || die "$p already exists, maybe from an earlier run. Move it away first."
done
dc config db | grep -Eq 'target: /var/lib/postgresql/data$' \
    || die "The db service does not mount its data at /var/lib/postgresql/data."
[[ -n $(dc ps -q --status running db) ]] || die "The db service is not running. Start it with: docker compose up -d db"
# Read inside the container: the host user usually cannot enter the data dir.
[[ $(dc exec -T db cat /var/lib/postgresql/data/PG_VERSION) == 14 ]] || die "The db data directory is not a Postgres 14 cluster."
DATA_SRC=$(mount_src /var/lib/postgresql/data)
[[ -n $DATA_SRC && -d $DATA_DIR && $(phys "$DATA_SRC") == "$(phys "$DATA_DIR")" ]] \
    || die "db's data is mounted from '${DATA_SRC:-nowhere}', expected $(phys "$DATA_DIR")."
# The dump has to survive `docker compose down`, so it must go to a host mount.
BACKUP_SRC=$(mount_src /var/backup)
[[ -n $BACKUP_SRC ]] || die "db has no mount at /var/backup, so there is nowhere on the host to put the dump."
DUMP_HOST=$BACKUP_SRC/$DUMP_NAME

OTHER_DBS=$(q "SELECT string_agg(datname, ', ') FROM pg_database
               WHERE datname NOT IN ('postgres', 'template0', 'template1');")
[[ -z $OTHER_DBS ]] || die "Found other databases this script does not migrate: $OTHER_DBS"

DB_BYTES=$(q "SELECT pg_database_size('postgres');")
FREE_BYTES=$(( $(df -Pk volumes | awk 'NR == 2 {print $4}') * 1024 ))
(( FREE_BYTES > DB_BYTES * 2 )) \
    || die "Not enough free disk: $((FREE_BYTES / 1048576)) MB free, need $((DB_BYTES * 2 / 1048576)) MB."
LOCALE_BEFORE=$(q "$LOCALE_SQL")

PROJECT=$(dc config | sed -n 's/^name: //p')
DB_TEST_VOLUME=$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" \
    --filter label=com.docker.compose.volume=db-test)
OTHER_SERVICES=()
while IFS= read -r svc; do OTHER_SERVICES+=("$svc"); done < <(dc config --services | grep -vx db || true)

cat <<EOF

  Server version : $(q "SHOW server_version;")
  Database size  : $((DB_BYTES / 1048576)) MB  (free disk: $((FREE_BYTES / 1048576)) MB)
  Encoding/locale: $LOCALE_BEFORE
  Will stop      : ${OTHER_SERVICES[*]:-(no other services)}
  Dump folder    : $DUMP_HOST
  Test db volume : ${DB_TEST_VOLUME:-(none)} (deleted, the test runner recreates it)

  The site is down until the script finishes.

EOF
if (( ! ASSUME_YES )); then
    read -r -p "Type yes to start the upgrade: " answer
    [[ $answer == yes ]] || { log "Aborted, nothing changed."; exit 0; }
fi

# The backup dir is often root-owned, so let the container create the folder.
dc exec -T db sh -c "mkdir -p '$DUMP_CONT' && chown $(id -u):$(id -g) '$DUMP_CONT'"
[[ -d $DUMP_HOST && -w $DUMP_HOST ]] \
    || die "Created $DUMP_CONT in the container but cannot write to it on the host as $DUMP_HOST."
exec > >(tee -a "$DUMP_HOST/upgrade.log") 2>&1
PHASE=pre

# ------------------------------------------------------------- 2. stop the app
log "2/8 Stopping services: ${OTHER_SERVICES[*]:-(none)}"
if (( ${#OTHER_SERVICES[@]} )); then
    dc stop "${OTHER_SERVICES[@]}"
fi

# --------------------------------------------------------------------- 3. dump
log "3/8 Dumping to $DUMP_HOST"
dc exec -T db pg_dumpall -U postgres --globals-only -f "$DUMP_CONT/globals.sql"
dc exec -T db pg_dump -U postgres -Fc -f "$DUMP_CONT/postgres.dump" postgres
dc exec -T db pg_restore --list "$DUMP_CONT/postgres.dump" > /dev/null
q "$COUNTS_SQL" > "$DUMP_HOST/counts-before.txt"
log "    dump: $(du -h "$DUMP_HOST/postgres.dump" | cut -f1), tables: $(wc -l < "$DUMP_HOST/counts-before.txt")"

# ------------------------------------------------------- 4. swap data and config
log "4/8 Moving $DATA_DIR to $OLD_DIR and switching config to 18"
PHASE=swap
dc down
mv "$DATA_DIR" "$OLD_DIR"
# db-test only holds the test runner's throwaway database; 18 refuses its 14 data.
if [[ -n $DB_TEST_VOLUME ]]; then
    log "    removing test database volume $DB_TEST_VOLUME"
    docker volume rm "$DB_TEST_VOLUME" > /dev/null
fi
sed -i.pg14.bak -E 's/^POSTGRES_VERSION=14(.*)$/POSTGRES_VERSION=18\1/' .env
sed -i.pg14.bak -E 's#:/var/lib/postgresql/data(["'"'"' ]*)$#:/var/lib/postgresql\1#' "$CF"
grep -Eq '^POSTGRES_VERSION=18' .env || die "Could not update POSTGRES_VERSION in .env."
dc config db | grep -Eq 'image: postgres:18' || die "compose does not resolve db to postgres:18."
dc config db | grep -Eq 'target: /var/lib/postgresql$' || die "Could not change the db data mount in $CF."

# ---------------------------------------------------------- 5. start postgres 18
log "5/8 Starting Postgres 18"
dc up -d db
# TCP, not the socket: during initialisation the image runs a temporary server
# that only listens on the socket, so TCP answering means init is finished.
for _ in $(seq 120); do
    dc exec -T db pg_isready -q -h 127.0.0.1 -U postgres 2>/dev/null && break
    sleep 1
done
dc exec -T db pg_isready -q -h 127.0.0.1 -U postgres \
    || { dc logs --tail 40 db; die "Postgres 18 did not become ready within 120s."; }
NEW_VERSION=$(q "SHOW server_version;")
[[ $NEW_VERSION == 18* ]] || die "Expected Postgres 18, got $NEW_VERSION."
LOCALE_AFTER=$(q "$LOCALE_SQL")
[[ $LOCALE_AFTER == "$LOCALE_BEFORE" ]] \
    || die "Encoding/locale differ: 14 had '$LOCALE_BEFORE', 18 has '$LOCALE_AFTER'."
log "    running $NEW_VERSION"

# ------------------------------------------------------------------ 6. restore
log "6/8 Restoring"
# The postgres role and its password come from POSTGRES_PASSWORD when 18
# initialises. Skipping them also avoids carrying over an old md5 hash.
grep -Ev '^(CREATE|ALTER) ROLE postgres( |;)' "$DUMP_HOST/globals.sql" \
    | dc exec -T db psql -U postgres -d postgres -Xq -v ON_ERROR_STOP=1
dc exec -T db pg_restore -U postgres -d postgres --exit-on-error --single-transaction \
    "$DUMP_CONT/postgres.dump"
log "    rebuilding planner statistics"
dc exec -T db vacuumdb -U postgres --all --analyze-only --quiet

# ------------------------------------------------------------------- 7. verify
log "7/8 Comparing row counts"
q "$COUNTS_SQL" > "$DUMP_HOST/counts-after.txt"
diff "$DUMP_HOST/counts-before.txt" "$DUMP_HOST/counts-after.txt" \
    || die "Row counts differ between 14 and 18 (see diff above)."
log "    all $(wc -l < "$DUMP_HOST/counts-after.txt") tables match"
PHASE="done"

# -------------------------------------------------------------- 8. start all
log "8/8 Starting all services"
dc up -d || log "WARNING: docker compose up -d failed. The database is upgraded; fix and start the services by hand."

cat <<EOF

Upgrade to Postgres $NEW_VERSION finished.

Check the site. When you are sure everything works, remove the leftovers:
  sudo rm -rf $OLD_DIR
  rm .env.pg14.bak $CF.pg14.bak
  rm -r $DUMP_HOST      (or keep it as a backup)

To go back to 14 before removing them:
  docker compose down
  mv $DATA_DIR $FAILED_DIR && mv $OLD_DIR $DATA_DIR
  mv .env.pg14.bak .env && mv $CF.pg14.bak $CF
  docker compose up -d
EOF
