"""Build the STORY demo video: before -> agent -> after, with synced visuals.

Every narrated beat gets a purpose-drawn visual (not a generic card) plus a
burned-in caption, so the screen always shows what the narrator is describing.
Voiceover is generated locally with macOS `say` (no API key); each beat's video
is held to exactly its narration length.

Arc:
  1 intro  2 healthy pipeline  3 change breaks it silently  4 the gap
  5 agent inserted (2 stages)  6 example-1 diff + BLIND stats  7 verdict
  8 durable contract / AI-off still caught  9 real DataHub proof (example 2)
  10 example-2 counterfactual (without vs with)  11 closing

Run:  python scripts/build_story_demo.py
Out:  demo/semantic_guardian_story.mp4
"""
from __future__ import annotations

import subprocess
import tempfile
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEMO = Path(__file__).resolve().parent.parent / "demo"
W, H = 1440, 900
FPS = 30
VOICE = "Samantha"
RATE = 178
CAP_H = 150  # bottom caption strip height

BG = (20, 22, 26)
PANEL = (32, 34, 40)
PANEL2 = (40, 43, 51)
TEXT = (226, 229, 234)
DIM = (128, 134, 143)
GREEN = (90, 200, 122)
RED = (240, 108, 100)
AMBER = (232, 180, 92)
CYAN = (118, 200, 222)
WHITE = (245, 246, 248)
ADD_BG = (28, 58, 40)
DEL_BG = (66, 32, 34)

SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"
f_title = ImageFont.truetype(SANS, 50)
f_h = ImageFont.truetype(SANS, 30)
f_lbl = ImageFont.truetype(SANS, 23)
f_sm = ImageFont.truetype(SANS, 18)
f_cap = ImageFont.truetype(SANS, 27)
mono = ImageFont.truetype(MONO, 20)
mono_sm = ImageFont.truetype(MONO, 17)


# ---------- drawing primitives ---------------------------------------------
def rrect(d, box, r, fill=None, outline=None, width=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def ctext(d, cx, y, text, font, fill):
    w = d.textlength(text, font=font)
    d.text((cx - w / 2, y), text, font=font, fill=fill)


def node(d, cx, cy, w, h, title, sub, color):
    box = [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]
    rrect(d, box, 14, fill=PANEL, outline=color, width=3)
    ctext(d, cx, cy - (28 if sub else 12), title, f_lbl, TEXT)
    if sub:
        ctext(d, cx, cy + 6, sub, f_sm, color)


def arrow(d, x1, y1, x2, y2, color, width=4):
    d.line([x1, y1, x2, y2], fill=color, width=width)
    # arrowhead
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    for da in (2.6, -2.6):
        d.line([x2, y2, x2 + 16 * math.cos(ang + da), y2 + 16 * math.sin(ang + da)],
               fill=color, width=width)


def badge(d, x, y, text, color, font=f_sm):
    tw = d.textlength(text, font=font)
    rrect(d, [x, y, x + tw + 28, y + 34], 17, fill=None, outline=color, width=2)
    d.text((x + 14, y + 7), text, font=font, fill=color)
    return x + tw + 28


def code_panel(d, x, y, w, h, title, lines):
    rrect(d, [x, y, x + w, y + h], 12, fill=PANEL, outline=(60, 64, 74), width=2)
    d.rectangle([x, y, x + w, y + 38], fill=(46, 49, 58))
    d.text((x + 16, y + 8), title, font=f_sm, fill=DIM)
    ly = y + 54
    for text, kind in lines:
        if kind == "add":
            d.rectangle([x + 6, ly - 3, x + w - 6, ly + 24], fill=ADD_BG)
            col, mark = GREEN, "+ "
        elif kind == "del":
            d.rectangle([x + 6, ly - 3, x + w - 6, ly + 24], fill=DEL_BG)
            col, mark = RED, "- "
        else:
            col, mark = TEXT, "  "
        d.text((x + 16, ly), mark + text, font=mono_sm, fill=col)
        ly += 28


def frame() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    return img, ImageDraw.Draw(img)


def caption(img, text):
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - CAP_H, W, H], fill=(12, 13, 16))
    d.line([0, H - CAP_H, W, H - CAP_H], fill=(60, 64, 74), width=2)
    lines = textwrap.wrap(text, width=64)[:3]
    ty = H - CAP_H + (CAP_H - len(lines) * 36) / 2
    for ln in lines:
        ctext(d, W / 2, ty, ln, f_cap, WHITE)
        ty += 36


# ---------- scene renderers (draw everything ABOVE the caption strip) ------
CX = W / 2


