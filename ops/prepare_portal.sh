#!/usr/bin/env bash
# Explicit owner invocation. No live IAM public grants or deployment trust changes.
set +x
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$(mktemp -d "${TMPDIR:-/tmp}/richon-portal-venv.XXXXXX")"
trap 'rm -rf -- "$VENV"' EXIT
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
test -s "$SSL_CERT_FILE"
export PYTHONDONTWRITEBYTECODE=1
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check 'psycopg[binary]==3.3.4'
"$VENV/bin/python" "$ROOT/ops/prepare_portal.py"
