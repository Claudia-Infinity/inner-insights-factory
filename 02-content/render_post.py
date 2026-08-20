#!/usr/bin/env python3
"""Render a Transmission post image (1080x1350) in Claudia's existing template:
cosmic background, uppercase 'TRANSMISSION: TITLE' header, translucent panel, centred monospace body,
©ClaudiaInfinityAI mark at the panel foot.
Usage: render_post.py <background.png> <title> <body.txt|-> <out.jpg>
"""
import sys, textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1080, 1350
FONT_DIR = "/System/Library/Fonts/Supplemental/"
HEAD_FONT = FONT_DIR + "Courier New Bold.ttf"     # TODO swap for Claudia's exact Canva font when she names it
BODY_FONT = FONT_DIR + "Courier New.ttf"
MARK = "©ClaudiaInfinityAI"

def fit_background(path):
    bg = Image.open(path).convert("RGB")
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((round(bg.width * s), round(bg.height * s)), Image.LANCZOS)
    x, y = (bg.width - W) // 2, (bg.height - H) // 2
    return bg.crop((x, y, x + W, y + H))

def wrap(draw, text, font, max_w):
    out = []
    for para in text.split("\n"):
        para = para.strip()
        if not para: continue
        words, line = para.split(), ""
        for w in words:
            t = (line + " " + w).strip()
            if draw.textlength(t, font=font) <= max_w: line = t
            else: out.append(line); line = w
        out.append(line); out.append("")          # blank line between paragraphs
    return out[:-1]

def render(bg_path, title, body, out_path):
    img = fit_background(bg_path)
    draw = ImageDraw.Draw(img)
    # header
    head_font = ImageFont.truetype(HEAD_FONT, 50)
    header = f"TRANSMISSION: {title}".upper()
    while draw.textlength(header, font=head_font) > W - 120 and head_font.size > 34:
        head_font = ImageFont.truetype(HEAD_FONT, head_font.size - 2)
    hy = 95
    draw.text(((W - draw.textlength(header, font=head_font)) / 2, hy), header, font=head_font, fill="white")
    # panel
    px0, py0, px1 = 108, 160, W - 108
    panel_w = px1 - px0
    # body font: shrink until it fits panel height budget
    size = 36
    while True:
        body_font = ImageFont.truetype(BODY_FONT, size)
        lines = wrap(draw, body, body_font, panel_w - 90)
        lh = round(size * 1.22)
        text_h = len(lines) * lh
        py1 = py0 + 55 + text_h + 40 + 60   # top pad + text + gap + mark row
        if py1 <= H - 110 or size <= 24: break
        size -= 1
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([px0, py0, px1, py1], fill=(235, 235, 235, 205))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(img)
    y = py0 + 55
    for ln in lines:
        if ln: draw.text(((W - draw.textlength(ln, font=body_font)) / 2, y), ln, font=body_font, fill=(20, 20, 20))
        y += lh
    mark_font = ImageFont.truetype(BODY_FONT, 30)
    draw.text(((W - draw.textlength(MARK, font=mark_font)) / 2, py1 - 52), MARK, font=mark_font, fill=(20, 20, 20))
    img.convert("RGB").save(out_path, quality=92)
    return out_path

if __name__ == "__main__":
    bg, title, body_src, out = sys.argv[1:5]
    body = sys.stdin.read() if body_src == "-" else open(body_src).read()
    print(render(bg, title, body, out))
