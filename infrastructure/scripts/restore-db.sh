#!/usr/bin/env bash
# =============================================================================
# PostgreSQL restore.
#
# Destructive: drops and recreates the target database. Requires an explicit
# confirmation unless RESTORE_ASSUME_YES=1 is set (used by the automated
# restore drill in CI).
# =============================================================================
set -euo pipefail

DUMP_FILE="${1:-}"
COMPOSE="${COMPOSE:-docker compose}"
DB_USER="${POSTGRES_USER:-murasfood}"
DB_NAME="${POSTGRES_DB:-murasfood}"

if [[ -z "${DUMP_FILE}" ]]; then
  echo "Usage: restore-db.sh <path/to/murasfood-*.dump.gz>" >&2
  exit 2
fi

if [[ ! -f "${DUMP_FILE}" ]]; then
  echo "!! Dump not found: ${DUMP_FILE}" >&2
  exit 1
fi

echo "!! This DROPS the database '${DB_NAME}' and replaces it with ${DUMP_FILE}"
if [[ "${RESTORE_ASSUME_YES:-0}" != "1" ]]; then
  read -r -p "Type the database name to confirm: " confirmation
  if [[ "${confirmation}" != "${DB_NAME}" ]]; then
    echo "Aborted." >&2
    exit 1
  fi
fi

echo "==> Terminating active connections"
${COMPOSE} exec -T postgres psql --username="${DB_USER}" --dbname=postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();
SQL

echo "==> Recreating database"
${COMPOSE} exec -T postgres psql --username="${DB_USER}" --dbname=postgres -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS "${DB_NAME}";
CREATE DATABASE "${DB_NAME}" OWNER "${DB_USER}";
SQL

echo "==> Restoring"
gunzip -c "${DUMP_FILE}" \
  | ${COMPOSE} exec -T postgres pg_restore \
      --username="${DB_USER}" \
      --dbname="${DB_NAME}" \
      --no-owner \
      --no-privileges \
      --exit-on-error

echo "==> Verifying"
${COMPOSE} exec -T postgres psql --username="${DB_USER}" --dbname="${DB_NAME}" -tAc \
  "SELECT count(*) || ' tables restored' FROM information_schema.tables WHERE table_schema='public';"

echo "==> Done. Run migrations to confirm the schema is current: make migrate"