def s_intro(d, img):
    ctext(d, CX, 300, "Semantic Guardian", f_title, WHITE)
    ctext(d, CX, 380, "an AI agent that reviews data-pipeline changes", f_h, CYAN)
    ctext(d, CX, 470, "it catches bugs that change MEANING, not shape", f_lbl, DIM)


def _pipeline(d, transform_color, ml_color, ml_sub, show_monitor=False):
    y = 300
    node(d, 300, y, 240, 110, "fct_users_created", "source table", GREEN)
    node(d, 720, y, 240, 110, "dbt transform", "SQL model", transform_color)
    node(d, 1140, y, 240, 110, "churn model", ml_sub, ml_color)
    arrow(d, 420, y, 600, y, DIM)
    arrow(d, 840, y, 1020, y, DIM)
    if show_monitor:
        badge(d, 620, y + 90, "stats monitor: 0 anomalies", GREEN)


def s_healthy(d, img):
    _pipeline(d, GREEN, GREEN, "healthy")


def s_break(d, img):
    _pipeline(d, AMBER, RED, "silently WRONG", show_monitor=True)
    ctext(d, CX, 470, "the numbers look fine  ·  the model is learning from broken data",
          f_lbl, DIM)


def s_gap(d, img):
    ctext(d, CX, 210, "The gap", f_h, RED)
    rrect(d, [300, 300, 700, 470], 14, fill=PANEL, outline=DIM, width=2)
    ctext(d, 500, 340, "Monitors watch", f_lbl, DIM)
    ctext(d, 500, 385, "the SHAPE", f_h, TEXT)
    ctext(d, 500, 425, "counts, ranges, nulls", f_sm, DIM)
    rrect(d, [740, 300, 1140, 470], 14, fill=PANEL, outline=CYAN, width=2)
    ctext(d, 940, 340, "This bug changes", f_lbl, DIM)
    ctext(d, 940, 385, "the MEANING", f_h, CYAN)
    ctext(d, 940, 425, "shape is identical", f_sm, DIM)


def s_agent(d, img):
    y = 280
    node(d, 250, y, 200, 100, "dbt transform", "changed", AMBER)
    node(d, 720, y, 300, 130, "Semantic Guardian", None, CYAN)
    node(d, 1180, y, 200, 100, "churn model", "protected", GREEN)
    arrow(d, 350, y, 560, y, DIM)
    arrow(d, 880, y, 1070, y, DIM)
    # two stages under the guardian
    rrect(d, [590, 400, 850, 448], 10, fill=PANEL2, outline=DIM, width=1)
    d.text((606, 412), "1  cheap stats filter", font=f_sm, fill=DIM)
    rrect(d, [560, 462, 900, 510], 10, fill=PANEL2, outline=CYAN, width=1)
    d.text((576, 474), "2  AI reads the code + DataHub contract", font=f_sm, fill=CYAN)


def s_example1(d, img):
    ctext(d, CX, 175, "Example 1 — account_status inverted", f_h, WHITE)
    code_panel(d, 90, 235, 720, 300, "dbt diff  —  what the engineer shipped", [
        ("SELECT", "ctx"),
        ("  CASE WHEN status = 1 THEN 1  -- active", "del"),
        ("       WHEN status = 1 THEN 0  -- now DELETED", "add"),
        ("       ELSE 0 END AS account_status", "ctx"),
        ("FROM raw.users", "ctx"),
    ])
    rrect(d, [850, 235, 1350, 400], 12, fill=PANEL, outline=CYAN, width=2)
    d.text((872, 252), "DataHub contract says", font=f_sm, fill=DIM)
    d.text((872, 292), "account_status: 1 = active", font=mono, fill=CYAN)
    d.text((872, 330), "0 = deleted", font=mono, fill=CYAN)
    badge(d, 850, 440, "stats filter: 0 anomalies  ·  BLIND", RED, f_lbl)
    d.text((850, 495), "the value set {0,1} never changed", font=f_sm, fill=DIM)


def s_verdict(d, img):
    rrect(d, [120, 190, 1320, 560], 16, fill=PANEL, outline=RED, width=3)
    d.text((150, 212), "AGENT VERDICT", font=f_sm, fill=DIM)
    ctext(d, CX, 240, "breaking  /  categorical_remap", f_h, RED)
    why = ("Why: the CASE inverts the encoding — 1 now maps to deleted while the "
           "catalog declares 1 = active, flipping the meaning of every row.")
    ty = 300
    for ln in textwrap.wrap(why, width=78):
        d.text((150, ty), ln, font=f_lbl, fill=TEXT)
        ty += 34
    d.text((150, 400), "Competing hypotheses (like a careful reviewer):", font=f_sm, fill=DIM)
    d.text((150, 436), "1  intentional recode  —  still a breaking change", font=f_sm, fill=CYAN)
    d.text((150, 468), "2  accidental inversion  —  ship-blocker", font=f_sm, fill=CYAN)
    d.text((150, 512), "reasoned from the code + contract — no hardcoded answer", font=f_sm, fill=DIM)


