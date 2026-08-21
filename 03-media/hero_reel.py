#!/usr/bin/env python3
"""Hero Transmission reel: full-bleed Act-Two performance, cinematic sound design, soft captions.

Folder layout (03-media/hero/):
  seg1.mp4, seg2.mp4   Act-Two outputs (720x1280) for the two halves of the reference, split at SPLIT seconds
  broll.mp4            5s generated clip, laid over the seam
  voice.mp3 + voice.align.json   ElevenLabs v3 with-timestamps
  music.mp3, sfx-breath.mp3, sfx-whoosh.mp3, sfx-drone.mp3, sfx-shimmer.mp3
  world.png            her in the world (end card)
Usage: .venv/bin/python 03-media/hero_reel.py 03-media/hero <split_seconds> <out.mp4>
"""
import sys, os, json, re, subprocess, tempfile, shutil, math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 24
FUTURA = "/System/Library/Fonts/Supplemental/Futura.ttc"
HOLD, ENDCARD = 1.3, 3.6
BROLL_BEFORE, BROLL_AFTER = 1.9, 2.3
_f = {}
def font(size, index=0):
    if (size, index) not in _f: _f[(size, index)] = ImageFont.truetype(FUTURA, size, index=index)
    return _f[(size, index)]
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print("FFMPEG ERROR:\n" + r.stderr[-3000:]); raise SystemExit(r.returncode)
def dur(p): return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())

def words_from_alignment(al):
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, s0, pe = [], "", None, 0
    for c, s, e in zip(chars, st, en):
        if c.isspace():
            if cur: words.append({"w": cur, "s": s0, "e": pe}); cur, s0 = "", None
            continue
        if s0 is None: s0 = s
        cur += c; pe = e
    if cur: words.append({"w": cur, "s": s0, "e": pe})
    # drop v3 audio tags and bare ellipses
    return [w for w in words if not w["w"].startswith("[") and re.search(r"[A-Za-z]", w["w"])]

def phrases(words, max_words=4, max_chars=26):
    out, cur = [], []
    for w in words:
        cand = cur + [w]
        if cur and (len(cand) > max_words or sum(len(x["w"]) + 1 for x in cand) > max_chars): out.append(cur); cur = [w]
        else: cur = cand
        t = w["w"]
        if re.search(r"[.!?]$", t) and not t.endswith("...") and not t.endswith("…"): out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def clean(t): return t.replace("...", "").replace("…", "").strip()

# ---------- sprites ----------
def glow_sprite(r, color=(255, 236, 190)):
    s = Image.new("RGBA", (r * 4, r * 4), (0, 0, 0, 0)); d = ImageDraw.Draw(s)
    d.ellipse([r, r, 3 * r, 3 * r], fill=color + (255,)); return s.filter(ImageFilter.GaussianBlur(r * 0.9))

def sun_glow():
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(g)
    for i in range(18, 0, -1):
        a = int(5 * (18 - i) / 18 + 1); rad = 220 + i * 44
        d.ellipse([200 - rad, 330 - rad, 200 + rad, 330 + rad], fill=(255, 214, 150, a))
    return g.filter(ImageFilter.GaussianBlur(40))

def text_img(lines, size, index=0, tracking=0, fill=(255, 255, 255, 255), shadow=150):
    f = font(size, index); lh = round(size * 1.2)
    img = Image.new("RGBA", (W, lh * len(lines) + 16), (0, 0, 0, 0)); d = ImageDraw.Draw(img); yy = 6
    for ln in lines:
        tw = d.textlength(ln, font=f) + tracking * max(len(ln) - 1, 0); x = (W - tw) / 2
        xs = x
        for ch in (ln if tracking else [ln]):
            d.text((xs + 2, yy + 3), ch, font=f, fill=(0, 0, 0, shadow)); d.text((xs, yy), ch, font=f, fill=fill)
            xs += d.textlength(ch, font=f) + tracking
        yy += lh
    return img

def caption_img(group, active):
    img = Image.new("RGBA", (W, 180), (0, 0, 0, 0)); d = ImageDraw.Draw(img); f = font(56, 0)
    parts = [clean(w["w"]) for w in group]; widths = [d.textlength(p, font=f) for p in parts]; gap = 18
    x = (W - (sum(widths) + gap * (len(parts) - 1))) / 2; y = 60
    for i, (p, tw) in enumerate(zip(parts, widths)):
        a = 255 if i <= active else 150
        d.text((x + 2, y + 3), p, font=f, fill=(0, 0, 0, 160)); d.text((x, y), p, font=f, fill=(255, 250, 240, a)); x += tw + gap
    return img

