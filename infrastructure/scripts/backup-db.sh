#!/usr/bin/env bash
# =============================================================================
# PostgreSQL backup.
#
# Writes a gzipped custom-format dump and prunes anything older than the
# retention window. A backup is NOT considered implemented until a restore has
# actually been exercised — see restore-db.sh and docs/deployment/README.md.
# =============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-infrastructure/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
COMPOSE="${COMPOSE:-docker compose}"
DB_USER="${POSTGRES_USER:-murasfood}"
DB_NAME="${POSTGRES_DB:-murasfood}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="${BACKUP_DIR}/murasfood-${timestamp}.dump.gz"

mkdir -p "${BACKUP_DIR}"

echo "==> Dumping ${DB_NAME} to ${target}"
${COMPOSE} exec -T postgres pg_dump \
  --username="${DB_USER}" \
  --dbname="${DB_NAME}" \
  --format=custom \
  --no-owner \
  --no-privileges \
  | gzip -9 > "${target}"

# A zero-byte dump means the pipeline failed silently; fail loudly instead.
if [[ ! -s "${target}" ]]; then
  echo "!! Backup is empty — aborting" >&2
  rm -f "${target}"
  exit 1
fi

echo "==> Wrote $(du -h "${target}" | cut -f1)"

# Optional off-server copy. Backups on the same machine as the database do not
# survive the failure mode they exist for.
if [[ -n "${BACKUP_S3_TARGET:-}" ]]; then
  echo "==> Uploading to ${BACKUP_S3_TARGET}"
  aws s3 cp "${target}" "${BACKUP_S3_TARGET}/" --only-show-errors
fi

echo "==> Pruning dumps older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -name 'murasfood-*.dump.gz' -mtime "+${RETENTION_DAYS}" -delete

echo "==> Done"
