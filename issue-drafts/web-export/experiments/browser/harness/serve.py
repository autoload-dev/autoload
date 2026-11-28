#!/usr/bin/env python3
"""EXPERIMENT(web-browser): runs a Godot web export in a browser and exits with its code.

Serves the export on 127.0.0.1, inserts hook.js into its page, starts the browser, prints
the application's log as it arrives (stdout and stderr) and exits with the code the engine
reports through `onExit`. No DevTools protocol. Writes a JSON record of the run to --result.

Exit codes besides the application's: 124 when it does not exit within --timeout, 125 when
the browser exits first, 126 when the page shows its failure notice (missing features) or
the engine fails to start.
"""

import argparse
import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HOOK = (Path(__file__).parent / "hook.js").read_bytes()
FLAG_SETS = {
    # chrome-headless-shell's defaults: on macOS (147) WebGL2 is unavailable, Godot's page
    # reports the missing feature.
    "default": [],
    # The host's GPU: chrome-headless-shell disables it unless asked.
    "gpu": ["--enable-gpu"],
    # As on a Linux CI runner without a GPU: no GPU process, WebGL through SwiftShader.
    "swiftshader": [
        "--disable-gpu",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
    ],
    "swiftshader-angle-only": ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    # GPU disabled without opting in to SwiftShader: what Chrome 137+ does by default.
    "disable-gpu": ["--disable-gpu"],
}
COMMON_FLAGS = [
    "--no-first-run",
    "--no-default-browser-check",
    # Background tabs and occluded windows must not throttle requestAnimationFrame.
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--autoplay-policy=no-user-gesture-required",
]


class Run:
    def __init__(self):
        self.lock = threading.Condition()
        self.events = {}  # (load, seq) -> event
        self.exit = None
        self.failed = None  # the page's failure notice, e.g. missing browser features
        self.t_start = time.monotonic()
        self.wall = {}
        self.printed = {}  # load -> next seq to print

    def add(self, event):
        with self.lock:
            key = (event["load"], event["seq"])
            self.events[key] = event
            self.wall.setdefault(event["kind"], time.monotonic() - self.t_start)
            self._print_in_order(event["load"])
            if event["kind"] == "exit":
                self.exit = event
            if event["kind"] in ("notice", "start-failed") or (
                event["kind"] == "console-error"
                and "features required" in event.get("text", "")
            ):
                self.failed = event
            self.lock.notify_all()

    def _print_in_order(self, load):
        """Prints the contiguous events of one page load in the order the page made them."""
        nxt = self.printed.get(load, 0)
        while (load, nxt) in self.events:
            event = self.events[(load, nxt)]
            if event["kind"] in ("stdout", "stderr"):
                stream = sys.stdout if event["kind"] == "stdout" else sys.stderr
                stream.write(event["text"].rstrip("\n") + "\n")
                stream.flush()
            elif event["kind"] != "exit":
                sys.stderr.write("[harness] %s\n" % json.dumps(event))
            nxt += 1
        self.printed[load] = nxt

    def complete(self):
        """Whether every event of the exiting load up to its exit has arrived."""
        load, last = self.exit["load"], self.exit["seq"]
        return all((load, s) in self.events for s in range(last))


