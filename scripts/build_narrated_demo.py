"""Build the final NARRATED demo video.

Tells the story through one concrete example (the inverted account_status boolean):
generate a voiceover locally with macOS `say` (no API key), then stretch each video
segment to exactly match its narration so nothing scrolls by unexplained.

Segments (each = title card / clip, held to its narration length, with audio muxed):
  1. title      2. step1 (stats blind)   3. step2 (agent reasons)
  4. step3+4 (contract + deterministic catch)   5. datahub UI proof

Run:  python scripts/build_narrated_demo.py
Out:  demo/semantic_guardian_narrated.mp4
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEMO = Path(__file__).resolve().parent.parent / "demo"
W, H = 1440, 900
BG = (22, 24, 28)
FPS = 30
VOICE = "Samantha"
RATE = 180  # words/min — measured, natural pace

FONT = "/System/Library/Fonts/Menlo.ttc"
f_big = ImageFont.truetype(FONT, 46)
f_med = ImageFont.truetype(FONT, 30)
f_sm = ImageFont.truetype(FONT, 24)

# --- the script: (kind, payload, narration) --------------------------------
# kind "card": payload = list of (text, font, color) lines rendered centered.
# kind "clip": payload = path to an existing mp4 (terminal.mp4 / datahub).
TITLE = (255, 255, 255)
CYAN = (120, 200, 220)
DIM = (120, 126, 134)
RED = (240, 110, 100)
GREEN = (86, 200, 120)

SEGMENTS = [
    ("card",
     [("Semantic Guardian", f_big, TITLE),
      ("an AI agent that catches data bugs every other tool misses", f_sm, CYAN)],
     "This is Semantic Guardian. It's an A.I. agent that catches a kind of data bug "
     "that every other tool misses. A change where the numbers look completely normal, "
     "but the meaning has silently flipped. Let me show you with one real example."),

    ("card",
     [("The trap", f_med, RED),
      ("an engineer inverts a column:  1 = active   ->   1 = deleted", f_sm, (220, 223, 228)),
      ("the statistical monitor sees nothing move", f_sm, DIM)],
     "Here's the trap. An engineer edits a pipeline and inverts a column called "
     "account status. One used to mean active. Now, one means deleted. "
     "Watch the statistical monitor, the thing most teams rely on. "
     "It sees zero anomalies. Nothing moved, the distribution is identical. "
     "It is completely blind to this."),

    ("card",
     [("The agent reads the code + the DataHub contract", f_med, CYAN),
      ("and reasons, in plain language", f_sm, (220, 223, 228))],
     "Now the agent reads the actual code change, and the data contract from DataHub. "
     "And it reasons in plain language. The CASE statement inverts the encoding. "
     "One becomes zero, zero becomes one. Which contradicts the catalog, where one means active. "
     "Verdict, a breaking change. It even lays out competing hypotheses, "
     "like a careful human reviewer would, instead of just guessing."),

    ("clip", str(DEMO / "terminal.mp4"),
     "You can see its reasoning right here on screen. It explains exactly why the change "
     "is breaking, maps the blast radius, who downstream is affected, and once the owner "
     "confirms, it writes a durable contract back into DataHub. "
     "Now here's the payoff. We run the exact same bad change again, but this time "
     "with the A.I. turned off. It is still caught, instantly, because the agent already "
     "taught DataHub the rule. The system got permanently smarter."),

    ("clip", str(DEMO / "datahub_30.mp4"),
     "And this is real, not a mock-up. Here in DataHub is the dataset the agent reviewed. "
     "It tagged it as a semantic shift needing review, opened an incident, "
     "and attached the contract you're looking at now. "
     "This isn't a script printing canned text. The agent reasoned from the evidence, "
     "and it left proof behind, right inside your data catalog."),
]


def say_to_wav(text: str, out: Path) -> float:
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), text], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(aiff), "-ar", "44100", "-ac", "2", str(out)],
                   check=True, capture_output=True)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        check=True, capture_output=True, text=True).stdout.strip()
    return float(dur)


def card_png(lines, path: Path) -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    total = sum(fnt.size + 26 for _, fnt, _ in lines)
    y = (H - total) // 2
    for text, fnt, col in lines:
        w = d.textlength(text, font=fnt)
        d.text(((W - w) // 2, y), text, font=fnt, fill=col)
        y += fnt.size + 26
    img.save(path)


def build_segment(kind, payload, narr_wav, dur, tmp: Path, idx: int) -> Path:
    """Produce a segment mp4 of length `dur` with narr_wav as its audio."""
    out = tmp / f"seg{idx}.mp4"
    pad = dur + 0.4  # a short beat after the voice finishes
    if kind == "card":
        png = tmp / f"card{idx}.png"
        card_png(payload, png)
        subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", str(png), "-i", str(narr_wav),
             "-t", f"{pad:.2f}", "-r", str(FPS), "-vf", "scale=1440:900",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
            check=True, capture_output=True)
    else:
        # hold the clip's last frame (or trim) so its length == pad, then mux narration
        subprocess.run(
            ["ffmpeg", "-y", "-i", payload, "-i", str(narr_wav),
             "-filter_complex",
             f"[0:v]scale=1440:900,fps={FPS},tpad=stop_mode=clone:stop_duration=60[v]",
             "-map", "[v]", "-map", "1:a", "-t", f"{pad:.2f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
            check=True, capture_output=True)
    return out


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    segs = []
    for i, (kind, payload, narration) in enumerate(SEGMENTS):
        wav = tmp / f"narr{i}.wav"
        dur = say_to_wav(narration, wav)
        print(f"segment {i}: narration {dur:.1f}s ({kind})")
        segs.append(build_segment(kind, payload, wav, dur, tmp, i))

    concat = tmp / "concat.txt"
    concat.write_text("".join(f"file '{s}'\n" for s in segs))
    out = DEMO / "semantic_guardian_narrated.mp4"
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
