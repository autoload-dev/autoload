#!/usr/bin/env bash
# EXPERIMENT(web tests): run the application tests N times and summarize the runner's timings.
#   web_exp/measure.sh <label> <runs> [bazel flags...]   (from addons/gdunit/examples)
set -euo pipefail
label=$1
runs=$2
shift 2
bazel test //web_exp:smoke_app_test //web_exp:gdunit_app_test --config=webtestb \
    --runs_per_test="$runs" --nocache_test_results --test_output=summary "$@" 2>&1 |
    grep -E "PASSED|FAILED|TIMEOUT|FLAKY|Executed" || true
for t in smoke_app_test gdunit_app_test; do
    python3 - "$label" "$t" "bazel-testlogs/web_exp/$t" "$runs" <<'PY'
import json, pathlib, re, statistics, sys
label, test, root = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
logs = sorted(root.glob(f"run_*_of_{sys.argv[4]}/test.log")) or [root / "test.log"]
rows = []
for log in logs:
    m = re.search(r"web_test_runner: timings (\{.*\})", log.read_text(errors="replace"))
    if m:
        rows.append(json.loads(m.group(1)))
def stat(xs):
    return f"median {statistics.median(xs):.2f} min {min(xs):.2f} max {max(xs):.2f}"
ok = sum(1 for r in rows if r["finished"] and r["exit"] in ("0",))
tot = [r["total_s"] for r in rows]
load = [r["page_marks_ms"].get("loaded", 0) / 1000 for r in rows]
main = [(r["page_marks_ms"].get("main", 0) - r["page_marks_ms"].get("loaded", 0)) / 1000 for r in rows]
run = [(r["page_marks_ms"].get("exit", 0) - r["page_marks_ms"].get("main", 0)) / 1000 for r in rows]
chrome = [r["chrome_to_first_request_s"] for r in rows]
print(f"{label} {test}: {ok}/{len(rows)} exit 0 | runner total {stat(tot)} s | chrome start {stat(chrome)} | "
      f"fetch wasm+pck {stat(load)} | wasm compile+engine init {stat(main)} | project run {stat(run)}")
PY
done