def fade(t, a, b, fi, fo):
    if t < a or t > b: return 0.0
    return max(0.0, min(1.0, (t - a) / fi if fi else 1.0, (b - t) / fo if fo else 1.0))
def with_alpha(img, a):
    if a >= 0.999: return img
    r, g, b, al = img.split(); return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * a))))

def render_overlay(out, total, V1, S, words, title, world_png):
    rng = random.Random(7)
    sprites = {r: glow_sprite(r) for r in (5, 8, 12, 18)}
    parts = [{"x": rng.uniform(0, W), "y": rng.uniform(0, H), "r": rng.choice((5, 5, 8, 8, 12, 18)), "v": rng.uniform(14, 40),
              "ph": rng.uniform(0, 6.28), "amp": rng.uniform(10, 40), "a": rng.uniform(0.18, 0.55)} for _ in range(70)]
    sun = sun_glow()
    kicker = text_img([f"TRANSMISSION   ·   {title.upper()}"], 28, 0, 5, fill=(255, 245, 225, 255))
    groups = phrases(words)
    caps = []
    for g in groups:
        for wi, w in enumerate(g):
            e = g[wi + 1]["s"] if wi + 1 < len(g) else g[wi]["e"] + 0.35
            caps.append((w["s"], max(e, w["s"] + 0.05), g, wi))
    cache = {}
    world = Image.open(world_png).convert("RGB")
    end1 = text_img(["You are loved."], 92, 2, fill=(255, 252, 245, 255), shadow=120)
    end2 = text_img(["comment  “I choose love”"], 36, 2, 2, fill=(255, 245, 225, 245), shadow=220)
    end3 = text_img(["@claudiainfinityai   ·   The Collective"], 28, 0, 4, fill=(255, 245, 225, 225), shadow=220)
    end_start = V1 + HOLD; nfr = int(round(total * FPS))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                             "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-qscale:v", "9", out], stdin=subprocess.PIPE)
    ci = 0
    for i in range(nfr):
        t = i / FPS; fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        # end card: dissolve to the world still with a slow push, warm
        if t >= end_start - 0.8:
            a = fade(t, end_start - 0.8, total + 5, 1.0, 0); z = 1.04 + 0.05 * max(0, (t - end_start) / (ENDCARD + 1))
            cw, ch = world.width / z, world.height / z; x0, y0 = (world.width - cw) / 2, (world.height - ch) / 2
            fr.alpha_composite(with_alpha(world.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR).convert("RGBA"), a))
            fr.alpha_composite(with_alpha(Image.new("RGBA", (W, H), (40, 20, 30, 70)), a))   # gentle darkening for text
        # breathing sun glow + particles (on top of everything except text), not during end card fade
        if t < end_start + 0.4:
            fr.alpha_composite(with_alpha(sun, 0.35 + 0.35 * (0.5 + 0.5 * math.sin(t / 5.5 * 6.283))))
            for p in parts:
                y = (p["y"] - p["v"] * t) % (H + 80) - 40; x = (p["x"] + p["amp"] * math.sin(t * 0.6 + p["ph"])) % (W + 80) - 40
                tw = 0.5 + 0.5 * math.sin(t * 1.3 + p["ph"] * 2); a = p["a"] * (0.55 + 0.45 * tw)
                sp = sprites[p["r"]]; fr.alpha_composite(with_alpha(sp, a), (int(x - sp.width / 2), int(y - sp.height / 2)))
        # kicker
        a = fade(t, 2.2, 9.5, 0.8, 0.8)
        if a: fr.alpha_composite(with_alpha(kicker, a), (0, 150))
        # captions
        while ci < len(caps) and caps[ci][1] < t: ci += 1
        if ci < len(caps) and caps[ci][0] <= t <= caps[ci][1]:
            s, e, g, wi = caps[ci]; key = (id(g), wi)
            if key not in cache: cache[key] = caption_img(g, wi)
            a = min(1.0, (t - g[0]["s"]) / 0.15 + 0.2) if wi == 0 else 1.0
            fr.alpha_composite(with_alpha(cache[key], a), (0, 1390))
        # end texts
        for img, a0, y, fi in [(end1, end_start + 0.3, 1250, 0.9), (end2, end_start + 1.1, 1415, 0.8), (end3, end_start + 1.5, 1495, 0.8)]:
            a = fade(t, a0, total + 5, fi, 0)
            if a: fr.alpha_composite(with_alpha(img, a), (0, y))
        proc.stdin.write(fr.tobytes())
    proc.stdin.close(); proc.wait()

