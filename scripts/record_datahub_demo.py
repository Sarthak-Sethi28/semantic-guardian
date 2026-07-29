"""Record a DataHub-UI walkthrough as a video (#14 demo).

Drives the DataHub UI with Playwright and records it to a .webm: log in, open the
fct_revenue dataset, and reveal what Semantic Guardian wrote back to the graph — the
tags, the semantic-contract assertions, the documentation. This is the visual proof of
'contributes durable context back to DataHub.'

Prereqs: local DataHub up (:9002), and the demo already run so the writes exist
(python scenario/seed.py && python scripts/demo_killer.py).

Run:  python scripts/record_datahub_demo.py
Output: demo/datahub_walkthrough.webm
"""
from __future__ import annotations

import pathlib

from playwright.sync_api import sync_playwright

BASE = "http://localhost:9002"
DATASET_PATH = (
    "/dataset/urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"
)
OUT_DIR = pathlib.Path("demo")


def _slow(page, ms=1600):
    page.wait_for_timeout(ms)


def _poll_fill(page, name: str, value: str, tries: int = 30) -> bool:
    """Poll for a form input that renders late / reports as not-visible, then fill it."""
    for _ in range(tries):
        el = page.query_selector(f"input#{name}")
        if el:
            try:
                el.fill(value)
                return True
            except Exception:
                pass
        page.wait_for_timeout(1000)
    return False


def _run(page) -> None:
    # 1. Login — DataHub's inputs render late and can report not-visible; poll + fill.
    page.goto(f"{BASE}/login", wait_until="load", timeout=30000)
    _slow(page, 3000)
    ok = _poll_fill(page, "username", "datahub") and _poll_fill(page, "password", "datahub")
    if ok:
        _slow(page, 800)
        try:
            page.click("button:has-text('Log in'), button:has-text('Login')", timeout=8000)
        except Exception:
            page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=30000)
        _slow(page, 2500)

    # 2. Open the dataset Semantic Guardian reviewed + wrote back to
    page.goto(f"{BASE}{DATASET_PATH}", wait_until="load", timeout=30000)
    page.wait_for_load_state("networkidle", timeout=30000)
    _slow(page, 3500)  # entity header (name, tags, documentation) render

    def _click_tab(*labels) -> bool:
        """Click the first matching tab by exact-ish text; return whether it landed."""
        for label in labels:
            tab = page.query_selector(f"nav >> text='{label}'") or page.query_selector(
                f"text='{label}'"
            )
            if tab:
                try:
                    tab.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    _slow(page, 3200)
                    return True
                except Exception:
                    pass
        return False

    # 3. THE PAYOFF — the write-back the agent made. Land on each and linger so the
    #    recording actually shows it (the tags + docs are already visible top/right).
    #    a) Quality -> the durable semantic contracts (CUSTOM assertions)
    if _click_tab("Quality"):
        # inside Quality, the assertions list may sit under an Assertions sub-tab
        _click_tab("Assertions", "Contracts")
        for _ in range(3):
            page.mouse.wheel(0, 400)
            _slow(page, 1400)
    # b) Incidents -> the raiseIncident the agent opened
    _click_tab("Incidents")
    _slow(page, 2500)
    for _ in range(2):
        page.mouse.wheel(0, 400)
        _slow(page, 1400)
    # c) end back on Quality/Assertions so the final frame IS the contract
    _click_tab("Quality")
    _click_tab("Assertions", "Contracts")
    _slow(page, 3500)


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": 1440, "height": 900},
        )
        page = context.new_page()
        try:
            _run(page)
        except Exception as exc:  # noqa: BLE001 - always finalize the video
            print(f"walkthrough hit an issue (video still saved): {exc}")
        finally:
            context.close()  # finalizes the video
            browser.close()

    vids = list(OUT_DIR.glob("*.webm"))
    if vids:
        newest = max(vids, key=lambda f: f.stat().st_mtime)
        print(f"Recorded: {newest}")
    else:
        print("No video produced — check DataHub is up on :9002")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
