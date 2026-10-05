#!/usr/bin/env bash
# Build and start the Compose stack, take one sample organisation through the
# API (create, answer, retake, compare, download the workbook), then tear the
# stack and its volume down again, also on failure or Ctrl-C.
set -euo pipefail
cd "$(dirname "$0")/.."

export CSFCHECK_PORT="${CSFCHECK_PORT:-23181}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-csfcheck-smoke}"
base="http://127.0.0.1:${CSFCHECK_PORT}"
work="$(mktemp -d "${TMPDIR:-/tmp}/csfcheck-smoke.XXXXXX")"

cleanup() {
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT INT TERM

docker compose up --build --detach --wait
curl -fsS "$base/health"; echo

python3 - "$base" "$work" <<'PY'
import json, sys, urllib.request
from pathlib import Path

base, work = sys.argv[1], Path(sys.argv[2])

def call(method, path, body=None, token=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json",
                                          **({"X-Assessment-Token": token} if token else {})})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
        return json.loads(data) if resp.headers.get_content_type() == "application/json" else data

old = json.loads(Path("samples/food_bank.json").read_text())
new = json.loads(Path("samples/retakes/food_bank.json").read_text())
org = call("POST", "/organisations", {"name": old["organisation"]["name"], "profile": old["organisation"]["profile"]})
a = call("POST", f"/organisations/{org['id']}/assessments")
token = a["token"]

def answer_all(aid, answers):
    while True:
        nxt = call("GET", f"/assessments/{aid}/next?limit=20", token=token)
        if nxt["complete"]:
            return
        call("POST", f"/assessments/{aid}/answers", token=token,
             body={"answers": [{"question_id": q["id"], "value": answers[q["id"]]} for q in nxt["questions"]]})

answer_all(a["id"], old["answers"])
v2 = call("POST", f"/assessments/{a['id']}/retake", {"profile": new["organisation"]["profile"]}, token)
changed = {q: v for q, v in new["answers"].items() if old["answers"].get(q) != v}
call("POST", f"/assessments/{v2['id']}/answers", token=token,
     body={"answers": [{"question_id": q, "value": changed[q]} for q in changed if q in old["answers"]]})
answer_all(v2["id"], new["answers"])
diff = call("GET", f"/assessments/{v2['id']}/compare", token=token)
t = diff["totals"]
print(f"version {diff['before']['version']} -> {diff['after']['version']}: {t['improved']} improved, "
      f"{t['regressed']} regressed, {t['actions_completed']} of {t['actions_before']} actions completed")
xlsx = call("GET", f"/assessments/{v2['id']}/workbook", token=token)
(work / "workbook.xlsx").write_bytes(xlsx)
print(f"workbook: {len(xlsx)} bytes")
assert (t["improved"], t["regressed"], t["actions_completed"]) == (18, 3, 4), t
PY
echo "compose smoke test passed"
