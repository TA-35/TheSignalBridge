#!/bin/bash
# Takes the shared password off the website by detaching basic-auth.js from
# the distribution. The function itself stays in CloudFront, so putting the
# password back is publish.sh again, which re-attaches it when nothing is:
#
#   ./infra/cloudfront/remove.sh
#
# Run it from the repo root. Only this function's association is removed;
# anything else attached to the distribution is left as it is.
set -euo pipefail

PROFILE="${AWS_PROFILE:-readtheroom}"
FN=thesignalbridge-basic-auth
DIST=E1YGUMFRDSPNVG

CFG=$(mktemp -t distcfg.XXXXXX.json)
NEW=$(mktemp -t distnew.XXXXXX.json)
trap 'rm -f "$CFG" "$NEW"' EXIT
aws cloudfront get-distribution-config --id "$DIST" --profile "$PROFILE" > "$CFG"
DETAG=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['ETag'])" "$CFG")

REMOVED=$(python3 - "$CFG" "$NEW" "$FN" <<'PY'
import json, sys
src, dst, name = sys.argv[1:]
cfg = json.load(open(src))['DistributionConfig']
behaviours = [cfg['DefaultCacheBehavior']] + cfg.get('CacheBehaviors', {}).get('Items', [])
removed = 0
for behaviour in behaviours:
    items = behaviour.get('FunctionAssociations', {}).get('Items', [])
    kept = [i for i in items if not i['FunctionARN'].endswith('function/' + name)]
    removed += len(items) - len(kept)
    behaviour['FunctionAssociations'] = {'Quantity': len(kept), **({'Items': kept} if kept else {})}
json.dump(cfg, open(dst, 'w'))
print(removed)
PY
)

if [ "$REMOVED" = "0" ]; then
    echo "The password function is not attached - the site is already public."
    exit 0
fi

echo "==> Detaching the password function from $DIST"
aws cloudfront update-distribution --id "$DIST" --distribution-config "file://$NEW" \
  --if-match "$DETAG" --profile "$PROFILE" --query 'Distribution.Status' --output text

echo
echo "==> Done. Edges take a few minutes to catch up."
echo "    curl -sI https://www.thesignalbridge.com/ | head -3     # expect 200"
