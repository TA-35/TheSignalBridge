#!/bin/bash
# Publishes basic-auth.js to CloudFront with the real credentials injected.
#
# The password is never stored in this repo. It is read from the environment
# and substituted into a copy of the function outside the working tree, so
# nothing secret is ever written to a tracked path:
#
#   SITE_AUTH_USER=thesignalbridge SITE_AUTH_PASSWORD='...' ./infra/cloudfront/publish.sh
#
# Rotating the password is the same command with a new value - no code edit.
# Run it from the repo root.
set -euo pipefail

PROFILE="${AWS_PROFILE:-readtheroom}"
FN=thesignalbridge-basic-auth
DIST=E1YGUMFRDSPNVG
SRC="infra/cloudfront/basic-auth.js"

: "${SITE_AUTH_USER:?set SITE_AUTH_USER (e.g. thesignalbridge)}"
: "${SITE_AUTH_PASSWORD:?set SITE_AUTH_PASSWORD}"

[ -f "$SRC" ] || { echo "run me from the repo root - $SRC not found" >&2; exit 1; }

TOKEN=$(printf '%s' "$SITE_AUTH_USER:$SITE_AUTH_PASSWORD" | base64 | tr -d '\n')

# Outside the repo, so a stray `git add -A` can never pick up the real token.
BUILD=$(mktemp -t basic-auth.XXXXXX.js)
trap 'rm -f "$BUILD"' EXIT
sed "s|__BASIC_AUTH_TOKEN__|$TOKEN|" "$SRC" > "$BUILD"

grep -q '__BASIC_AUTH_TOKEN__' "$BUILD" && {
  echo "substitution failed - placeholder still present" >&2; exit 1; }

echo "==> Uploading function"
if aws cloudfront describe-function --name "$FN" --profile "$PROFILE" >/dev/null 2>&1; then
    ETAG=$(aws cloudfront describe-function --name "$FN" --profile "$PROFILE" \
      --query 'ETag' --output text)
    aws cloudfront update-function --name "$FN" \
      --function-config Comment="Shared password for thesignalbridge.com",Runtime=cloudfront-js-2.0 \
      --function-code "fileb://$BUILD" --if-match "$ETAG" --profile "$PROFILE" \
      --query 'FunctionSummary.Status' --output text
else
    aws cloudfront create-function --name "$FN" \
      --function-config Comment="Shared password for thesignalbridge.com",Runtime=cloudfront-js-2.0 \
      --function-code "fileb://$BUILD" --profile "$PROFILE" \
      --query 'FunctionSummary.Status' --output text
fi

echo "==> Checking it challenges without credentials before going live"
EV=$(mktemp -t ev.XXXXXX.json)
trap 'rm -f "$BUILD" "$EV"' EXIT
printf '%s' '{"version":"1.0","context":{"eventType":"viewer-request"},"viewer":{"ip":"1.2.3.4"},"request":{"method":"GET","uri":"/","headers":{},"cookies":{},"querystring":{}}}' > "$EV"
ETAG=$(aws cloudfront describe-function --name "$FN" --profile "$PROFILE" --query 'ETag' --output text)
STATUS=$(aws cloudfront test-function --name "$FN" --if-match "$ETAG" --stage DEVELOPMENT \
  --event-object "fileb://$EV" --profile "$PROFILE" \
  --query 'TestResult.FunctionOutput' --output text | grep -o '"statusCode":[0-9]*' | head -1)
[ "$STATUS" = '"statusCode":401' ] || { echo "expected a 401 challenge, got: $STATUS" >&2; exit 1; }
echo "    401 confirmed"

echo "==> Publishing to LIVE"
ETAG=$(aws cloudfront describe-function --name "$FN" --profile "$PROFILE" --query 'ETag' --output text)
aws cloudfront publish-function --name "$FN" --if-match "$ETAG" --profile "$PROFILE" \
  --query 'FunctionSummary.Status' --output text

# Only needed the first time; a republish updates every distribution already
# associated with the function.
ASSOCIATED=$(aws cloudfront get-distribution-config --id "$DIST" --profile "$PROFILE" \
  --query 'DistributionConfig.DefaultCacheBehavior.FunctionAssociations.Quantity' --output text)
if [ "$ASSOCIATED" = "0" ]; then
    echo "==> First run - attaching the function to $DIST"
    CFG=$(mktemp -t distcfg.XXXXXX.json)
    NEW=$(mktemp -t distnew.XXXXXX.json)
    trap 'rm -f "$BUILD" "$EV" "$CFG" "$NEW"' EXIT
    aws cloudfront get-distribution-config --id "$DIST" --profile "$PROFILE" > "$CFG"
    DETAG=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['ETag'])" "$CFG")
    ARN=$(aws cloudfront describe-function --name "$FN" --profile "$PROFILE" \
      --query 'FunctionSummary.FunctionMetadata.FunctionARN' --output text)
    python3 - "$CFG" "$NEW" "$ARN" <<'PY'
import json, sys
src, dst, arn = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open(src))['DistributionConfig']
cfg['DefaultCacheBehavior']['FunctionAssociations'] = {
    'Quantity': 1,
    'Items': [{'FunctionARN': arn, 'EventType': 'viewer-request'}],
}
json.dump(cfg, open(dst, 'w'))
PY
    aws cloudfront update-distribution --id "$DIST" --distribution-config "file://$NEW" \
      --if-match "$DETAG" --profile "$PROFILE" --query 'Distribution.Status' --output text
fi

echo
echo "==> Done. Edges take a few minutes to catch up."
echo "    curl -sI https://www.thesignalbridge.com/ | head -3     # expect 401"
