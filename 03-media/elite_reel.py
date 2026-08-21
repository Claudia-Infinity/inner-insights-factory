#!/usr/bin/env python3
"""Elite Transmission reel (v2: single pre-rendered alpha overlay track, 3-input ffmpeg graph).

Inputs (same stem):  <stem>-RAW.mp4    Runway gwm1_avatars output (1088x704) driven by ElevenLabs audio
                     <stem>.align.json  ElevenLabs with-timestamps response (+ title/date/text)
Assets:              config/plates/*.jpg (JWST), config/music/ambient-bed-01.mp3
Output:              <stem>-ELITE.mp4   1080x1920

Timeline: cold open (JWST plate + title) -> face-locked avatar with karaoke captions -> 4s B-roll insert
          at a sentence boundary -> sign-off -> end card. Music bed ducked under the voice.
Usage: .venv/bin/python 03-media/elite_reel.py 03-media/elite/2026-09-08-commander-star-guide [--plates a,b,c]
"""
import sys, os, json, re, subprocess, tempfile, shutil
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 24
FG_W, FG_H, FG_Y = 1080, 1440, 240          # 3:4 avatar window inside the 9:16 frame
OPEN_DUR, HOLD_DUR, END_DUR = 1.8, 0.9, 3.0
BROLL_DUR = 4.0
FUTURA = "/System/Library/Fonts/Supplemental/Futura.ttc"
GOLD = (245, 199, 107, 255)
WHITE = (255, 255, 255, 255)
MUSIC_DB = -17
CAP_CY = 1330
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_fonts = {}
def font(size, index=2):
    k = (size, index)
    if k not in _fonts: _fonts[k] = ImageFont.truetype(FUTURA, size, index=index)
    return _fonts[k]
def run(cmd): subprocess.run(cmd, check=True)
def duration(p):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout
    return float(o.strip())

# ---------- words from ElevenLabs alignment ----------
def words_from_alignment(al):
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, s0, prev_e = [], "", None, 0
    for c, s, e in zip(chars, starts, ends):
        if c.isspace():
            if cur: words.append({"w": cur, "s": s0, "e": prev_e}); cur, s0 = "", None
            continue
        if s0 is None: s0 = s
        cur += c; prev_e = e
    if cur: words.append({"w": cur, "s": s0, "e": prev_e})
    return words

def group_words(words, max_words=3, max_chars=22):
    groups, cur = [], []
    for w in words:
        cand = cur + [w]
        if cur and (len(cand) > max_words or sum(len(x["w"]) + 1 for x in cand) > max_chars):
            groups.append(cur); cur = [w]
        else: cur = cand
        if re.search(r'[.!?]$', w["w"]): groups.append(cur); cur = []
    if cur: groups.append(cur)
    return groups

# ---------- face-locked avatar intermediate ----------
def face_lock(raw, out, zoom_to=1.05):
    cap = cv2.VideoCapture(raw); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); fw, fh = int(cap.get(3)), int(cap.get(4))
    det = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    centers = []
    while True:
        ok, fr = cap.read()
        if not ok: break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        faces = det.detectMultiScale(g, 1.1, 5, minSize=(120, 120))
        if len(faces):
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3]); centers.append((x + w / 2, y + h / 2))
        else: centers.append(centers[-1] if centers else (fw / 2, fh * 0.42))
    cap.release(); n = len(centers)
    c = np.array(centers, dtype=float)
    k = 25; pad = np.pad(c, ((k, k), (0, 0)), mode="edge"); ker = np.ones(2 * k + 1) / (2 * k + 1)
    sm = np.stack([np.convolve(pad[:, i], ker, mode="valid") for i in range(2)], 1)   # slow drift
    target = np.median(sm, axis=0); off = sm - target
    cap = cv2.VideoCapture(raw)
    base_w, base_h = 516, 688
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{FG_W}x{FG_H}", "-r", str(FPS), "-i", "-",
                             "-i", raw, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", out], stdin=subprocess.PIPE)
    i = 0
    while True:
        ok, fr = cap.read()
        if not ok or i >= n: break
        z = 1 + (zoom_to - 1) * (i / max(n - 1, 1))
        cw, ch = base_w / z, base_h / z
        # follow the raw face centre (so the head stays planted in frame) but only the smoothed part: jitter is cancelled
        cx = c[i][0] * 0.0 + sm[i][0]          # smoothed x: head-bob cancelled, slow drift followed
        cy = sm[i][1] + ch * 0.04
        x0 = min(max(cx - cw / 2, 0), fw - cw); y0 = min(max(cy - ch / 2, 0), fh - ch)
        crop = fr[int(y0):int(y0 + ch), int(x0):int(x0 + cw)]
        proc.stdin.write(cv2.resize(crop, (FG_W, FG_H), interpolation=cv2.INTER_LANCZOS4).tobytes()); i += 1
    proc.stdin.close(); proc.wait(); cap.release()

