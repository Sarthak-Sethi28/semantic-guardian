"""Render captured terminal output as a typed-out terminal video (MP4).

Turns a text transcript into terminal-styled frames (Pillow) and stitches them with
ffmpeg. Used to film the killer-demo run so it can be spliced with the DataHub UI video.

Run:  python scripts/render_terminal_video.py /tmp/killer_out.txt demo/terminal.mp4
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1440, 900
MARGIN = 48
LINE_H = 30
FONT_PATH = "/System/Library/Fonts/Menlo.ttc"
FONT_SIZE = 19
FPS = 30
BG = (22, 24, 28)
FG = (220, 223, 228)
DIM = (120, 126, 134)
GREEN = (86, 200, 120)
RED = (240, 110, 100)
AMBER = (230, 180, 90)
CYAN = (100, 200, 220)
TITLE = (255, 255, 255)


def _color(line: str):
    s = line.strip()
    if s.startswith("STEP"):
        return TITLE
    if "BLIND" in line or "VERDICT: breaking" in line or "caught deterministically: True" in line:
        return RED if "BLIND" in line else GREEN
    if line.strip().startswith("-->"):
        return AMBER
    if s.startswith(("WHY", "HYPOTHESES", "blast", "existing", "VERDICT", "anomaly")):
        return CYAN
    return FG


def _wrap(text: str, font, draw, max_w: int) -> list[str]:
    words = text.split(" ")
    out, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w and cur:
            cur = trial
        elif not cur:
            cur = w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out or [""]


def render(transcript: Path, out_mp4: Path) -> None:
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
    raw_lines = transcript.read_text().rstrip("\n").split("\n")

    # wrap long lines to the frame width, keep each display line's color
    display: list[tuple[str, tuple]] = []
    for ln in raw_lines:
        col = _color(ln)
        indent = len(ln) - len(ln.lstrip())
        prefix = " " * indent
        for i, seg in enumerate(_wrap(ln.strip(), font, probe, W - 2 * MARGIN - indent * 10)):
            display.append(((prefix if i == 0 else prefix + "  ") + seg, col))

    frames_dir = Path(tempfile.mkdtemp())
    frame_no = 0

    def emit(visible: list[tuple[str, tuple]]):
        nonlocal frame_no
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        # header bar (fake terminal chrome)
        d.rectangle([0, 0, W, 40], fill=(32, 34, 40))
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            d.ellipse([20 + i * 26, 14, 32 + i * 26, 26], fill=c)
        d.text((W // 2 - 130, 12), "semantic-guardian — demo", font=font, fill=DIM)
        y = 60
        for text, col in visible:
            d.text((MARGIN, y), text, font=font, fill=col)
            y += LINE_H
        img.save(frames_dir / f"f{frame_no:05d}.png")
        frame_no += 1

    # type the transcript out line-by-line, holding a few frames per line
    shown: list[tuple[str, tuple]] = []
    for line in display:
        shown = shown + [line]
        hold = 10 if line[0].strip().startswith("STEP") else 6
        for _ in range(hold):
            emit(shown)
    # linger on the final frame
    for _ in range(FPS * 3):
        emit(shown)

    out_mp4.parent.mkdir(exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(frames_dir / "f%05d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_mp4)],
        check=True, capture_output=True,
    )
    print(f"Rendered terminal video: {out_mp4}")


if __name__ == "__main__":
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/killer_out.txt")
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else "demo/terminal.mp4")
    render(src, dst)