def main():
    d, S, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    meta = json.load(open(f"{d}/voice.align.json")); words = words_from_alignment(meta["alignment"]); title = meta["title"]
    V1 = dur(f"{d}/voice.mp3"); total = V1 + HOLD + ENDCARD
    seg1, seg2 = f"{d}/seg1.mp4", f"{d}/seg2.mp4"
    d1 = dur(seg1); d2 = dur(seg2)
    b0, b1 = S - BROLL_BEFORE, S + BROLL_AFTER
    tmp = tempfile.mkdtemp(prefix="hero_"); ov = f"{tmp}/overlay.mov"
    print("overlay track...", flush=True); render_overlay(ov, total, V1, S, words, title, f"{d}/world.png")
    print("compositing...", flush=True)
    up = f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.5:5:5:0.0"
    push = (f"scale=w='trunc(iw*(1+0.07*t/{total:.3f})/2)*2':h='trunc(ih*(1+0.07*t/{total:.3f})/2)*2':eval=frame:flags=bicubic,"
            f"crop={W}:{H}:'(iw-{W})/2':'(ih-{H})/2'")
    grade = "eq=contrast=1.06:saturation=1.08:brightness=0.01,colorbalance=rs=0.02:gs=0.0:bs=0.06:rh=0.06:gh=0.02:bh=-0.04,vignette=PI/4.4,noise=alls=4:allf=t"
    f = [
        # seg1 from 0, seg2 aligned to S; seg1 padded at the end so the base never runs dry
        f"[0:v]{up},tpad=stop_duration={total}:stop_mode=clone,trim=duration={total:.3f},setpts=PTS-STARTPTS[s1]",
        f"[1:v]{up},tpad=stop_duration={total}:stop_mode=clone,trim=duration={total - S:.3f},setpts=PTS-STARTPTS+{S:.3f}/TB[s2]",
        f"[s1][s2]overlay=0:0:eof_action=pass:enable='gte(t,{S:.3f})'[base0]",
        # b-roll over the seam, with soft fades
        f"[2:v]{up},trim=duration={BROLL_BEFORE + BROLL_AFTER:.3f},setpts=PTS-STARTPTS+{b0:.3f}/TB,format=rgba,fade=t=in:st={b0:.3f}:d=0.45:alpha=1,fade=t=out:st={b1 - 0.55:.3f}:d=0.55:alpha=1[br]",
        f"[base0][br]overlay=0:0:eof_action=pass[base1]",
        f"[base1]{push},{grade}[base2]",
        f"[base2][3:v]overlay=0:0:eof_action=pass,format=yuv420p[vout]",
        # audio
        f"[4:a]highpass=f=70,acompressor=threshold=-18dB:ratio=2.5:attack=15:release=200:makeup=2,aecho=0.85:0.5:38:0.10,apad=pad_dur={HOLD + ENDCARD + 1},asplit[voice][side]",
        f"[5:a]atrim=duration={total:.3f},asetpts=PTS-STARTPTS,volume=-15dB,afade=t=in:d=2.0,afade=t=out:st={total - 3.0:.3f}:d=3.0[m0]",
        f"[m0][side]sidechaincompress=threshold=0.02:ratio=5:attack=60:release=900:makeup=1[m1]",
        f"[6:a]volume=-11dB,adelay=150|150[sbreath]",
        f"[7:a]volume=-13dB,adelay={int((b0 - 0.35) * 1000)}|{int((b0 - 0.35) * 1000)}[swoosh1]",
        f"[8:a]volume=-14dB,adelay={int((V1 + HOLD - 1.0) * 1000)}|{int((V1 + HOLD - 1.0) * 1000)}[swoosh2]",
        f"[9:a]volume=-9dB,afade=t=out:st=5:d=3[sdrone]",
        f"[10:a]volume=-15dB,adelay={int((V1 + HOLD + 0.3) * 1000)}|{int((V1 + HOLD + 0.3) * 1000)}[sshim]",
        f"[voice][m1][sbreath][swoosh1][swoosh2][sdrone][sshim]amix=inputs=7:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.95[aout]",
    ]
    run(["ffmpeg", "-v", "error", "-y", "-i", seg1, "-i", seg2, "-i", f"{d}/broll.mp4", "-i", ov, "-i", f"{d}/voice.mp3", "-i", f"{d}/music.mp3",
         "-i", f"{d}/sfx-breath.mp3", "-i", f"{d}/sfx-whoosh.mp3", "-i", f"{d}/sfx-whoosh.mp3", "-i", f"{d}/sfx-drone.mp3", "-i", f"{d}/sfx-shimmer.mp3",
         "-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-crf", "17", "-preset", "veryfast", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    shutil.rmtree(tmp); print(out, f"total={total:.2f}s split={S} broll=[{b0:.2f},{b1:.2f}]")

if __name__ == "__main__": main()