def s_deterministic(d, img):
    ctext(d, CX, 185, "The agent makes DataHub permanently smarter", f_h, WHITE)
    rrect(d, [130, 260, 690, 470], 14, fill=PANEL, outline=CYAN, width=2)
    ctext(d, 410, 290, "1st run — AI ON", f_lbl, CYAN)
    ctext(d, 410, 345, "agent reasons -> breaking", f_lbl, TEXT)
    ctext(d, 410, 395, "writes a durable contract", f_lbl, TEXT)
    ctext(d, 410, 430, "back into DataHub", f_sm, DIM)
    rrect(d, [750, 260, 1310, 470], 14, fill=PANEL, outline=GREEN, width=3)
    ctext(d, 1030, 290, "re-run same bug — AI OFF", f_lbl, GREEN)
    ctext(d, 1030, 350, "STILL CAUGHT ✓", f_title, GREEN)
    ctext(d, 1030, 425, "the contract alone enforces it now", f_sm, DIM)
    arrow(d, 690, 365, 750, 365, DIM)


def s_counterfactual(d, img):
    ctext(d, CX, 175, "Example 2 — revenue: dollars -> cents  (x 100)", f_h, WHITE)
    rrect(d, [110, 235, 690, 560], 14, fill=PANEL, outline=RED, width=3)
    ctext(d, 400, 262, "WITHOUT the agent", f_lbl, RED)
    d.text((140, 320), "revenue silently 100x too large", font=f_lbl, fill=TEXT)
    d.text((140, 365), "model trains on garbage", font=f_lbl, fill=TEXT)
    d.text((140, 410), "every forecast is wrong", font=f_lbl, fill=RED)
    # broken bar chart
    for i, hgt in enumerate([30, 45, 40, 300, 290, 310]):
        col = RED if hgt > 150 else DIM
        d.rectangle([160 + i * 70, 520 - hgt / 2, 210 + i * 70, 520], fill=col)
    rrect(d, [750, 235, 1330, 560], 14, fill=PANEL, outline=GREEN, width=3)
    ctext(d, 1040, 262, "WITH the agent", f_lbl, GREEN)
    d.text((780, 330), "caught as: unit_scale", font=mono, fill=GREEN)
    d.text((780, 385), "proposes the fix:", font=f_lbl, fill=TEXT)
    d.text((780, 425), "revenue = revenue * 0.01", font=mono, fill=CYAN)
    d.text((780, 490), "forecast stays correct", font=f_lbl, fill=GREEN)


def s_closing(d, img):
    ctext(d, CX, 280, "Two silent bugs.", f_title, WHITE)
    ctext(d, CX, 360, "Every shape-based monitor missed both.", f_h, DIM)
    ctext(d, CX, 440, "Semantic Guardian caught both — by reasoning about meaning.",
          f_h, CYAN)