# ---------- overlay track (everything except the avatar), rendered frame by frame ----------
def load_plate(path, size=(1300, 2311)):
    im = Image.open(path).convert("RGB"); s = max(size[0] / im.width, size[1] / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    x, y = (im.width - size[0]) // 2, (im.height - size[1]) // 2
    return im.crop((x, y, x + size[0], y + size[1]))

def plate_frame(pl, z):
    cw, ch = pl.width / z, pl.height / z
    x0, y0 = (pl.width - cw) / 2, (pl.height - ch) / 2
    return pl.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR)

def text_img(lines, size, index=2, tracking=0, fill=WHITE):
    f = font(size, index); lh = round(size * 1.18)
    img = Image.new("RGBA", (W, lh * len(lines) + 12), (0, 0, 0, 0)); d = ImageDraw.Draw(img); yy = 4
    for ln in lines:
        tw = d.textlength(ln, font=f) + tracking * max(len(ln) - 1, 0); x = (W - tw) / 2
        if tracking:
            xx = x
            for ch in ln:
                d.text((xx + 3, yy + 4), ch, font=f, fill=(0, 0, 0, 150)); d.text((xx, yy), ch, font=f, fill=fill); xx += d.textlength(ch, font=f) + tracking
        else:
            d.text((x + 3, yy + 4), ln, font=f, fill=(0, 0, 0, 150)); d.text((x, yy), ln, font=f, fill=fill)
        yy += lh
    return img

