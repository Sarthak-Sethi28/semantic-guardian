"""Assemble the final demo from REAL footage + Samantha narration.

Segments (each held to its narration, audio muxed):
  1 hero.mp4 (animated)      2 problem card
  3 terminal_live.mp4 (real live run)   4 datahub_assertions.mp4 (real, lands on contracts)
  5 payoff card              6 close card

Out: demo/semantic_guardian_final.mp4
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
RATE = 176

BG = (13, 15, 20)
SANS = "/System/Library/Fonts/Helvetica.ttc"
f_big = ImageFont.truetype(SANS, 52)
f_h = ImageFont.truetype(SANS, 34)
f_sm = ImageFont.truetype(SANS, 25)
f_cap = ImageFont.truetype(SANS, 28)
WHITE = (245, 246, 248)
CYAN = (90, 208, 230)
RED = (240, 108, 100)
GREEN = (89, 200, 122)
DIM = (123, 130, 141)


def ctext(d, cx, y, t, f, c):
    d.text((cx - d.textlength(t, font=f) / 2, y), t, font=f, fill=c)


# ---- scene cards (for segments that aren't footage) ----
def card_problem(d):
    ctext(d, W / 2, 210, "The trap", f_h, RED)
    ctext(d, W / 2, 330, "An engineer inverts a column:", f_sm, DIM)
    ctext(d, W / 2, 380, "1 = active   becomes   1 = deleted", f_big, WHITE)
    ctext(d, W / 2, 500, "The numbers are identical. The meaning flipped.", f_sm, DIM)
    ctext(d, W / 2, 555, "Every statistical monitor sees zero anomalies.", f_sm, RED)


def card_payoff(d):
    ctext(d, W / 2, 250, "Then we re-run the same bad change", f_h, WHITE)
    ctext(d, W / 2, 320, "with the AI switched OFF", f_h, DIM)
    ctext(d, W / 2, 470, "STILL CAUGHT", f_big, GREEN)
    ctext(d, W / 2, 560, "the contract alone enforces it now — no model needed", f_sm, DIM)


def card_revenue(d):
    ctext(d, W / 2, 200, "A second example", f_h, CYAN)
    ctext(d, W / 2, 320, "revenue: dollars  to  cents", f_big, WHITE)
    ctext(d, W / 2, 420, "an engineer divides revenue by 100", f_sm, DIM)
    ctext(d, W / 2, 470, "every downstream number is now 100x off", f_sm, RED)
    ctext(d, W / 2, 575, "next: what the agent wrote back into DataHub", f_sm, DIM)


def _panel(d, x0, y0, x1, y1, color):
    d.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=(26, 29, 36), outline=color, width=3)


def card_anomaly(d):
    # the two-stage story: cheap layer FIRES when it should, stays QUIET when it should
    ctext(d, W / 2, 120, "Two stages: a cheap filter guards an expensive brain", f_h, WHITE)
    ctext(d, W / 2, 172, "the statistical layer decides WHEN the LLM is worth calling", f_sm, DIM)
    # left: FIRES
    _panel(d, 120, 260, 690, 620, RED)
    ctext(d, 405, 290, "null rate spikes  0.2%  ->  41%", f_sm, WHITE)
    ctext(d, 405, 360, "FIRES", f_big, RED)
    ctext(d, 405, 445, "confidence 1.00", f_sm, DIM)
    ctext(d, 405, 500, "escalates to the LLM", f_sm, WHITE)
    ctext(d, 405, 545, "(a real shift — worth the spend)", f_sm, DIM)
    # right: QUIET
    _panel(d, 750, 260, 1320, 620, GREEN)
    ctext(d, 1035, 290, "normal day-over-day drift", f_sm, WHITE)
    ctext(d, 1035, 360, "QUIET", f_big, GREEN)
    ctext(d, 1035, 445, "0 signals", f_sm, DIM)
    ctext(d, 1035, 500, "never calls the LLM", f_sm, WHITE)
    ctext(d, 1035, 545, "(no false alarms, no wasted cost)", f_sm, DIM)


def card_blast(d):
    ctext(d, W / 2, 130, "It also knows the blast radius", f_h, WHITE)
    ctext(d, W / 2, 182, "walks DataHub lineage to find who breaks downstream", f_sm, DIM)
    # mini lineage: fct_revenue -> revenue_forecast (ML feature)
    cy = 400
    _panel(d, 210, cy - 55, 560, cy + 55, RED)
    ctext(d, 385, cy - 26, "fct_revenue", f_sm, WHITE)
    ctext(d, 385, cy + 6, "changed dataset", f_sm, DIM)
    d.line([560, cy, 880, cy], fill=DIM, width=4)
    d.polygon([(880, cy), (864, cy - 8), (864, cy + 8)], fill=DIM)
    _panel(d, 880, cy - 55, 1240, cy + 55, CYAN)
    ctext(d, 1060, cy - 26, "revenue_forecast", f_sm, WHITE)
    ctext(d, 1060, cy + 6, "ML feature", f_sm, CYAN)
    ctext(d, W / 2, 560, "severity: medium   ·   1 downstream ML feature impacted", f_sm, DIM)


def card_close(d):
    ctext(d, W / 2, 360, "Semantic Guardian", f_big, WHITE)
    ctext(d, W / 2, 450, "catches what shape-based monitors miss —", f_sm, DIM)
    ctext(d, W / 2, 490, "by reasoning about meaning.", f_sm, CYAN)


CARDS = {"problem": card_problem, "payoff": card_payoff, "close": card_close,
         "revenue": card_revenue, "anomaly": card_anomaly, "blast": card_blast}

# ---- the timeline ----
# kind: "clip" -> footage path; "card" -> card name
# clips take an optional start-offset (seconds into the footage) as a 5th field.
SEG = [
    ("clip", "hero.mp4", None,
     "This is Semantic Guardian, an A.I. agent that catches a kind of data bug every "
     "other tool misses. A change where the numbers look normal, but the meaning "
     "silently flipped.", 0),
    ("card", "problem", "The trap: 1=active becomes 1=deleted — monitors see nothing",
     "Here is the trap. An engineer inverts a column. One used to mean active, now one "
     "means deleted. The numbers are identical, so every statistical monitor sees zero "
     "anomalies and lets it through.", 0),
    ("clip", "terminal_live.mp4", None,
     "But the agent reads the actual code and the contract from DataHub. In a real run, "
     "it reasons that the encoding is inverted, contradicting the declared meaning. "
     "Verdict, a breaking change. It even weighs competing hypotheses, the way a careful "
     "reviewer would.", 0),
    # anomaly layer earning its place: it's a cost-aware two-stage design.
    ("card", "anomaly", None,
     "And it is efficient. A cheap statistical layer decides when the expensive A.I. is "
     "even worth calling. When a null rate suddenly spikes, it fires and escalates. On "
     "normal drift, it stays silent, so there are no false alarms and no wasted cost.", 0),
    # the new "one scene" you asked for: introduce the revenue example on its own,
    # so the DataHub screen (which shows fct_revenue) makes sense.
    ("card", "revenue", None,
     "Here is a second example, on a different dataset. Revenue was accidentally changed "
     "from dollars to cents, divided by a hundred. Every downstream number is now a "
     "hundred times off.", 0),
    # start at 32s: opens on the Quality tab with the SEMANTIC CONTRACT cards.
    # narration kept short so it matches the real footage motion — no frozen frame.
    ("clip", "datahub_assertions.mp4", "Real DataHub — the semantic contracts the agent wrote back",
     "The agent caught it, and this is what it wrote back into DataHub. Three durable "
     "semantic contracts, right here in the Quality tab. Real proof, in your catalog.", 32),
    # blast radius: deep DataHub lineage integration.
    ("card", "blast", None,
     "It also walks DataHub's lineage to find the blast radius. This revenue change "
     "flows downstream into a machine-learning feature, revenue forecast, so the agent "
     "flags it as medium severity and routes it to the right owner.", 0),
    ("card", "payoff", "Re-run with the AI OFF — still caught, by the contract alone",
     "Here is the key idea. We re-run the exact same bad change with the A.I. switched "
     "off. It is still caught, instantly, because the agent already taught DataHub the "
     "rule. The system got permanently smarter.", 0),
    ("card", "close", None,
     "Two silent bugs that shape-based monitors miss, both caught by reasoning about "
     "meaning. That is Semantic Guardian.", 0),
]


AUDIO_DIR = DEMO / "audio"  # if demo/audio/1.mp3..9.mp3 exist, use them (real voiceover)


def _dur(path) -> float:
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(path)],
        check=True, capture_output=True, text=True).stdout.strip())


def narr_wav(text, out, i):
    """Segment i's audio: prefer demo/audio/<i+1>.mp3 (real voiceover); else macOS say."""
    supplied = AUDIO_DIR / f"{i + 1}.mp3"
    if supplied.exists():
        # normalise to a consistent wav so muxing/concat is clean
        subprocess.run(["ffmpeg", "-y", "-i", str(supplied), "-ar", "44100", "-ac", "2",
                        str(out)], check=True, capture_output=True)
        return _dur(out)
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), text], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "44100", "-ac", "2", str(out)],
                   check=True, capture_output=True)
    return _dur(out)


