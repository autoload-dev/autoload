"""
PROTOTYPE(web): serve a web application on localhost and open it in the browser.

Serves the site with the headers Godot's own web server sends, so a threaded build would
get cross-origin isolation too. Ctrl-C stops the server.
"""

from __future__ import annotations

import functools
import http.server
import webbrowser
from collections.abc import Callable, Mapping
from typing import Any

import launch_common

OPTIONS = frozenset({"headless", "detach", "env"})

_PORT = 8060  # The port of Godot's editor's "Run in browser".


class _Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map | {
        ".wasm": "application/wasm",
        ".pck": "application/octet-stream",
    }

    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def launch(
    manifest: Mapping[str, Any],
    options: launch_common.Options,
    runfile: Callable[[str], str],
) -> int:
    site = runfile(manifest["site"])
    handler = functools.partial(_Handler, directory=site)
    with http.server.ThreadingHTTPServer(("127.0.0.1", _PORT), handler) as server:
        url = f"http://127.0.0.1:{_PORT}/index.html"
        launch_common.log(f"Serving {site} at {url}; Ctrl-C stops the server")
        if not options.headless:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0
