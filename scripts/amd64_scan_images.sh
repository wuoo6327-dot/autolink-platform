#!/usr/bin/env bash
# Full vulnerability scan of isolated image archives; no Docker socket mount.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ "$(uname -m)" == x86_64 && "$ROOT" == /home/admin/autolink-global-seo-qa-* ]] || { echo 'Requires the named AMD64 QA checkout' >&2; exit 2; }
SCAN='aquasec/trivy@sha256:9db099105405c648166e6b94155eb32f8da12673cf1f455207f7385cc9a77283'
OUT="$ROOT/qa-scan"
mkdir -p "$OUT/results" "$OUT/cache"
for kind in auth web; do
  test -s "$ROOT/$kind-image.tar"
  sudo -n docker run --rm --platform linux/amd64 --cpus 0.5 --memory 512m --pids-limit 128 \
    --cap-drop ALL --security-opt no-new-privileges:true \
    -v "$ROOT/$kind-image.tar:/input/image.tar:ro" -v "$OUT/results:/output" \
    -v "$OUT/cache:/root/.cache/trivy" "$SCAN" image --scanners vuln \
    --ignorefile /dev/null --severity UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL \
    --format json --output "/output/$kind.json" --input /input/image.tar \
    > "$OUT/$kind.log" 2>&1
  python3 - "$OUT/results/$kind.json" "$kind" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]));findings=[v for result in report.get('Results',[]) for v in result.get('Vulnerabilities',[])]
print(sys.argv[2],json.dumps({severity:sum(v.get('Severity')==severity for v in findings) for severity in ('CRITICAL','HIGH','MEDIUM','LOW','UNKNOWN')}),flush=True)
PY
done
