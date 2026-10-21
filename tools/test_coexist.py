"""最小复现：ThreadingHTTPServer + pywebview 同进程，HTTP 是否还能响应。"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--disable-gpu --no-sandbox --disable-features=RendererCodeIntegrity",
)

PORT = 8799
HITS = {"n": 0}


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_GET(self):
        HITS["n"] += 1
        body = json.dumps({"ok": True, "n": HITS["n"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def probe(tag: str) -> None:
    for i in range(3):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=6) as r:
                data = r.read()
            print(f"[{tag}] {i} ok {(time.perf_counter()-t0)*1000:.0f}ms {data!r}", flush=True)
        except Exception as e:
            print(f"[{tag}] {i} FAIL {(time.perf_counter()-t0)*1000:.0f}ms {type(e).__name__} {e}", flush=True)
        time.sleep(1)


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("server up", flush=True)
    probe("pre-webview")

    import webview

    url = sys.argv[1] if len(sys.argv) > 1 else "html"
    win = webview.create_window(
        "Coexist",
        html="<h1>coexist</h1>" if url == "html" else url,
        width=520, height=360,
    )

    def job() -> None:
        time.sleep(2)
        probe("in-webview")
        time.sleep(1)
        win.destroy()

    print("calling webview.start", flush=True)
    webview.start(job, gui="edgechromium", private_mode=False)
    print("webview returned", flush=True)
    srv.shutdown()


if __name__ == "__main__":
    main()
