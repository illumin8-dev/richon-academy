#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.pages-dist"

rm -rf "$OUT"
mkdir -p "$OUT/frontend/shared"

PUBLIC_ROOT_FILES=(
  index.html
  apply.html
  privacy.html
  terms.html
  signup-guide.html
)

for relative in "${PUBLIC_ROOT_FILES[@]}"; do
  source="$ROOT/$relative"
  [[ -f "$source" && ! -L "$source" ]] || {
    echo "Unsafe or missing public file: $relative" >&2
    exit 1
  }
  cp "$source" "$OUT/$relative"
done

for relative in site.css site.js login.js; do
  source="$ROOT/frontend/shared/$relative"
  [[ -f "$source" && ! -L "$source" ]] || {
    echo "Unsafe or missing shared public asset: $relative" >&2
    exit 1
  }
  cp "$source" "$OUT/frontend/shared/$relative"
done

[[ -d "$ROOT/assets" ]] || {
  echo "Missing public assets directory" >&2
  exit 1
}
if find "$ROOT/assets" -type l -print -quit | grep -q .; then
  echo "Symlinks are not allowed in public assets" >&2
  exit 1
fi
cp -R "$ROOT/assets" "$OUT/assets"

for private in backend .github edge ops docs preview tools; do
  [[ ! -e "$OUT/$private" ]] || {
    echo "Private repository path leaked into Pages output: $private" >&2
    exit 1
  }
done

[[ -f "$OUT/index.html" ]] || {
  echo "Pages output must contain top-level index.html" >&2
  exit 1
}

echo "PASS: Cloudflare Pages output contains only allowlisted public files"
