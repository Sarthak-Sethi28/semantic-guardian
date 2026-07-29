"""Build the REAL-PROOF middle segment for the Veo-bookended demo.

No voiceover (the Veo hook/close carry the audio) — just the real footage with
crisp burned-in captions, tightened so the judge sees the agent work fast:
  terminal killer-run (captioned)  ->  live DataHub write-back (captioned)

Out: demo/proof_segment.mp4  (splice between Veo clip 2 and Veo clip 3)
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEMO = Path(__file__).resolve().parent.parent / "demo"
W, H = 1440, 900
FPS = 30
SANS = "/System/Library/Fonts/Helvetica.ttc"
f_cap = ImageFont.truetype(SANS, 30)
f_sub = ImageFont.truetype(SANS, 22)


def caption_overlay(text, sub, path: Path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 96], fill=(10, 12, 16, 232))
    tw = d.textlength(text, font=f_cap)
    d.text(((W - tw) / 2, 18), text, font=f_cap, fill=(245, 246, 248))
    if sub:
        sw = d.textlength(sub, font=f_sub)
        d.text(((W - sw) / 2, 58), sub, font=f_sub, fill=(118, 200, 222))
    img.save(path)


def clip_with_caption(src, cap_png, dur, out):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-i", str(cap_png),
         "-filter_complex",
         f"[0:v]scale=1440:900,fps={FPS},setpts=PTS-STARTPTS[bg];[bg][1:v]overlay=0:0[v]",
         "-map", "[v]", "-t", f"{dur}", "-an",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True)


def main():
    tmp = Path(tempfile.mkdtemp())
    c1 = tmp / "c1.png"
    c2 = tmp / "c2.png"
    caption_overlay("The agent reads the code + the DataHub contract",
                    "inverted boolean — stats monitors are blind, the agent is not", c1)
    caption_overlay("It writes the verdict back into DataHub — live",
                    "tags · incident · a durable semantic contract", c2)

    t = tmp / "t.mp4"
    dh = tmp / "dh.mp4"
    clip_with_caption(DEMO / "terminal.mp4", c1, 7.3, t)
    clip_with_caption(DEMO / "datahub_30.mp4", c2, 22, dh)

    concat = tmp / "c.txt"
    concat.write_text(f"file '{t}'\nfile '{dh}'\n")
    out = DEMO / "proof_segment.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
        check=True, capture_output=True)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(out)],
        check=True, capture_output=True, text=True).stdout.strip()
    print(f"proof segment: {out}  ({float(dur):.1f}s)")


if __name__ == "__main__":
    main()