def cap_png(text, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, H - 92, W, H], fill=(8, 9, 12, 235))
    lines = textwrap.wrap(text, width=70)[:2]
    y = H - 92 + (92 - len(lines) * 34) / 2
    for ln in lines:
        ctext(d, W / 2, y, ln, f_cap, WHITE)
        y += 34
    img.save(path)


def build(kind, ref, cap, wav, dur, tmp, i, start=0):
    out = tmp / f"s{i}.mp4"
    pad = dur + 0.45
    if kind == "card":
        img = Image.new("RGB", (W, H), BG)
        CARDS[ref](ImageDraw.Draw(img))
        png = tmp / f"c{i}.png"
        img.save(png)
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-i", str(wav),
             "-t", f"{pad:.2f}", "-r", str(FPS), "-c:v", "libx264",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
            check=True, capture_output=True)
    else:
        src = DEMO / ref
        seek = ["-ss", str(start)] if start else []
        inputs = [*seek, "-i", str(src), "-i", str(wav)]
        if cap:
            cp = tmp / f"cap{i}.png"
            cap_png(cap, cp)
            inputs += ["-i", str(cp)]
            fc = (f"[0:v]scale=1440:900,fps={FPS},setpts=PTS-STARTPTS,"
                  f"tpad=stop_mode=clone:stop_duration=90[bg];[bg][2:v]overlay=0:0[v]")
        else:
            fc = (f"[0:v]scale=1440:900,fps={FPS},setpts=PTS-STARTPTS,"
                  f"tpad=stop_mode=clone:stop_duration=90[v]")
        subprocess.run(
            ["ffmpeg", "-y", *inputs, "-filter_complex", fc,
             "-map", "[v]", "-map", "1:a", "-t", f"{pad:.2f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
            check=True, capture_output=True)
    return out


def main():
    tmp = Path(tempfile.mkdtemp())
    segs = []
    for i, (kind, ref, cap, narr, start) in enumerate(SEG):
        wav = tmp / f"n{i}.wav"
        dur = narr_wav(narr, wav, i)
        src = "voiceover" if (AUDIO_DIR / f"{i + 1}.mp3").exists() else "say"
        print(f"seg {i} {kind:4s} {ref:26s} {dur:5.1f}s  (start={start}, {src})")
        segs.append(build(kind, ref, cap, wav, dur, tmp, i, start))
    concat = tmp / "c.txt"
    concat.write_text("".join(f"file '{s}'\n" for s in segs))
    out = DEMO / "semantic_guardian_final.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-r", str(FPS), str(out)],
        check=True, capture_output=True)
    total = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(out)],
        check=True, capture_output=True, text=True).stdout.strip()
    print(f"\nFINAL: {out}  ({float(total):.1f}s)")


if __name__ == "__main__":
    main()