# ---------- beats: (kind, spec, narration, caption) ------------------------
BEATS = [
    ("draw", s_intro,
     "This is Semantic Guardian, an A.I. agent that reviews data pipeline changes. "
     "Let me show you the problem it solves, and then how it fixes it.",
     "Semantic Guardian — an AI reviewer for data-pipeline changes"),
    ("draw", s_healthy,
     "Here is a normal data pipeline. A source table feeds a transformation, "
     "which feeds a machine learning model. Everything is healthy.",
     "A normal pipeline: source -> transform -> ML model"),
    ("draw", s_break,
     "Now an engineer ships a change to the transformation. The statistical monitor "
     "checks the numbers and sees nothing wrong, zero anomalies. But downstream, the "
     "model is now silently learning from broken data, and no one knows.",
     "Before Guardian: stats monitor sees 0 anomalies — the model breaks silently"),
    ("draw", s_gap,
     "This is the gap. DataHub and statistical monitors watch the shape of the data, "
     "the counts and ranges. But this kind of bug does not change the shape. It changes "
     "the meaning. So on its own, it slips right through.",
     "The gap: monitors watch the data's SHAPE, not its MEANING"),
    ("draw", s_agent,
     "So we built the agent, and we place it directly in the path of every change. "
     "It works in two stages. First a cheap statistical filter. Then the expensive step, "
     "an A.I. that reads the actual code and the data contract from DataHub.",
     "Guardian sits in the change path: (1) stats filter  (2) AI reads code + contract"),
    ("draw", s_example1,
     "Here is a real example. The engineer inverts a column called account status. "
     "One used to mean active. Now one means deleted. But the contract still says one "
     "means active. And notice, the statistical filter is blind, because the set of "
     "values, zeros and ones, did not change at all.",
     "Example 1: account_status inverted (1=active -> 1=deleted). Stats filter: BLIND"),
    ("draw", s_verdict,
     "But the agent reads the code. It reasons, in plain language, that the encoding has "
     "been flipped, which contradicts the declared meaning. Verdict, a breaking change. "
     "It even offers competing hypotheses, the way a careful human reviewer would. "
     "Nothing here is hardcoded, it is reasoning from the evidence.",
     "Agent reasons from the code -> VERDICT: breaking (categorical_remap)"),
    ("draw", s_deterministic,
     "And here is the key idea. Once the owner confirms, the agent writes a permanent "
     "contract back into DataHub. We ran the exact same bad change again with the A.I. "
     "switched off, and it was still caught instantly. The agent taught your catalog a "
     "rule it now enforces forever.",
     "Agent writes a durable contract -> same bug re-run with AI OFF = still caught"),
    ("clip", str(DEMO / "datahub_30.mp4"),
     "And this is real, inside DataHub. Here is a second, different example, revenue "
     "accidentally converted from dollars to cents. The agent tagged the dataset, opened "
     "an incident, and documented exactly what broke, all written back automatically.",
     "Real DataHub write-back — example 2: revenue dollars->cents, tagged + documented"),
    ("draw", s_counterfactual,
     "Why does that second one matter? Without the agent, the revenue model would train "
     "on values a hundred times too large, and every forecast would be wrong. With the "
     "agent, it is caught as a unit scale change, and it even proposes the fix, multiply "
     "by zero point zero one.",
     "Without Guardian: 100x forecast error.  With Guardian: caught + fix proposed (x0.01)"),
    ("draw", s_closing,
     "Two examples, two silent bugs that every shape based monitor missed, both caught by "
     "reasoning about meaning. That is Semantic Guardian.",
     "Catches what shape-based monitors miss — by reasoning about meaning"),
]


# ---------- build ----------------------------------------------------------
def say_to_wav(text, out: Path) -> float:
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), text], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "44100", "-ac", "2", str(out)],
                   check=True, capture_output=True)
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        check=True, capture_output=True, text=True).stdout.strip())


def caption_png(text, path: Path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - CAP_H, W, H], fill=(12, 13, 16, 235))
    d.line([0, H - CAP_H, W, H - CAP_H], fill=(60, 64, 74, 255), width=2)
    lines = textwrap.wrap(text, width=64)[:3]
    ty = H - CAP_H + (CAP_H - len(lines) * 36) / 2
    for ln in lines:
        ctext(d, W / 2, ty, ln, f_cap, WHITE)
        ty += 36
    img.save(path)


def build_beat(kind, spec, wav, dur, tmp, i) -> Path:
    out = tmp / f"beat{i}.mp4"
    pad = dur + 0.5
    if kind == "draw":
        img, d = frame()
        spec(d, img)
        caption(img, BEATS[i][3])
        png = tmp / f"beat{i}.png"
        img.save(png)
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-i", str(wav),
             "-t", f"{pad:.2f}", "-r", str(FPS), "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
            check=True, capture_output=True)
    else:
        cap = tmp / f"cap{i}.png"
        caption_png(BEATS[i][3], cap)
        subprocess.run(
            ["ffmpeg", "-y", "-i", spec, "-i", str(cap), "-i", str(wav),
             "-filter_complex",
             f"[0:v]scale=1440:900,fps={FPS},tpad=stop_mode=clone:stop_duration=90[bg];"
             f"[bg][1:v]overlay=0:0[v]",
             "-map", "[v]", "-map", "2:a", "-t", f"{pad:.2f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
            check=True, capture_output=True)
    return out


def main():
    tmp = Path(tempfile.mkdtemp())
    beats = []
    for i, (kind, spec, narr, _cap) in enumerate(BEATS):
        wav = tmp / f"n{i}.wav"
        dur = say_to_wav(narr, wav)
        print(f"beat {i:2d} {kind:5s}  {dur:5.1f}s")
        beats.append(build_beat(kind, spec, wav, dur, tmp, i))
    concat = tmp / "c.txt"
    concat.write_text("".join(f"file '{b}'\n" for b in beats))
    out = DEMO / "semantic_guardian_story.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-r", str(FPS), str(out)],
        check=True, capture_output=True)
    total = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        check=True, capture_output=True, text=True).stdout.strip()
    print(f"\nFINAL: {out}  ({float(total):.1f}s)")


if __name__ == "__main__":
    main()
