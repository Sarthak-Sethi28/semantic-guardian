"""Capture a real, animated terminal from the LIVE killer-demo output.

Renders an HTML terminal (mac chrome, syntax colors, blinking cursor) that types the
real /tmp/killer_live.txt line by line, and screen-records it with Playwright. Real
motion, not drawn PNG frames.

Run:  python scripts/capture_terminal_html.py [/tmp/killer_live.txt]
Out:  demo/terminal_live.mp4
"""
from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DEMO = Path(__file__).resolve().parent.parent / "demo"


def classify(line: str) -> str:
    s = line.strip()
    if s.startswith("STEP"):
        return "step"
    if "BLIND" in line:
        return "red"
    if "VERDICT: breaking" in line or "caught deterministically, no LLM: True" in line:
        return "green"
    if s.startswith("-->"):
        return "amber"
    if s.startswith(("WHY", "HYPOTHESES", "blast", "existing", "anomaly")):
        return "cyan"
    return "fg"


def build_html(lines: list[str]) -> str:
    payload = json.dumps([[classify(ln), ln.rstrip("\n")] for ln in lines])
    return """<!doctype html><html><head><meta charset=utf-8><style>
  *{margin:0;padding:0;box-sizing:border-box}
  html,body{width:1440px;height:900px;background:#0d0f14;overflow:hidden;
    font-family:"SF Mono",Menlo,monospace}
  .win{position:absolute;top:52px;left:70px;right:70px;bottom:52px;background:#12151c;
    border-radius:12px;box-shadow:0 30px 90px rgba(0,0,0,.6);overflow:hidden;
    border:1px solid #232833}
  .bar{height:40px;background:#1b1f28;display:flex;align-items:center;padding:0 16px;gap:9px}
  .dot{width:13px;height:13px;border-radius:50%}
  .title{color:#7b828d;font-size:15px;margin-left:14px}
  .body{padding:26px 30px;font-size:19px;line-height:1.55;white-space:pre-wrap;
    word-break:break-word;color:#e7eaef;height:calc(100% - 40px);overflow:hidden}
  .step{color:#fff;font-weight:700;margin-top:14px;display:block}
  .red{color:#f06c64}.green{color:#59c87a}.amber{color:#e6b45c}.cyan{color:#5ad0e6}.fg{color:#cfd4dc}
  .cursor{display:inline-block;width:10px;height:20px;background:#5ad0e6;
    vertical-align:-3px;animation:blink 1s steps(1) infinite}
  @keyframes blink{50%{opacity:0}}
</style></head><body>
  <div class="win">
    <div class="bar">
      <div class="dot" style="background:#ff5f56"></div>
      <div class="dot" style="background:#ffbd2e"></div>
      <div class="dot" style="background:#27c93f"></div>
      <div class="title">semantic-guardian &mdash; live run (real Claude)</div>
    </div>
    <div class="body" id="out"></div>
  </div>
<script>
const LINES = __PAYLOAD__;
const out = document.getElementById('out');
let li = 0, ci = 0, cur = null;
function tick(){
  if(li >= LINES.length){ if(cur) cur.remove(); return; }
  const [cls, text] = LINES[li];
  if(ci === 0){
    cur = document.createElement('span'); cur.className = cls;
    out.appendChild(cur);
    out.appendChild(document.createElement('br'));
  }
  if(ci < text.length){
    cur.textContent += text[ci]; ci++;
    setTimeout(tick, text.startsWith('STEP') ? 14 : 7);
  } else {
    li++; ci = 0;
    setTimeout(tick, LINES[li-1][0]==='step' ? 260 : 130);
  }
}
setTimeout(tick, 400);
</script>
</body></html>""".replace("__PAYLOAD__", payload)


def main() -> None:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/killer_live.txt")
    lines = [ln for ln in src.read_text().split("\n")]
    page_html = build_html(lines)
    tmp = DEMO / "_terminal.html"
    tmp.write_text(page_html)

    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(DEMO),
            record_video_size={"width": 1440, "height": 900},
        )
        pg = ctx.new_page()
        pg.goto(tmp.resolve().as_uri(), wait_until="load")
        pg.wait_for_timeout(21000)  # let it type out + linger
        ctx.close()
        b.close()

    webms = sorted(DEMO.glob("*.webm"), key=lambda f: f.stat().st_mtime)
    srcv = webms[-1]
    out = DEMO / "terminal_live.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(srcv), "-vf", "scale=1440:900,fps=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True)
    srcv.unlink(missing_ok=True)
    tmp.unlink(missing_ok=True)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(out)],
        check=True, capture_output=True, text=True).stdout.strip()
    print(f"terminal_live: {out}  ({float(dur):.1f}s)")


if __name__ == "__main__":
    main()
