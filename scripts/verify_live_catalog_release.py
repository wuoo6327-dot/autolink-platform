"""Read-only production catalog/source check for a release candidate.

Fetches only public catalog, reference, and image URLs. It never writes to the
production service. A mismatch withdraws release approval rather than changing
the candidate's reviewed content automatically.
"""
import hashlib
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://autolinkglobal.com"
FIXTURE = json.loads((ROOT / "tests/fixtures/production-public-catalog-20261012.json").read_text())
HEROES = json.loads((ROOT / "site/images/seo-heroes/manifest.json").read_text())


def fetch(path):
    assert path.startswith("/") and not path.startswith("//")
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "AUTOLINK-release-readonly/1.0"})
    # Public CDN responses can be interrupted mid-body. Retry the same read-only
    # request, but never treat a partial body as evidence that content matches.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except (OSError, http.client.HTTPException, urllib.error.URLError):
            if attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))


def check_model(model):
    ident = model["id"]
    errors = []
    reference_path = f"/model-reference/{ident}.json"
    local_reference = ROOT / reference_path.lstrip("/")
    if not local_reference.is_file():
        local_reference = ROOT / "site" / reference_path.lstrip("/")
    try:
        body, content_type = fetch(reference_path)
        if "json" not in content_type:
            errors.append("reference-content-type")
        if json.loads(body) != json.loads(local_reference.read_bytes()):
            errors.append("reference-content-change")
    except (OSError, ValueError, http.client.HTTPException, urllib.error.URLError) as exc:
        errors.append("reference-fetch:" + type(exc).__name__)

    hero = HEROES.get(ident)
    if not hero or hero.get("source") != model.get("image"):
        errors.append("image-path-change")
    else:
        try:
            body, content_type = fetch(hero["source"])
            if not content_type.startswith("image/"):
                errors.append("image-content-type")
            if hashlib.sha256(body).hexdigest() != hero["sourceSHA256"]:
                errors.append("image-content-change")
        except (OSError, http.client.HTTPException, urllib.error.URLError) as exc:
            errors.append("image-fetch:" + type(exc).__name__)
    return ident, errors


def main(output):
    models_raw, _ = fetch("/autolink/public/models?limit=500")
    brands_raw, _ = fetch("/autolink/public/brands")
    live_models = json.loads(models_raw)["data"]
    live_brands = json.loads(brands_raw)["data"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        checks = dict(pool.map(check_model, live_models))
    findings = {ident: issues for ident, issues in checks.items() if issues}
    summary = {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "productionOrigin": BASE,
        "models": len(live_models),
        "brands": len(live_brands),
        "catalogModelsExact": live_models == FIXTURE["models"],
        "catalogBrandsExact": live_brands == FIXTURE["brands"],
        "referenceAndImageChecks": len(checks),
        "findings": findings,
    }
    summary["pass"] = (summary["models"] == 244 and summary["brands"] == 53
                       and summary["catalogModelsExact"] and summary["catalogBrandsExact"]
                       and len(checks) == 244 and not findings)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests/results/live-catalog-release-20261012.json"
    raise SystemExit(main(path))
