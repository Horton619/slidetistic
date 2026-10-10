#!/usr/bin/env bash
# Upload the five signing/notarization secrets from release-secrets.local.txt to GitHub Actions.
# Follows the global CLAUDE.md gotchas: pipe values with no --body flag, single-line base64 for the
# certificate, and check each secret landed (gh can exit 0 on a failed set).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO=Horton619/slidetistic
FILE=release-secrets.local.txt
[ -f "$FILE" ] || { echo "Missing $FILE" >&2; exit 1; }

get() { grep -E "^$1=" "$FILE" | head -1 | cut -d= -f2-; }

for key in CSC_P12_PATH CSC_KEY_PASSWORD APPLE_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_TEAM_ID; do
  [ -n "$(get "$key")" ] || { echo "$key is blank in $FILE" >&2; exit 1; }
done
P12=$(get CSC_P12_PATH)
[ -f "$P12" ] || { echo "Certificate not found: $P12" >&2; exit 1; }
openssl pkcs12 -in "$P12" -passin "pass:$(get CSC_KEY_PASSWORD)" -noout -legacy 2>/dev/null \
  || openssl pkcs12 -in "$P12" -passin "pass:$(get CSC_KEY_PASSWORD)" -noout 2>/dev/null \
  || { echo "CSC_KEY_PASSWORD doesn't open $P12" >&2; exit 1; }

check() {
  gh secret list --repo "$REPO" | grep -q "^$1[[:space:]]" || { echo "$1 did not land" >&2; exit 1; }
  echo "  ✓ $1"
}

echo "Setting secrets on ${REPO}..."
openssl base64 -A -in "$P12" | tr -d '\n' | gh secret set CSC_LINK --repo "$REPO"; check CSC_LINK
for key in CSC_KEY_PASSWORD APPLE_ID APPLE_APP_SPECIFIC_PASSWORD APPLE_TEAM_ID; do
  printf '%s' "$(get "$key")" | gh secret set "$key" --repo "$REPO"; check "$key"
done
echo "All five set. Delete $FILE now."