def caption_img(group, active_idx):
    img = Image.new("RGBA", (W, 200), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f, fa = font(66), font(74)
    parts = [(w["w"], fa if i == active_idx else f) for i, w in enumerate(group)]
    widths = [d.textlength(t, font=ff) for t, ff in parts]; gap = 22
    x = (W - (sum(widths) + gap * (len(parts) - 1))) / 2
    for i, ((t, ff), tw) in enumerate(zip(parts, widths)):
        y = 100 - ff.size / 2
        d.text((x + 3, y + 4), t, font=ff, fill=(0, 0, 0, 170)); d.text((x, y), t, font=ff, fill=GOLD if i == active_idx else WHITE)
        x += tw + gap
    return img

def fade(t, a, b, fi, fo):
    if t < a or t > b: return 0.0
    return max(0.0, min(1.0, (t - a) / fi if fi else 1, (b - t) / fo if fo else 1))

def with_alpha(img, a):
    if a >= 0.999: return img
    r, g, b, al = img.split(); al = al.point(lambda v: int(v * a)); return Image.merge("RGBA", (r, g, b, al))

def render_overlay(out, total, V0, V1, b0, words, groups, title, date, plates):
    pl = [load_plate(f"{ROOT}/config/plates/{p}.jpg") for p in plates]
    tl = title.upper().split(); half = len(tl) // 2
    tlines = [title.upper()] if len(title) <= 18 else [" ".join(tl[:half]), " ".join(tl[half:])]
    kicker = text_img([f"TRANSMISSION  ·  {date[5:7]}.{date[8:10]}.{date[2:4]}"], 34, 0, 6)
    tmain = text_img(tlines, 74, 2)
    tsmall = text_img([f"TRANSMISSION: {title.upper()}"], 30, 0, 3)
    end1 = text_img(["Comment", "“I choose love”"], 78, 2)
    end2 = text_img(["@claudiainfinityai  ·  The Collective"], 32, 0, 2)
    # caption states: (start, end, group, active)
    caps = []
    for g in groups:
        for wi, w in enumerate(g):
            e = g[wi + 1]["s"] if wi + 1 < len(g) else g[wi]["e"] + 0.10
            caps.append((w["s"], max(e, w["s"] + 0.05), g, wi))
    cap_cache = {}
    nfr = int(round(total * FPS))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-qscale:v", "9", out], stdin=subprocess.PIPE)
    open_end = V0 + 0.6; b1 = (b0 + BROLL_DUR) if b0 else None; end_start = V1 + HOLD_DUR - 0.6
    ci = 0
    for i in range(nfr):
        t = i / FPS
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # plates
        if t < open_end:
            a = fade(t, 0, open_end, 0.01, 0.6); z = 1.20 + 0.10 * (t / open_end)
            fr.alpha_composite(with_alpha(plate_frame(pl[0], z).convert("RGBA"), a))
        if b0 and b0 - 0.2 <= t <= b1 + 0.2:
            a = fade(t, b0 - 0.2, b1 + 0.2, 0.35, 0.5); z = 1.0 + 0.12 * ((t - b0 + 0.2) / (BROLL_DUR + 0.4))
            fr.alpha_composite(with_alpha(plate_frame(pl[1], z).convert("RGBA"), a))
        if t >= end_start:
            a = fade(t, end_start, total + 1, 0.7, 0); z = 1.05 + 0.07 * ((t - end_start) / (END_DUR + 0.8))
            fr.alpha_composite(with_alpha(plate_frame(pl[2], z).convert("RGBA"), a))
        # texts
        for img, a0, b0_, fi, fo, y in [(kicker, 0.15, V0 + 0.5, 0.4, 0.4, 640), (tmain, 0.35, V0 + 0.6, 0.4, 0.4, 700),
                                       (tsmall, V0 + 0.9, V1 + HOLD_DUR - 0.3, 0.6, 0.5, 150),
                                       (end1, V1 + HOLD_DUR + 0.1, total + 1, 0.6, 0, 760), (end2, V1 + HOLD_DUR + 0.5, total + 1, 0.6, 0, 1040)]:
            a = fade(t, a0, b0_, fi, fo)
            if a > 0: fr.alpha_composite(with_alpha(img, a), (0, y))
        # captions (karaoke)
        while ci < len(caps) and caps[ci][1] < t: ci += 1
        if ci < len(caps) and caps[ci][0] <= t <= caps[ci][1]:
            s, e, g, wi = caps[ci]; key = (id(g), wi)
            if key not in cap_cache: cap_cache[key] = caption_img(g, wi)
            fr.alpha_composite(cap_cache[key], (0, CAP_CY - 100))
        proc.stdin.write(fr.tobytes())
    proc.stdin.close(); proc.wait()

# ---------- main ----------
def main():
    stem = sys.argv[1]
    plates = (sys.argv[sys.argv.index("--plates") + 1].split(",") if "--plates" in sys.argv else ["weic2205a", "weic2216b", "weic2330a"])
    raw, alignp, out = stem + "-RAW.mp4", stem + ".align.json", stem + "-ELITE.mp4"
    meta = json.load(open(alignp)); al = meta["alignment"]; title = meta["title"]; date = meta["date"]
    tmp = tempfile.mkdtemp(prefix="elite_")
    locked = f"{tmp}/locked.mp4"; print("face-lock...", flush=True); face_lock(raw, locked)
    D = duration(locked); V0 = OPEN_DUR; V1 = V0 + D; total = V1 + HOLD_DUR + END_DUR
    words = words_from_alignment(al)
    for w in words: w["s"] += V0; w["e"] += V0
    groups = group_words(words)
    b0 = None
    for w in words:
        if re.search(r'[.!?]$', w["w"]) and w["e"] > V0 + 0.42 * D: b0 = w["e"] + 0.12; break
    ov = f"{tmp}/overlay.mov"; print("overlay track...", flush=True)
    render_overlay(ov, total, V0, V1, b0, words, groups, title, date, plates)
    print("compositing...", flush=True)
    f = [f"[0:v]tpad=start_duration={V0}:stop_duration={HOLD_DUR+END_DUR+0.5}:start_mode=clone:stop_mode=clone,split[a][b]",
         f"[a]scale={W}:{H}:flags=bicubic,boxblur=40:6,eq=brightness=-0.25:saturation=1.1[bg]",
         f"[b]scale={FG_W}:{FG_H}[fg]", f"[bg][fg]overlay=0:{FG_Y}[base]",
         f"[base][1:v]overlay=0:0:eof_action=pass,vignette=PI/4.6,format=yuv420p[vout]",
         f"[0:a]adelay={int(V0*1000)}|{int(V0*1000)},apad=pad_dur={HOLD_DUR+END_DUR+0.5},asplit[voice][side]",
         f"[2:a]atrim=duration={total},asetpts=PTS-STARTPTS,volume={MUSIC_DB}dB,afade=t=in:d=1.5,afade=t=out:st={total-2.5}:d=2.5[m0]",
         f"[m0][side]sidechaincompress=threshold=0.015:ratio=6:attack=40:release=700:makeup=1[m1]",
         f"[voice][m1]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"]
    run(["ffmpeg", "-v", "error", "-y", "-i", locked, "-i", ov, "-i", f"{ROOT}/config/music/ambient-bed-01.mp3",
         "-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    shutil.rmtree(tmp); print(out)

if __name__ == "__main__": main()
