"""在同一个进程树里启动 app.py 并探测端口，避免后台任务的网络隔离干扰诊断。"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
PORT = 8731


def probe(tag: str) -> None:
    t0 = time.perf_counter()
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
    except Exception as e:
        print(f"{tag} connect {type(e).__name__} ({(time.perf_counter()-t0)*1000:.0f}ms)", flush=True)
        return
    try:
        s.settimeout(3)
        s.sendall(b"GET /api/state HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        buf = b""
        while True:
            d = s.recv(65536)
            if not d:
                break
            buf += d
        head = buf.split(b"\r\n\r\n")[0].split(b"\r\n")[0].decode(errors="replace")
        body = buf.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in buf else b""
        ms = (time.perf_counter() - t0) * 1000
        try:
            j = json.loads(body)
            devs = [(x["name"][:10], x["percent"]) for x in j.get("devices", [])]
            print(f"{tag} OK {ms:.0f}ms devs={devs}", flush=True)
        except Exception:
            print(f"{tag} OK {ms:.0f}ms {head} raw={body[:80]!r}", flush=True)
    except Exception as e:
        print(f"{tag} read {type(e).__name__} ({(time.perf_counter()-t0)*1000:.0f}ms)", flush=True)
    finally:
        s.close()


def main() -> None:
    args = [PY, "-u", "app.py"] + sys.argv[1:]
    print("launch:", " ".join(args), flush=True)
    proc = subprocess.Popen(
        args, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            print("  [app]", line.rstrip(), flush=True)

    threading.Thread(target=pump, daemon=True).start()

    time.sleep(6)
    for i in range(7):
        probe(f"probe{i}")
        time.sleep(1.5)

    print("alive:", proc.poll() is None, flush=True)
    try:
        proc.terminate()
        proc.wait(timeout=6)
    except Exception:
        proc.kill()
    print("done", flush=True)


if __name__ == "__main__":
    main()
