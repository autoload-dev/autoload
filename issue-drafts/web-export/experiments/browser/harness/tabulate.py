#!/usr/bin/env python3
"""EXPERIMENT(web-browser): prints every matrix's summary.json as one Markdown table.

Usage: tabulate.py <results-dir>
"""

import json
import re
import sys
from pathlib import Path


def fmt(s):
    return (
        "-"
        if not s
        else "%d / %d / %d / %d" % (s["min"], s["median"], s["p90"], s["max"])
    )


def main():
    root = Path(sys.argv[1])
    print(
        "| matrix | export | case | right code | statuses | output before exit | first print ms | exit ms (page) | wall ms | isolated | loads | page errors |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for summary in sorted(root.glob("*/summary.json")):
        for r in json.loads(summary.read_text()):
            print(
                "| %s | %s | %s | %d/%d | %s | %s | %s | %s | %s | %s | %s | %s |"
                % (
                    r["matrix"],
                    r["export"],
                    r["case"],
                    r["correct_code"],
                    r["runs"],
                    ", ".join("%s %d" % kv for kv in sorted(r["statuses"].items())),
                    "yes" if r["all_output_before_exit"] else "NO",
                    fmt(r["first_stdout_ms"]),
                    fmt(r["page_exit_ms"]),
                    fmt(r["wall_total_ms"]),
                    ",".join(str(i) for i in r["isolated"]),
                    ",".join(str(i) for i in r["loads"]),
                    "<br>".join(
                        sorted(
                            {
                                re.sub(
                                    r"\s+",
                                    " ",
                                    re.sub(r"https?://127\.0\.0\.1:\d+", "", t),
                                ).replace("|", "/")[:80]
                                for t in r["page_errors"]
                            }
                        )
                    )
                    or "-",
                )
            )
    renderers = sorted(
        {
            (json.loads(s.read_text())[0]["matrix"], w)
            for s in root.glob("*/summary.json")
            for r in json.loads(s.read_text())
            for w in r["webgl2"]
        }
    )
    print("\nWebGL2 renderer per matrix (unmasked, from the page):\n")
    for m, w in renderers:
        print("- %s: %s" % (m, w))


if __name__ == "__main__":
    main()
