#!/usr/bin/env bash
# Cloud Shell only. Do not run with bash -x; never print a DB URL.
set +x
set -euo pipefail
PROJECT_ID="${PROJECT_ID:-richon-academy}"
SECRET="richon-database-url"
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for command in gcloud python3; do
  command -v "$command" >/dev/null || { echo "Missing command: $command"; exit 1; }
done
VERSION_RESOURCE="$(gcloud secrets versions list "$SECRET" --project="$PROJECT_ID" \
  --filter='state=ENABLED' --sort-by='~createTime' --limit=1 --format='value(name)')"
VERSION="${VERSION_RESOURCE##*/}"
[[ "$VERSION" =~ ^[0-9]+$ ]] || { echo "No enabled secret version found."; exit 1; }
echo "Target: $PROJECT_ID / secret $SECRET / version $VERSION (value not shown)."
echo "This creates richon.courses, richon.orders and the migration ledger in that DB."
echo "No course, price, customer or test order is added. No server/frontend deployment occurs."
echo "Verify privately that this secret points to the Richon TEST database, not another site's DB."
read -r -p "Apply schema changes? Type CREATE: " confirmation
[[ "$confirmation" == CREATE ]] || { echo "Cancelled."; exit 0; }
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/richon-orders.XXXXXXXX")"
cleanup() { unset DATABASE_URL; rm -rf -- "$WORKDIR"; }
trap cleanup EXIT
python3 -m venv "$WORKDIR/venv"
"$WORKDIR/venv/bin/python" -m pip install --disable-pip-version-check -r "$BACKEND_DIR/requirements.txt"
# Obtain the secret only after package installation. It is never an argument,
# log entry, persisted .env file, shell history value or frontend/GitHub content.
DATABASE_URL="$(gcloud secrets versions access "$VERSION" --secret="$SECRET" --project="$PROJECT_ID")"
export DATABASE_URL
"$WORKDIR/venv/bin/python" "$BACKEND_DIR/migrate_orders.py" --apply
