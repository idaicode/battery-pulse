"""测量：参数最小集 + 窗口创建/销毁耗时（决定托盘菜单的实现方式）。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PARAMS = sys.argv[1] if len(sys.argv) > 1 else "--disable-gpu"
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = PARAMS

import webview

ROOT = Path(__file__).resolve().parent.parent
STORE = str(ROOT / "data" / "webview2")


def main() -> None:
    marks: dict[str, float] = {}
    main_win = webview.create_window(
        "main", html="<h1>main</h1>", width=400, height=300, hidden=True
    )

    def job() -> None:
        t0 = time.perf_counter()
        try:
            main_win.show()
            marks["main_show"] = (time.perf_counter() - t0) * 1000
            t1 = time.perf_counter()
            w2 = webview.create_window("t2", html="<h1>two</h1>", width=300, height=200, frameless=True)
            w2.events.loaded.wait(20)
            marks["create2+loaded"] = (time.perf_counter() - t1) * 1000
            t2 = time.perf_counter()
            w2.destroy()
            marks["destroy"] = (time.perf_counter() - t2) * 1000
        except Exception as e:
            print("ERR", type(e).__name__, e)
        finally:
            print("MARKS:", {k: round(v, 1) for k, v in marks.items()})
            for w in list(webview.windows):
                try:
                    w.destroy()
                except Exception:
                    pass

    webview.start(job, gui="edgechromium", private_mode=False, storage_path=STORE)


if __name__ == "__main__":
    main()
