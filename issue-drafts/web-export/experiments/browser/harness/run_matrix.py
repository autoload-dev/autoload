#!/usr/bin/env python3
"""EXPERIMENT(web-browser): runs serve.py many times per case and summarizes the results.

Usage: run_matrix.py <exports-dir> <chrome> <out-dir> <matrix-name> [runs]
"""

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
EXPORTS, CHROME, OUT, MATRIX = (
    Path(sys.argv[1]),
    sys.argv[2],
    Path(sys.argv[3]),
    sys.argv[4],
)
RUNS = int(sys.argv[5]) if len(sys.argv) > 5 else 20

# name: (godot args, expected code, timeout)
CASES = {
    "ready_c0": (["--", "code=0"], 0, 8),
    "ready_c3": (["--", "code=3"], 3, 8),
    "frames2_c3": (["--", "code=3", "frames=2"], 3, 8),
    "frames10_c3": (["--", "code=3", "frames=10"], 3, 12),
    "frames60_c0": (["--", "code=0", "frames=60"], 0, 20),
    "frames60_c42": (["--", "code=42", "frames=60"], 42, 10),
    "frames60_c255": (["--", "code=255", "frames=60"], 255, 20),
    "ready_dummyaudio_c5": (["--audio-driver", "Dummy", "--", "code=5"], 5, 12),
    "headless_ready_c9": (["--headless", "--", "code=9"], 9, 12),
}
MATRICES = {
    # export dir, serve.py options, cases
    "nt-swiftshader": (
        ["nt_release", "nt_debug"],
        ["--flags", "swiftshader"],
        list(CASES),
    ),
    "nt-gpu": (
        ["nt_release"],
        ["--flags", "gpu"],
        [
            "ready_c3",
            "frames10_c3",
            "frames60_c42",
            "ready_dummyaudio_c5",
            "headless_ready_c9",
        ],
    ),
    "nt-default-flags": (["nt_release"], ["--flags", "default"], ["frames60_c42"]),
    "nt-disable-gpu": (["nt_release"], ["--flags", "disable-gpu"], ["frames60_c42"]),
    "nt-swiftshader-angle-only": (
        ["nt_release"],
        ["--flags", "swiftshader-angle-only"],
        ["frames60_c42"],
    ),
    "th-swiftshader": (
        ["th_release", "th_debug"],
        ["--flags", "swiftshader", "--threads"],
        list(CASES),
    ),
    "th-gpu": (
        ["th_release"],
        ["--flags", "gpu", "--threads"],
        ["ready_c3", "frames60_c42", "ready_dummyaudio_c5"],
    ),
    "th-no-headers": (
        ["th_release"],
        ["--flags", "swiftshader", "--threads", "--no-isolate"],
        ["frames60_c42"],
    ),
    "nt-no-headers": (
        ["nt_release"],
        ["--flags", "swiftshader", "--no-isolate"],
        ["frames60_c42", "ready_dummyaudio_c5"],
    ),
    # The progressive web app, served without COOP/COEP: the service worker must supply them.
    "pwa-th-no-headers": (
        ["th_pwa_release", "th_pwa_debug"],
        ["--flags", "swiftshader", "--threads", "--no-isolate"],
        ["frames60_c42", "ready_dummyaudio_c5"],
    ),
    "pwa-th-no-headers-index": (
        ["th_pwa_release"],
        ["--flags", "swiftshader", "--threads", "--no-isolate", "--path", "index.html"],
        ["frames60_c42"],
    ),
    "pwa-th-no-headers-swreload": (
        ["th_pwa_release", "th_pwa_debug"],
        ["--flags", "swiftshader", "--threads", "--no-isolate", "--sw-reload"],
        ["frames60_c42", "ready_dummyaudio_c5"],
    ),
    "pwa-th-headers": (
        ["th_pwa_release"],
        ["--flags", "swiftshader", "--threads"],
        ["frames60_c42"],
    ),
    "pwa-nt-no-headers": (
        ["nt_pwa_release"],
        ["--flags", "swiftshader", "--no-isolate"],
        ["frames60_c42"],
    ),
}


def stats(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    q = lambda p: values[min(len(values) - 1, int(p * len(values)))]
    return {
        "n": len(values),
        "min": round(values[0]),
        "median": round(statistics.median(values)),
        "p90": round(q(0.9)),
        "max": round(values[-1]),
    }


def main():
    dirs, options, cases = MATRICES[MATRIX]
    summary = []
    for d in dirs:
        for case in cases:
            args, expected, timeout = CASES[case]
            records = []
            for i in range(RUNS):
                res = OUT / MATRIX / d / case / ("%02d.json" % i)
                res.parent.mkdir(parents=True, exist_ok=True)
                log = res.with_suffix(".log")
                with open(log, "w") as f:
                    p = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            str(HERE / "serve.py"),
                            "--dir",
                            str(EXPORTS / d),
                            "--chrome",
                            CHROME,
                            "--args",
                            json.dumps(args),
                            "--timeout",
                            str(timeout),
                            "--result",
                            str(res),
                            *options,
                        ],
                        stdout=f,
                        stderr=subprocess.STDOUT,
                    )
                r = json.loads(res.read_text())
                r["process_exit"] = p.returncode
                records.append(r)
            row = {
                "matrix": MATRIX,
                "export": d,
                "case": case,
                "expected": expected,
                "runs": RUNS,
                "correct_code": sum(
                    r["process_exit"] == expected and r["status"] == "exit"
                    for r in records
                ),
                "statuses": {
                    s: sum(r["status"] == s for r in records)
                    for s in {r["status"] for r in records}
                },
                "codes": sorted({r["process_exit"] for r in records}),
                "all_output_before_exit": all(
                    r["printed_before_exit"] for r in records if r["status"] == "exit"
                ),
                "complete_log": sum(
                    r["status"] == "exit"
                    and any(l.startswith("LAST") for l in r["stdout"])
                    for r in records
                ),
                "first_stdout_ms": stats(r["first_stdout_ms"] for r in records),
                "ready_ms": stats(r["ready_ms"] for r in records),
                "page_exit_ms": stats(
                    r["page_exit_ms"] for r in records if r["status"] == "exit"
                ),
                "wall_total_ms": stats(
                    r["wall_total_s"] * 1000 for r in records if r["status"] == "exit"
                ),
                "page_errors": sorted(
                    {
                        e["text"][:120]
                        for r in records
                        for e in r["events"]
                        if e["kind"]
                        in ("page-error", "console-error", "notice", "start-failed")
                    }
                ),
                "loads": sorted({r["loads"] for r in records}),
                "webgl2": sorted(
                    {
                        e.get("webgl2")
                        for r in records
                        for e in r["events"]
                        if e["kind"] == "boot"
                    }
                ),
                "isolated": sorted(
                    {
                        e.get("crossOriginIsolated")
                        for r in records
                        for e in r["events"]
                        if e["kind"] == "boot"
                    }
                ),
            }
            summary.append(row)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in (
                            "export",
                            "case",
                            "correct_code",
                            "statuses",
                            "codes",
                            "page_exit_ms",
                        )
                    }
                ),
                flush=True,
            )
    (OUT / MATRIX / "summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
