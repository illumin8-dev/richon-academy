#!/usr/bin/env bash
set +x
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$(mktemp -d "${TMPDIR:-/tmp}/richon-login-venv.XXXXXX")"
trap 'rm -rf -- "$VENV"' EXIT
export PYTHONDONTWRITEBYTECODE=1 CLOUDSDK_CORE_LOG_HTTP=false
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --disable-pip-version-check --quiet 'psycopg[binary]==3.3.4'
cd "$ROOT"
"$VENV/bin/python" -B ops/prepare_login_release.py "$@"