def make_handler(root, config, run, isolate):
    inject = (
        b'<script src="index.js"></script>\n<script>window.__HARNESS__ = '
        + json.dumps(config).encode()
        + b';</script>\n<script src="/__harness/hook.js"></script>'
    )

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root), **kw)

        def log_message(self, *_):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            if isolate:
                self.send_header("Cross-Origin-Opener-Policy", "same-origin")
                self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            super().end_headers()

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/__harness/hook.js":
                return self._send(HOOK, "text/javascript")
            if path in ("/", "/index.html"):
                page = (root / "index.html").read_bytes()
                marker = b'<script src="index.js"></script>'
                if marker not in page:
                    sys.exit("index.html has no %r" % marker)
                construct = b"new Engine(GODOT_CONFIG)"
                if construct not in page:
                    sys.exit("index.html has no %r" % construct)
                page = page.replace(marker, inject, 1).replace(
                    construct, b"new Engine(window.__harnessConfig(GODOT_CONFIG))", 1
                )
                return self._send(page, "text/html")
            return super().do_GET()

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(204)
            self.end_headers()
            if self.path == "/__harness/event":
                for event in json.loads(body):
                    run.add(event)

    Handler.extensions_map = dict(
        http.server.SimpleHTTPRequestHandler.extensions_map,
        **{
            ".wasm": "application/wasm",
            ".js": "text/javascript",
            ".pck": "application/octet-stream",
        },
    )
    return Handler


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=True, type=Path, help="the export directory")
    p.add_argument("--chrome", required=True)
    p.add_argument("--flags", default="swiftshader", choices=sorted(FLAG_SETS))
    p.add_argument("--extra-flag", action="append", default=[])
    p.add_argument("--no-isolate", action="store_true", help="send no COOP/COEP headers")
    p.add_argument(
        "--threads", action="store_true", help="the export uses the threaded template"
    )
    p.add_argument(
        "--args", default=None, help="JSON list of Godot command-line arguments"
    )
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--result", type=Path)
    p.add_argument(
        "--sw-reload",
        action="store_true",
        help="reload again once the service worker is active",
    )
    p.add_argument("--path", default="", help="the page's path to open, e.g. index.html")
    a = p.parse_args()

    run = Run()
    config = {"threads": a.threads, "swReload": a.sw_reload}
    if a.args is not None:
        config["args"] = json.loads(a.args)
    http.server.ThreadingHTTPServer.request_queue_size = 128
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(a.dir, config, run, not a.no_isolate)
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/%s" % (server.server_address[1], a.path)

    profile = tempfile.mkdtemp(prefix="harness-chrome-")
    chrome_log = open(os.path.join(profile, "chrome.log"), "w")
    flags = COMMON_FLAGS + FLAG_SETS[a.flags] + a.extra_flag
    chrome = subprocess.Popen(
        [a.chrome, *flags, "--user-data-dir=" + profile, url],
        stdout=chrome_log,
        stderr=subprocess.STDOUT,
    )
    status, code = "timeout", 124
    deadline = run.t_start + a.timeout
    with run.lock:
        while time.monotonic() < deadline:
            if run.exit is not None:
                # Give late log messages a moment; the transport is unordered.
                grace = time.monotonic() + 5
                while not run.complete() and time.monotonic() < grace:
                    run.lock.wait(0.05)
                status, code = (
                    ("exit" if run.complete() else "exit-incomplete"),
                    run.exit["code"],
                )
                break
            if run.failed is not None:
                status, code = "page-failed", 126
                break
            if chrome.poll() is not None:
                status, code = "browser-exited", 125
                break
            run.lock.wait(0.1)
        events = sorted(run.events.values(), key=lambda e: (e["load"], e["seq"]))
    t_total = time.monotonic() - run.t_start
    chrome.terminate()
    try:
        chrome.wait(5)
    except subprocess.TimeoutExpired:
        chrome.kill()
    server.shutdown()

    if a.result:
        exit_event = run.exit or {}
        lines = [e["text"] for e in events if e["kind"] == "stdout"]
        record = {
            "status": status,
            "code": code,
            "wall_total_s": round(t_total, 3),
            "wall_first": {k: round(v, 3) for k, v in run.wall.items()},
            "page_exit_ms": exit_event.get("t"),
            # Page times (ms since navigation start) of the engine's first print and of READY.
            "first_stdout_ms": next(
                (e["t"] for e in events if e["kind"] == "stdout"), None
            ),
            "ready_ms": next(
                (
                    e["t"]
                    for e in events
                    if e["kind"] == "stdout" and e["text"].startswith("READY")
                ),
                None,
            ),
            "loads": max((e["load"] for e in events), default=0),
            "stdout_lines": len(lines),
            "stderr_lines": sum(1 for e in events if e["kind"] == "stderr"),
            # Every print the engine made reached the page before onExit.
            "printed_before_exit": all(
                e["seq"] < exit_event["seq"]
                for e in events
                if e["kind"] in ("stdout", "stderr")
                and e["load"] == exit_event.get("load")
            )
            if exit_event
            else None,
            "events": [e for e in events if e["kind"] not in ("stdout", "stderr")],
            "stdout": lines,
            "chrome_flags": flags,
        }
        a.result.write_text(json.dumps(record, indent=1))
    shutil.rmtree(profile, ignore_errors=True)
    sys.stderr.write("[harness] %s, code %d, %.2fs\n" % (status, code, t_total))
    sys.exit(code)


if __name__ == "__main__":
    main()
