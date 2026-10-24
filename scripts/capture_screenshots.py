"""Capture full-page screenshots of the running dashboard via headless Chrome (CDP).

Prerequisite: the app is running, e.g. `streamlit run app.py --server.port 8599`.

Usage:
    python scripts/capture_screenshots.py --port 8599 [--chrome PATH]
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
PAGES = {
    "01_executive_overview": "",
    "02_city_explorer": "Pakistan_City_Explorer",
    "03_city_comparison": "City_Comparison",
    "04_historical_trends": "Historical_Trends",
    "05_seasonal_analysis": "Seasonal_Analysis",
    "06_weather_relationships": "Weather_Relationships",
    "07_pollutant_distributions": "Pollutant_Distributions",
    "08_statistical_analysis": "Statistical_Analysis",
    "09_data_quality": "Data_Quality",
    "10_methodology": "Methodology_and_Sources",
}
CHROME_DEFAULT = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


class CDP:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(ws_url, timeout=120, suppress_origin=True)
        self.i = 0

    def call(self, method: str, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    def eval(self, expr: str):
        return self.call("Runtime.evaluate", expression=expr, returnByValue=True).get("result", {}).get("value")


def wait_rendered(cdp: CDP, timeout: float = 120) -> None:
    """Wait until Streamlit stops running and no skeleton/spinner remains, then settle."""
    t0 = time.time()
    stable = 0
    while time.time() - t0 < timeout:
        busy = cdp.eval("""(() => {
            const s = document.querySelector('[data-testid="stStatusWidget"]');
            const sk = document.querySelectorAll('[data-testid="stSkeleton"], [data-testid="stSpinner"]').length;
            const app = document.querySelector('[data-testid="stMain"]');
            return (s ? 1 : 0) + sk + (app ? 0 : 1);
        })()""")
        stable = stable + 1 if busy == 0 else 0
        if stable >= 4:
            time.sleep(2.5)
            return
        time.sleep(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8599)
    ap.add_argument("--chrome", default=CHROME_DEFAULT)
    ap.add_argument("--width", type=int, default=1440)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    prof = tempfile.mkdtemp(prefix="pea-chrome-")
    dbg = 9333
    proc = subprocess.Popen([args.chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                             f"--remote-debugging-port={dbg}", f"--user-data-dir={prof}",
                             f"--window-size={args.width},1000", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(30):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{dbg}/json").read())
                break
            except OSError:
                time.sleep(0.5)
        page = next(t for t in tabs if t["type"] == "page")
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        for name, path in PAGES.items():
            cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=1000, deviceScaleFactor=1, mobile=False)
            cdp.call("Page.navigate", url=f"http://localhost:{args.port}/{path}")
            time.sleep(3)
            wait_rendered(cdp)
            h = cdp.eval("""(() => { const m = document.querySelector('[data-testid="stMain"]');
                                       return Math.max(m ? m.scrollHeight : 0, document.body.scrollHeight); })()""")
            h = int(min(max(h or 1000, 1000), 16000))
            cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=h, deviceScaleFactor=1, mobile=False)
            time.sleep(3)
            wait_rendered(cdp, 30)
            shot = cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=False)
            (OUT / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
            errs = cdp.eval("document.querySelectorAll('[data-testid=\"stException\"]').length")
            print(f"{name}: {h}px, exceptions on page: {errs}")
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
