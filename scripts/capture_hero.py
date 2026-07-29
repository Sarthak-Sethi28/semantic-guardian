"""Capture the animated HTML hero as real video (records the CSS animation playing).

Playwright renders demo/hero.html at 1440x900 and records the actual motion to webm;
we transcode to mp4. Real animation, not drawn PNG frames.

Run:  python scripts/capture_hero.py [seconds]
Out:  demo/hero.mp4
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DEMO = Path(__file__).resolve().parent.parent / "demo"


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    hero = (DEMO / "hero.html").resolve()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(DEMO),
            record_video_size={"width": 1440, "height": 900},
        )
        pg = ctx.new_page()
        pg.goto(hero.as_uri(), wait_until="load")
        pg.wait_for_timeout(int(seconds * 1000))
        ctx.close()
        b.close()
    # newest webm -> hero.mp4
    webms = sorted(DEMO.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    src = webms[-1]
    out = DEMO / "hero.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-vf", "scale=1440:900,fps=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True)
    src.unlink(missing_ok=True)
    print(f"hero: {out}")


if __name__ == "__main__":
    main()
