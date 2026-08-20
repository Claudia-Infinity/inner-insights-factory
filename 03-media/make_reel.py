#!/usr/bin/env python3
"""Runway avatar_videos output (1088x704 landscape, portrait pillarboxed) -> 1080x1920 reel with burned-in captions.
Captions are rendered as transparent PNGs (Pillow) and overlaid with time windows (this ffmpeg has no libass/drawtext).
Usage: make_reel.py <in.mp4> <script.txt|-> <out.mp4> [--title "The People Who Stay"]
Timing: Runway gives no word timestamps; chunks are spread across the audio duration proportionally to character count.
"""
import sys, re, subprocess, json, os, tempfile, shutil
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
# 3:4 centre crop (528x704) scaled to 1080x1440, laid over a blurred full-bleed version of itself (1080x1920).
CROP = ("split[a][b];[a]crop=528:704:280:0,scale=1080:1920:flags=lanczos,boxblur=30:5,eq=brightness=-0.15[bg];"
        "[b]crop=528:704:280:0,scale=1080:1440:flags=lanczos[fg];[bg][fg]overlay=0:240")
FONT_DIR = "/System/Library/Fonts/Supplemental/"
CAP_FONT, CAP_SIZE = FONT_DIR + "Courier New Bold.ttf", 56
TITLE_FONT, TITLE_SIZE = FONT_DIR + "Courier New Bold.ttf", 44
CAP_Y = 1480          # caption block centre: over the bottom of the picture + top of the lower pad
TITLE_Y = 150         # in the top pad (TikTok clear; IG header is left-aligned and thin)

def duration(path):
    p = subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","json",path],capture_output=True,text=True)
    return float(json.loads(p.stdout)["format"]["duration"])

def chunks(text, max_chars=72):
    sents = re.split(r'(?<=[.!?])\s+', " ".join(text.split()))
    out = []
    for s in sents:
        if len(s) <= max_chars: out.append(s); continue
        cur = ""
        for p in re.split(r'(?<=[,;:])\s+', s):
            if len(cur) + len(p) + 1 <= max_chars: cur = (cur + " " + p).strip()
            else:
                if cur: out.append(cur)
                cur = p
        if cur: out.append(cur)
    final = []
    for c in out:
        while len(c) > max_chars:
            cut = c.rfind(" ", 0, max_chars); cut = cut if cut > 20 else max_chars
            final.append(c[:cut]); c = c[cut:].strip()
        if c: final.append(c)
    return final

def wrap(draw, text, font, max_w):
    words, lines, line = text.split(), [], ""
    for w in words:
        t = (line + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w: line = t
        else: lines.append(line); line = w
    lines.append(line); return lines

def text_png(path, text, font_path, size, cy, max_w=920, fill="white"):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    font = ImageFont.truetype(font_path, size)
    lines = wrap(d, text, font, max_w); lh = round(size * 1.25)
    y = cy - (len(lines) * lh) // 2
    for ln in lines:
        x = (W - d.textlength(ln, font=font)) / 2
        d.text((x, y), ln, font=font, fill=fill, stroke_width=4, stroke_fill=(0, 0, 0, 200))
        y += lh
    img.save(path)

def main():
    args = sys.argv[1:]; title = None
    if "--title" in args:
        i = args.index("--title"); title = args[i + 1]; del args[i:i + 2]
    src, script_src, out = args
    text = sys.stdin.read() if script_src == "-" else open(script_src).read()
    total = duration(src); caps = chunks(text)
    tmp = tempfile.mkdtemp(prefix="reel_")
    total_chars = sum(map(len, caps)) or 1; lead = 0.3; usable = total - lead
    inputs, filters, t = ["-i", src], [], lead
    windows = []
    for i, c in enumerate(caps):
        p = f"{tmp}/cap{i:03d}.png"; text_png(p, c, CAP_FONT, CAP_SIZE, CAP_Y)
        d = usable * len(c) / total_chars; windows.append((p, t, t + d)); t += d
    if title:
        p = f"{tmp}/title.png"; text_png(p, f"TRANSMISSION: {title.upper()}", TITLE_FONT, TITLE_SIZE, TITLE_Y, max_w=960)
        windows.append((p, 0, total))
    for p, a, b in windows: inputs += ["-i", p]
    prev = "[base]"; filters.append(f"[0:v]{CROP}[base]")
    for i, (p, a, b) in enumerate(windows):
        nxt = f"[v{i}]"
        filters.append(f"{prev}[{i+1}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'{nxt}"); prev = nxt
    cmd = ["ffmpeg","-v","error","-y",*inputs,"-filter_complex",";".join(filters),"-map",prev,"-map","0:a?",
           "-c:v","libx264","-crf","19","-preset","veryfast","-pix_fmt","yuv420p","-c:a","aac","-b:a","160k","-movflags","+faststart",out]
    subprocess.run(cmd, check=True); shutil.rmtree(tmp); print(out)

if __name__ == "__main__": main()
