"""
EXPERIMENT(web tests): run a Godot web export in a headless Chrome as a Bazel test.

Serves the exported site on 127.0.0.1 together with a harness page that starts the engine
through Godot's `Engine` JS API, streams onPrint/onPrintError to this process's
stdout/stderr, receives the JUnit XML from the page and ends with the engine's exit code.

Bazel's test contract: XML_OUTPUT_FILE receives the JUnit report, TEST_UNDECLARED_OUTPUTS_DIR
the timings, TEST_TOTAL_SHARDS/TEST_SHARD_INDEX and TESTBRIDGE_TEST_ONLY select suites on
the host, and TEST_SHARD_STATUS_FILE is touched.

    web_test_runner.py --site DIR --chrome PATH [--suite res://a.gd ...]
        [--godot-arg ARG ...] [--timeout S] [--keep-profile] [-- <GdUnit options>]
"""

from __future__ import annotations

import argparse
import base64
import functools
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

_HARNESS = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>godot web test</title>
<style>html,body{margin:0;background:#000}canvas{display:block}</style></head>
<body><canvas id="canvas" width="640" height="360"></canvas>
<script src="index.js"></script>
<script>
const ARGS = __ARGS__;
const T0 = performance.now();
let queue = [], chain = Promise.resolve(), timer = null;
function post(path, body) {
  chain = chain.then(() => fetch(path, {method: 'POST', body}).catch(() => {}));
  return chain;
}
function flush() {
  timer = null;
  if (queue.length) { const lines = queue; queue = []; post('/__log', JSON.stringify(lines)); }
  return chain;
}
function log(stream, text) {
  queue.push([stream, text]);
  if (!timer) timer = setTimeout(flush, 20);
}
function mark(name) { post('/__mark', JSON.stringify([name, performance.now() - T0])); }
window.addEventListener('error', (e) => log('stderr', 'page error: ' + e.message));
window.addEventListener('unhandledrejection', (e) => log('stderr', 'page rejection: ' + e.reason));
// Channel 1 for the report: the GDScript adapter calls this through JavaScriptBridge.
window.godotTestReport = (name, text) => {
  flush();
  post('/__report?channel=bridge&name=' + encodeURIComponent(name), text);
};
// Channel 3: IndexedDB, where Emscripten's IDBFS keeps user:// (/userfs).
function readUserfs() {
  return new Promise((resolve) => {
    const open = indexedDB.open('/userfs');
    open.onerror = () => resolve({error: String(open.error)});
    open.onsuccess = () => {
      const db = open.result;
      if (!db.objectStoreNames.contains('FILE_DATA')) { resolve({stores: [...db.objectStoreNames]}); return; }
      const out = {};
      const req = db.transaction('FILE_DATA').objectStore('FILE_DATA').openCursor();
      req.onsuccess = () => {
        const cursor = req.result;
        if (!cursor) { resolve(out); return; }
        const v = cursor.value;
        if (v && v.contents) {
          let bin = ''; const bytes = new Uint8Array(v.contents);
          for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
          out[cursor.key] = btoa(bin);
        }
        cursor.continue();
      };
      req.onerror = () => resolve({error: String(req.error)});
    };
  });
}
const engine = new Engine({
  executable: 'index',
  mainPack: 'index.pck',
  canvas: document.getElementById('canvas'),
  canvasResizePolicy: 0,
  focusCanvas: false,
  ensureCrossOriginIsolationHeaders: false,
  experimentalVK: false,
  gdextensionLibs: [],
  args: ARGS,
  onPrint: (...parts) => log('stdout', parts.join(' ')),
  onPrintError: (...parts) => log('stderr', parts.join(' ')),
  onExit: (code) => {
    mark('exit');
    flush();
    // Give IDBFS a moment in case the engine syncs on exit.
    setTimeout(async () => {
      const files = await readUserfs();
      await post('/__userfs', JSON.stringify(files));
      await post('/__exit', String(code));
    }, 200);
  },
});
mark('script');
(() => {
  const gl = document.createElement('canvas').getContext('webgl2');
  const info = gl && gl.getExtension('WEBGL_debug_renderer_info');
  log('stdout', 'harness: webgl2 renderer ' + (info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl ? 'masked' : 'none'));
})();
Promise.all([engine.init('index'), engine.preloadFile('index.pck', 'index.pck')])
  .then(() => { mark('loaded'); return engine.start({args: ['--main-pack', 'index.pck'].concat(ARGS)}); })
  .then(() => mark('main'))
  .catch((err) => { log('stderr', 'engine failed to start: ' + err); flush().then(() => post('/__exit', 'start-failed')); });
</script></body></html>
"""


class _State:
    def __init__(self) -> None:
        self.exit_code: str | None = None
        self.done = threading.Event()
        self.reports: dict[str, bytes] = {}
        self.userfs: dict[str, str] = {}
        self.marks: dict[str, float] = {}
        self.first_request: float | None = None
        self.stdout: list[str] = []


def _handler(site: str, page: bytes, state: _State):
    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
            ".wasm": "application/wasm",
            ".pck": "application/octet-stream",
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site, **kwargs)

        def log_message(self, *args) -> None:  # quiet
            pass

        def end_headers(self) -> None:
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            if state.first_request is None:
                state.first_request = time.monotonic()
            if self.path.startswith("/__harness.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(page)))
                self.end_headers()
                self.wfile.write(page)
                return
            super().do_GET()

        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            if url.path == "/__log":
                for stream, text in json.loads(body):
                    out = sys.stdout if stream == "stdout" else sys.stderr
                    if stream == "stdout":
                        state.stdout.append(text)
                    out.write(text + "\n")
                    out.flush()
            elif url.path == "/__mark":
                name, millis = json.loads(body)
                state.marks[name] = millis
            elif url.path == "/__report":
                state.reports[query["channel"][0] + ":" + query["name"][0]] = body
            elif url.path == "/__userfs":
                state.userfs = json.loads(body)
            elif url.path == "/__exit":
                state.exit_code = body.decode()
                state.done.set()
            self.send_response(204)
            self.end_headers()

    return Handler


def _select(suites: list[str]) -> list[str] | None:
    """Bazel's filter and shard selection on the host, as test_cases.gd does in the pack."""
    status = os.environ.get("TEST_SHARD_STATUS_FILE")
    total = int(os.environ.get("TEST_TOTAL_SHARDS", "0") or 0)
    if total and status:
        pathlib.Path(status).touch()
    only = os.environ.get("TESTBRIDGE_TEST_ONLY")
    if only:
        suites = [suite for suite in suites if only in suite]
    if total:
        index = int(os.environ["TEST_SHARD_INDEX"])
        suites = [
            suite for position, suite in enumerate(suites) if position % total == index
        ]
    return suites


def _junit_from_log(text: str) -> str | None:
    begin, end = "@@JUNIT-BEGIN@@\n", "@@JUNIT-END@@"
    if begin not in text:
        return None
    return text.split(begin, 1)[1].split(end, 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--chrome", required=True)
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--godot-arg", action="append", default=[])
    # Below Bazel's TEST_TIMEOUT, so the runner reports a hang itself.
    parser.add_argument(
        "--timeout", type=float, default=float(os.environ.get("TEST_TIMEOUT", "250")) - 10
    )
    parser.add_argument("--chrome-flag", action="append", default=[])
    parser.add_argument("gdunit", nargs="*")
    options = parser.parse_args()

    started = time.monotonic()
    gdunit = list(options.gdunit)
    if options.suite:
        selected = _select(options.suite)
        if not selected:
            print("web_test_runner: no suite in this shard or filter")
            return 0
        for suite in selected:
            gdunit += ["-a", suite]
    # An unknown option makes main_args nonempty, so Godot runs without a main scene.
    args = options.godot_arg + ["--autoload-test", "--"] + gdunit
    page = _HARNESS.replace("__ARGS__", json.dumps(args)).encode()
    state = _State()
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), _handler(options.site, page, state)
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/__harness.html"

    # Chrome's profile holds a Unix socket, whose path macOS limits to 104 bytes; Bazel's
    # TEST_TMPDIR is longer, so the profile lives in /tmp.
    profile = tempfile.mkdtemp(prefix="gwt-", dir="/tmp")
    chrome = [
        options.chrome,
        f"--user-data-dir={profile}",
        "--no-first-run",
        # Chrome's own sandbox cannot start inside Bazel's (sandbox-exec on macOS, namespaces
        # on Linux): "sandbox initialization failed: Operation not permitted".
        "--no-sandbox",
        "--no-default-browser-check",
        "--disable-gpu",
        "--enable-unsafe-swiftshader",
        "--use-angle=swiftshader",
        "--disable-dev-shm-usage",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--use-mock-keychain",
        "--remote-debugging-port=0",
        *options.chrome_flag,
        url,
    ]
    print("web_test_runner: godot args " + json.dumps(args), flush=True)
    browser = subprocess.Popen(chrome, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.monotonic() + options.timeout
    finished = False
    while time.monotonic() < deadline:
        if state.done.wait(0.2):
            finished = True
            break
        if browser.poll() is not None:
            print(
                f"web_test_runner: Chrome exited with {browser.returncode} before the engine",
                file=sys.stderr,
            )
            break
    ended = time.monotonic()
    browser.terminate()
    try:
        _, chrome_err = browser.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        browser.kill()
        _, chrome_err = browser.communicate()
    server.shutdown()
    shutil.rmtree(profile, ignore_errors=True)

    timings = {
        "chrome_to_first_request_s": round((state.first_request or ended) - started, 3),
        "page_marks_ms": {k: round(v) for k, v in state.marks.items()},
        "total_s": round(ended - started, 3),
        "finished": finished,
        "exit": state.exit_code,
    }
    print("web_test_runner: timings " + json.dumps(timings), flush=True)
    outputs = os.environ.get("TEST_UNDECLARED_OUTPUTS_DIR")
    if outputs:
        pathlib.Path(outputs, "timings.json").write_text(json.dumps(timings))
        for key, value in state.userfs.items():
            if isinstance(value, str) and key.startswith("/userfs/"):
                target = pathlib.Path(outputs, "userfs", key[len("/userfs/") :])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode(value))
    channels = sorted(state.reports) + [
        "indexeddb:" + key for key in state.userfs if key.endswith("results.xml")
    ]
    if _junit_from_log("\n".join(state.stdout) + "\n"):
        channels.append("log:results.xml")
    print("web_test_runner: report channels " + json.dumps(channels), flush=True)
    if not finished:
        sys.stderr.write(chrome_err.decode(errors="replace")[-4000:])
        print(
            f"web_test_runner: no engine exit (timeout {options.timeout}s)",
            file=sys.stderr,
        )
        return 1
    report = state.reports.get("bridge:results.xml")
    xml_output = os.environ.get("XML_OUTPUT_FILE")
    if report and xml_output:
        pathlib.Path(xml_output).write_bytes(report)
    try:
        return int(state.exit_code or "1")
    except ValueError:
        return 1


if __name__ == "__main__":
    sys.exit(main())
