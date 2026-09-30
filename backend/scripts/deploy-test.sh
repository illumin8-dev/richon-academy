#!/usr/bin/env bash
# Run from an authenticated GCP Cloud Shell. Never run with bash -x.
set +x
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-richon-academy}"
REGION="asia-southeast1"
SERVICE="richon-backend-test"
RUNTIME="richon-backend@${PROJECT_ID}.iam.gserviceaccount.com"
BUILDER="richon-build@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET="richon-database-url"
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for command in gcloud curl python3; do
  command -v "$command" >/dev/null || { echo "Required command missing: $command"; exit 1; }
done

echo "Project: $PROJECT_ID / Region: $REGION / Private service: $SERVICE"
echo "This creates a build identity (roles/run.builder), build artifacts, and a private test service."
echo "Runtime: 1 CPU / 512 MiB / min 0 / max 1. Usage/build/storage charges can apply."
echo "No frontend changes, no DB tables/data changes, and no secret values are printed."
read -r -p "Continue? Type YES: " confirmation
[[ "$confirmation" == "YES" ]] || { echo "Cancelled."; exit 0; }

# Read metadata only. The secret payload never passes through this script.
gcloud projects describe "$PROJECT_ID" --format='value(projectId)' >/dev/null
gcloud iam service-accounts describe "$RUNTIME" --project="$PROJECT_ID" >/dev/null
VERSION_RESOURCE="$(gcloud secrets versions list "$SECRET" --project="$PROJECT_ID" \
  --filter='state=ENABLED' --sort-by='~createTime' --limit=1 --format='value(name)')"
VERSION="${VERSION_RESOURCE##*/}"
[[ "$VERSION" =~ ^[0-9]+$ ]] || { echo "No enabled secret version found."; exit 1; }
echo "Pinning secret version: $VERSION (value not displayed)."

EXISTING="$(gcloud run services list --project="$PROJECT_ID" --region="$REGION" \
  --filter="metadata.name=$SERVICE" --format='value(metadata.name)')"
if [[ -n "$EXISTING" ]]; then
  POLICY="$(gcloud run services get-iam-policy "$SERVICE" --project="$PROJECT_ID" \
    --region="$REGION" --format=json)"
  if printf '%s' "$POLICY" | grep -Eq 'allUsers|allAuthenticatedUsers'; then
    echo "An existing service has broad invocation access. Stop and review it before deploying."
    exit 1
  fi
fi

BUILD_IDENTITY="$(gcloud iam service-accounts list --project="$PROJECT_ID" \
  --filter="email=$BUILDER" --format='value(email)')"
if [[ -z "$BUILD_IDENTITY" ]]; then
  gcloud iam service-accounts create richon-build --project="$PROJECT_ID" \
    --display-name='Richon build only'
fi
# Keep build permissions separate from the runtime's single-secret permission.
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$BUILDER" --role='roles/run.builder' \
  --condition=None --quiet >/dev/null

echo "Building only backend/ and deploying. New IAM grants can take a few minutes to propagate."
gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" --region="$REGION" \
  --source="$BACKEND_DIR" \
  --build-service-account="projects/$PROJECT_ID/serviceAccounts/$BUILDER" \
  --service-account="$RUNTIME" \
  --set-secrets="DATABASE_URL=$SECRET:$VERSION" \
  --no-allow-unauthenticated --invoker-iam-check \
  --ingress=all --cpu=1 --memory=512Mi --cpu-throttling \
  --min=0 --max=1 --min-instances=0 --max-instances=1 \
  --concurrency=4 --timeout=30 --port=8080 --quiet

URL="$(gcloud run services describe "$SERVICE" --project="$PROJECT_ID" \
  --region="$REGION" --format='value(status.url)')"
[[ "$URL" == https://* ]] || { echo "Could not read service URL."; exit 1; }

# Prove that IAM blocks requests before accepting a successful deployment.
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$URL/health")"
[[ "$CODE" == 401 || "$CODE" == 403 ]] || {
  echo "Unexpected unauthenticated status: $CODE. Review IAM; do not expose this service."; exit 1;
}
echo "Unauthenticated request blocked: HTTP $CODE"

TOKEN="$(gcloud auth print-identity-token)"
for endpoint in health health/db; do
  echo "Checking /$endpoint"
  RESULT="$(curl -fsS --max-time 40 -H "Authorization: Bearer $TOKEN" "$URL/$endpoint")" || {
    unset TOKEN
    echo "Check failed. Do not paste secret values. Review secret format and permissions privately."
    echo "The service may already be deployed even though this check failed."
    exit 1
  }
  printf '%s' "$RESULT" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("status")=="ok", "Unexpected response"'
  printf '%s\n' "$RESULT"
done
unset TOKEN
echo "PASS: private Cloud Run service and read-only Neon query confirmed."
echo "Service URL: $URL (browser access without IAM authentication is intentionally blocked)."
