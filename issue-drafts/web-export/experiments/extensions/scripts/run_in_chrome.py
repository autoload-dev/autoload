"""
Serve a web export and run it in headless Chrome; print the page's console and the verdict.

usage: run_in_chrome.py <export dir> [--isolation] [--timeout=60] [--chrome=PATH]
Without --isolation the server sends no COOP/COEP headers.
"""

import functools
import http.server
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Handler(http.server.SimpleHTTPRequestHandler):
    isolation = False
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".wasm": "application/wasm",
        ".js": "text/javascript",
        ".pck": "application/octet-stream",
    }

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        if self.isolation:
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("[server] " + fmt % args + "\n")


def main():
    directory = os.path.abspath(sys.argv[1])
    isolation = "--isolation" in sys.argv
    timeout = 60
    chrome = CHROME
    for a in sys.argv[2:]:
        if a.startswith("--timeout="):
            timeout = int(a.split("=", 1)[1])
        if a.startswith("--chrome="):
            chrome = a.split("=", 1)[1]
    Handler.isolation = isolation
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=directory)
    )
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/index.html" % port
    print(
        "serving %s at %s (COOP/COEP: %s)"
        % (directory, url, "on" if isolation else "off"),
        flush=True,
    )
    profile = tempfile.mkdtemp(prefix="chrome-profile-")
    cmd = [
        chrome,
        "--headless=new",
        "--no-first-run",
        "--no-default-browser-check",
        "--user-data-dir=" + profile,
        "--enable-logging=stderr",
        "--v=0",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
        "--autoplay-policy=no-user-gesture-required",
        url,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    verdict = None
    deadline = time.time() + timeout
    console = re.compile(r'CONSOLE[:(]\d+\)?\] "(.*)", source')

    def reader():
        nonlocal verdict
        for line in proc.stderr:
            m = console.search(line)
            if m:
                msg = m.group(1)
                print("[console] " + msg, flush=True)
                if "WEBHELLO RESULT=" in msg:
                    verdict = msg.split("WEBHELLO RESULT=", 1)[1]
            elif "ERROR" in line and "CONSOLE" not in line and "gpu" not in line.lower():
                pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    while time.time() < deadline and verdict is None and proc.poll() is None:
        time.sleep(0.5)
    time.sleep(1)
    proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
    server.shutdown()
    shutil.rmtree(profile, ignore_errors=True)
    print(
        "VERDICT: %s"
        % (verdict or "TIMEOUT (no WEBHELLO RESULT line within %ds)" % timeout)
    )
    sys.exit(0 if verdict and verdict.startswith("PASS") else 1)


main()
