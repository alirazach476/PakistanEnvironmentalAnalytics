"""Load every route of the static web dashboard in headless Chrome, report JS errors and
rendered-chart counts, and save full-page screenshots.

Usage:
    python scripts/check_web.py --url http://127.0.0.1:8765/ [--out docs/screenshots/web] [--dark] [--query "season=Monsoon"]
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from capture_screenshots import CDP, CHROME_DEFAULT  # noqa: E402

ROUTES = ["overview", "explorer", "compare", "trends", "seasonal", "weather", "distributions", "statistics", "quality",
          "methodology"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots" / "web"))
    ap.add_argument("--dark", action="store_true")
    ap.add_argument("--query", default="")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--no-shots", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    prof = tempfile.mkdtemp(prefix="pea-web-")
    port = 9345
    proc = subprocess.Popen([CHROME_DEFAULT, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                             f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures = 0
    try:
        for _ in range(40):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json").read())
                break
            except OSError:
                time.sleep(0.5)
        cdp = CDP(next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"])
        errors: list[str] = []
        cdp.call("Runtime.enable")
        cdp.call("Log.enable")
        cdp.call("Page.enable")
        theme = "dark" if args.dark else "light"
        cdp.call("Page.addScriptToEvaluateOnNewDocument",
                 source=f"try{{localStorage.setItem('pea-theme','{theme}')}}catch(e){{}}")
        orig_call = cdp.call

        def drain():
            cdp.ws.settimeout(0.2)
            try:
                while True:
                    msg = json.loads(cdp.ws.recv())
                    if msg.get("method") == "Runtime.exceptionThrown":
                        d = msg["params"]["exceptionDetails"]
                        errors.append(d.get("exception", {}).get("description") or d.get("text"))
                    elif msg.get("method") == "Log.entryAdded" and msg["params"]["entry"]["level"] == "error":
                        errors.append(msg["params"]["entry"]["text"])
                    elif msg.get("method") == "Runtime.consoleAPICalled" and msg["params"]["type"] == "error":
                        errors.append(" ".join(str(a.get("value", a.get("description"))) for a in msg["params"]["args"]))
            except Exception:
                pass
            finally:
                cdp.ws.settimeout(120)

        q = f"?{args.query}" if args.query else ""
        for i, r in enumerate(ROUTES):
            errors.clear()
            orig_call("Emulation.setDeviceMetricsOverride", width=args.width, height=1000, deviceScaleFactor=1, mobile=False)
            orig_call("Page.navigate", url=f"{args.url}#/{r}{q}")
            t0 = time.time()
            while time.time() - t0 < 60:
                time.sleep(1)
                drain()
                ready = cdp.eval("!!document.querySelector('#content') && !document.querySelector('#content .loading')")
                if ready:
                    break
            time.sleep(2.5)
            drain()
            info = cdp.eval("""(() => ({charts: document.querySelectorAll('.js-plotly-plot').length,
                empties: document.querySelectorAll('.empty').length,
                warn: [...document.querySelectorAll('#content .callout.warn')].map(e => e.textContent.slice(0, 90)).filter(t => t.startsWith('This view')),
                h: Math.max(document.querySelector('.main').scrollHeight, document.body.scrollHeight)}))()""")
            status = "OK" if not errors and not info["warn"] else "FAIL"
            failures += status == "FAIL"
            print(f"{r:14s} {status}  charts={info['charts']:2d} empty={info['empties']}  {'; '.join(errors[:3])} {info['warn']}")
            if not args.no_shots:
                h = int(min(max(info["h"], 1000), 16000))
                orig_call("Emulation.setDeviceMetricsOverride", width=args.width, height=h, deviceScaleFactor=1, mobile=False)
                time.sleep(2.5)
                shot = orig_call("Page.captureScreenshot", format="png")
                (out / f"{i + 1:02d}_{r}{'_dark' if args.dark else ''}.png").write_bytes(base64.b64decode(shot["data"]))
    finally:
        proc.terminate()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
