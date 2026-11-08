"""SurgerySaathi 'OT Kisse' video engine.
Usage: python3 ss_make.py spec.json OUTDIR [--preview]
Builds OUTDIR/<slug>.mp4 (1080x1920 Short) + OUTDIR/<slug>_cover.jpg + OUTDIR/<slug>_check.jpg (contact sheet).
See README.md for the spec format.
"""
import json, math, os, subprocess, sys, urllib.request
import numpy as np, soundfile as sf
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
A = lambda f: os.path.join(HERE, "assets", f)
FPS = 30; W, H = 1080, 1920
P = lambda s: ImageFont.truetype(A("Poppins-Bold.ttf"), s)
GREEN = (18, 83, 42); LIGHT = (232, 245, 236); RED = (200, 30, 40); DARK = (25, 45, 30); OK = (30, 140, 60); BLUE = (40, 110, 200)
KDIR = os.environ.get("KOKORO_DIR", "/home/claude/kokoro")
KURL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"

# ---------------- spec checks ----------------
LIM = dict(bubble=24, bullet=36, tile_k=11, tile_v=9, row=27, intro=16, intro_sub=38, title=95)
ICONS = ["ring", "nail", "teeth", "glasses", "file", "pill", "person", "drop", "cube", "heart", "leaf", "clock", "glass", "plate", "bandage", "phone", "cigarette", "lungs", "thermo", "syringe"]
def check(s):
    e = []
    for k in ["slug", "num", "intro", "q_vo", "a_vo", "f_vo", "q_bubble", "a_bubble", "bullets", "bullet_starts", "cap", "tiles", "stage", "youtube"]:
        if k not in s: e.append(f"missing {k}")
    if e: return e
    if s.get("patient", "uncle") not in ("uncle", "dadi", "didi"): e.append("patient must be uncle, dadi or didi")
    if len(s["intro"]) != 3: e.append("intro needs 3 strings")
    for x in s["intro"][:2]:
        if len(x) > LIM["intro"]: e.append(f"intro line too long ({len(x)}>{LIM['intro']}): {x}")
    if len(s["intro"][2]) > LIM["intro_sub"]: e.append("intro subtitle too long")
    for b in ("q_bubble", "a_bubble"):
        if not 2 <= len(s[b]) <= 3: e.append(f"{b} needs 2-3 lines")
        for x in s[b]:
            if len(x) > LIM["bubble"]: e.append(f"{b} line too long ({len(x)}>{LIM['bubble']}): {x}")
    if len(s["bullets"]) != 4: e.append("bullets needs exactly 4")
    for x in s["bullets"]:
        if len(x) > LIM["bullet"]: e.append(f"bullet too long ({len(x)}>{LIM['bullet']}): {x}")
    bs = s["bullet_starts"]
    if len(bs) != 4 or bs != sorted(bs) or bs[0] < 1 or bs[-1] >= len(s["f_vo"]): e.append("bullet_starts: 4 increasing phrase indexes into f_vo, first >=1 (index 0 is 'सच क्या है?')")
    for k in ("q", "a", "f", "f2"):
        if k not in s["cap"]: e.append(f"cap.{k} missing")
        elif len(s["cap"][k]) > 120: e.append(f"cap.{k} too long (>120)")
    if len(s["tiles"]) != 4: e.append("tiles needs exactly 4")
    for t in s["tiles"]:
        if len(t) != 3: e.append(f"tile needs [label, before, after]: {t}"); continue
        if len(t[0]) > LIM["tile_k"]: e.append(f"tile label too long: {t[0]}")
        for v in t[1:]:
            if len(v) > LIM["tile_v"]: e.append(f"tile value too long ({len(v)}>{LIM['tile_v']}): {v}")
    st = s["stage"]
    if st.get("type") == "checklist":
        if len(st.get("rows", [])) != 4: e.append("checklist needs 4 rows")
        for r in st.get("rows", []):
            if r.get("icon") not in ICONS: e.append(f"unknown icon {r.get('icon')} (use {ICONS})")
            if len(r.get("label", "")) > LIM["row"]: e.append(f"row label too long: {r.get('label')}")
        if len(st.get("title", "")) > 26: e.append("stage title too long (>26)")
    elif st.get("type") == "meter":
        for k in ("title", "min", "max", "from", "to", "left", "right"):
            if k not in st: e.append(f"meter missing {k}")
    else:
        e.append("stage.type must be checklist or meter")
    for vo in ("q_vo", "a_vo", "f_vo"):
        for p in s[vo]:
            if any("a" <= ch.lower() <= "z" for ch in p[0]): e.append(f"{vo} must be Devanagari only (no Latin letters): {p[0]}")
            if any(ch.isdigit() for ch in p[0]): e.append(f"{vo}: write numbers in words: {p[0]}")
    y = s["youtube"]
    if len(y.get("title", "")) > LIM["title"]: e.append("youtube.title too long (>95 chars)")
    for k in ("title", "description", "tags"):
        if k not in y: e.append(f"youtube.{k} missing")
    return e

# ---------------- TTS ----------------
def kokoro():
    os.makedirs(KDIR, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(KDIR, f)
        if not os.path.exists(p) or os.path.getsize(p) < 1e6:
            urllib.request.urlretrieve(KURL + f, p)
    from kokoro_onnx import Kokoro
    return Kokoro(os.path.join(KDIR, "kokoro-v1.0.onnx"), os.path.join(KDIR, "voices-v1.0.bin"))

def say(K, parts, voice, speed):
    out = []; starts = []; t = 0.0; sr = 24000
    for txt, pause in parts:
        s, sr = K.create(txt, voice=voice, speed=speed, lang="hi")
        nz = np.where(np.abs(s) > 0.01)[0]
        s = s[max(0, nz[0] - 240): nz[-1] + 480] if len(nz) else s
        starts.append(t); out += [s, np.zeros(int(pause * sr), dtype=np.float32)]; t += len(s) / sr + pause
    return np.concatenate(out).astype(np.float32), sr, starts


# Microsoft Edge neural voices (preferred), Kokoro fallback
EDGE = {"dr": ("hi-IN-SwaraNeural", "+6%", "+0Hz"), "uncle": ("hi-IN-MadhurNeural", "+0%", "-4Hz"),
        "dadi": ("hi-IN-SwaraNeural", "-10%", "-40Hz"), "didi": ("hi-IN-SwaraNeural", "+2%", "+22Hz")}
KOK = {"dr": ("hf_alpha", 1.02), "uncle": ("hm_omega", 1.0), "dadi": ("hf_beta", 0.92), "didi": ("hf_beta", 1.0)}
def edge_clip(text, voice, rate, pitch, sr=24000):
    import asyncio, ssl, tempfile
    import edge_tts, edge_tts.communicate as C
    ca = os.path.expanduser("~/.ccr/ca-bundle.crt")
    if os.path.exists(ca): C._SSL_CTX = ssl.create_default_context(cafile=ca)
    tmp = tempfile.mktemp(suffix=".mp3")
    for a in range(3):
        try:
            asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(tmp))
            if os.path.getsize(tmp) > 500: break
        except Exception as e:
            err = e
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", tmp, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"], capture_output=True).stdout
    os.remove(tmp)
    s = np.frombuffer(raw, dtype=np.float32)
    if len(s) < 1000: raise RuntimeError("edge tts failed")
    return s
_K = None
def say_role(role, parts):
    global _K
    use_edge = os.environ.get("SS_TTS", "edge") == "edge"
    out = []; starts = []; t = 0.0; sr = 24000
    for txt, pause in parts:
        s = None
        if use_edge:
            try: s = edge_clip(txt, *EDGE[role])
            except Exception: use_edge = False
        if s is None:
            if _K is None: _K = kokoro()
            v, sp = KOK[role]; s, sr = _K.create(txt, voice=v, speed=sp, lang="hi")
        nz = np.where(np.abs(s) > 0.01)[0]
        s = s[max(0, nz[0] - 240): nz[-1] + 480] if len(nz) else s
        starts.append(t); out += [s.astype(np.float32), np.zeros(int(pause * sr), dtype=np.float32)]; t += len(s) / sr + pause
    return np.concatenate(out).astype(np.float32), sr, starts

END_VO = [["डर नहीं,", 0.1], ["तैयारी!", 0.25], ["फ़ॉलो कीजिए, सर्जरी साथी।", 0.1]]

# ---------------- drawing helpers ----------------
src = Image.open(A("hi2.png")).convert("RGB")
def circ(box, size, ring=GREEN):
    f = src.crop(box).resize((size, size), Image.LANCZOS)
    m = Image.new("L", (size, size), 0); ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGBA", (size + 16, size + 16), (0, 0, 0, 0)); d = ImageDraw.Draw(out); d.ellipse([0, 0, size + 15, size + 15], fill=ring)
    out.paste(f, (8, 8), m); return out
def cast(name, h):
    im = Image.open(A(f"cast/{name}.png")).convert("RGBA"); k = h / im.height
    return im.resize((int(im.width * k), h), Image.LANCZOS)
SITE_HANDLE = os.environ.get("SS_HANDLE", "@surgerysathi")
PATIENTS = {"uncle": ("Uncle", "hm_omega", 1.0), "dadi": ("Dadi", "hf_beta", 0.92), "didi": ("Didi", "hf_beta", 1.0)}

def wrap(d, text, font, maxw):
    words = text.split(); L = []; cur = ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw: cur = t
        else: L.append(cur); cur = w
    L.append(cur); return L

def bubble(d, box, lines, font, color, tail):
    d.rounded_rectangle(box, radius=36, fill="white", outline=GREEN, width=6)
    d.polygon(tail, fill="white", outline=GREEN, width=6); d.line([tail[0], tail[2]], fill="white", width=8)
    cy = (box[1] + box[3]) / 2; lh = font.size * 1.3
    for i, l in enumerate(lines): d.text(((box[0] + box[2]) / 2, cy + (i - (len(lines) - 1) / 2) * lh), l, font=font, fill=color, anchor="mm")

def icon(d, k, cx, cy):
    if k == "ring":
        d.ellipse([cx-34, cy-20, cx+34, cy+44], outline=(220, 170, 40), width=12); d.polygon([(cx-16, cy-22), (cx+16, cy-22), (cx, cy-46)], fill=(120, 200, 255))
    elif k == "nail":
        d.rounded_rectangle([cx-26, cy-46, cx+26, cy+46], radius=26, fill=(240, 190, 150)); d.rounded_rectangle([cx-18, cy-40, cx+18, cy-2], radius=16, fill=(220, 30, 70))
    elif k == "teeth":
        d.rounded_rectangle([cx-48, cy-30, cx+48, cy+30], radius=24, fill=(240, 120, 140))
        for n in range(5): d.rounded_rectangle([cx-42+n*17, cy-24, cx-28+n*17, cy+6], radius=5, fill="white")
    elif k == "glasses":
        d.ellipse([cx-50, cy-20, cx-8, cy+22], outline=DARK, width=7); d.ellipse([cx+8, cy-20, cx+50, cy+22], outline=DARK, width=7); d.line([cx-8, cy, cx+8, cy], fill=DARK, width=6)
    elif k == "file":
        d.rectangle([cx-34, cy-44, cx+34, cy+44], fill="white", outline=DARK, width=5)
        for n in range(4): d.line([cx-22, cy-26+n*16, cx+22, cy-26+n*16], fill=(120, 130, 140), width=4)
    elif k == "pill":
        d.rounded_rectangle([cx-46, cy-18, cx+46, cy+18], radius=18, fill="white", outline=DARK, width=4); d.rounded_rectangle([cx-46, cy-18, cx, cy+18], radius=18, fill=(220, 60, 60), outline=DARK, width=4)
    elif k == "person":
        d.ellipse([cx-18, cy-46, cx+18, cy-10], fill=(240, 180, 130), outline=DARK, width=4); d.rounded_rectangle([cx-34, cy-4, cx+34, cy+46], radius=20, fill=(80, 140, 220), outline=DARK, width=4)
    elif k == "drop":
        d.polygon([(cx, cy-46), (cx-30, cy+4), (cx+30, cy+4)], fill=(200, 30, 40)); d.ellipse([cx-30, cy-20, cx+30, cy+40], fill=(200, 30, 40))
    elif k == "cube":
        d.rectangle([cx-30, cy-30, cx+30, cy+30], fill="white", outline=DARK, width=4); d.line([cx-30, cy-30, cx-14, cy-44], fill=DARK, width=4); d.line([cx+30, cy-30, cx+46, cy-44], fill=DARK, width=4); d.line([cx-14, cy-44, cx+46, cy-44], fill=DARK, width=4)
    elif k == "heart":
        d.ellipse([cx-38, cy-32, cx+2, cy+8], fill=(220, 40, 60)); d.ellipse([cx-2, cy-32, cx+38, cy+8], fill=(220, 40, 60)); d.polygon([(cx-36, cy-4), (cx+36, cy-4), (cx, cy+40)], fill=(220, 40, 60))
    elif k == "leaf":
        d.ellipse([cx-24, cy-44, cx+24, cy+30], fill=(70, 160, 80)); d.line([cx, cy-36, cx, cy+44], fill=(40, 90, 50), width=5)
    elif k == "clock":
        d.ellipse([cx-42, cy-42, cx+42, cy+42], fill="white", outline=DARK, width=6); d.line([cx, cy, cx, cy-28], fill=DARK, width=6); d.line([cx, cy, cx+20, cy+8], fill=RED, width=6)
    elif k == "glass":
        d.polygon([(cx-30, cy-44), (cx+30, cy-44), (cx+22, cy+44), (cx-22, cy+44)], fill=(220, 240, 255), outline=DARK, width=4); d.polygon([(cx-26, cy-10), (cx+26, cy-10), (cx+22, cy+40), (cx-22, cy+40)], fill=(120, 190, 240))
    elif k == "plate":
        d.ellipse([cx-48, cy-34, cx+48, cy+34], fill="white", outline=DARK, width=5); d.ellipse([cx-26, cy-18, cx+26, cy+18], fill=(250, 200, 90))
    elif k == "bandage":
        d.rounded_rectangle([cx-50, cy-18, cx+50, cy+18], radius=14, fill=(240, 200, 160), outline=DARK, width=4); d.rectangle([cx-16, cy-18, cx+16, cy+18], fill=(255, 240, 225), outline=DARK, width=3)
    elif k == "phone":
        d.rounded_rectangle([cx-26, cy-46, cx+26, cy+46], radius=10, fill=DARK); d.rectangle([cx-20, cy-36, cx+20, cy+30], fill=(150, 210, 255))
    elif k == "cigarette":
        d.rectangle([cx-50, cy-10, cx+30, cy+10], fill="white", outline=DARK, width=3); d.rectangle([cx+30, cy-10, cx+50, cy+10], fill=(230, 150, 60), outline=DARK, width=3); d.line([cx-60, cy+30, cx+60, cy-30], fill=RED, width=8)
    elif k == "lungs":
        d.ellipse([cx-46, cy-34, cx-6, cy+44], fill=(240, 140, 150), outline=DARK, width=4); d.ellipse([cx+6, cy-34, cx+46, cy+44], fill=(240, 140, 150), outline=DARK, width=4); d.line([cx, cy-46, cx, cy-10], fill=DARK, width=6)
    elif k == "thermo":
        d.rounded_rectangle([cx-10, cy-46, cx+10, cy+20], radius=10, fill="white", outline=DARK, width=4); d.ellipse([cx-20, cy+12, cx+20, cy+48], fill=RED, outline=DARK, width=4); d.rectangle([cx-4, cy-10, cx+4, cy+20], fill=RED)
    elif k == "syringe":
        d.rectangle([cx-40, cy-14, cx+20, cy+14], fill=(220, 240, 255), outline=DARK, width=4); d.line([cx+20, cy, cx+52, cy], fill=DARK, width=4); d.line([cx-56, cy, cx-40, cy], fill=DARK, width=8); d.line([cx-56, cy-16, cx-56, cy+16], fill=DARK, width=6)

def mix(c1, c2, p): return tuple(int(c1[k] + (c2[k] - c1[k]) * p) for k in range(3))

# ---------------- build ----------------
def build(spec, outdir, preview=False):
    os.makedirs(outdir, exist_ok=True)
    slug = spec["slug"]; num = spec["num"]
    pt = spec.get("patient", "uncle")
    qa, sr, _ = say_role(pt, spec["q_vo"])
    aa, _, _ = say_role("dr", spec["a_vo"])
    fa, _, fst = say_role("dr", spec["f_vo"])
    ea, _, _ = say_role("dr", END_VO)
    aud = dict(q=qa, a=aa, f=fa, e=ea)
    segs = [("intro", 1.8), ("q", len(qa)/sr + 0.6), ("a", len(aa)/sr + 0.7), ("f", len(fa)/sr + 0.8), ("e", len(ea)/sr + 0.9)]
    total = sum(d for _, d in segs)
    FST = segs[0][1] + segs[1][1] + segs[2][1]
    btimes = [fst[i] + 0.25 for i in spec["bullet_starts"]]
    sw_i = spec.get("switch_bullet", 2)  # tiles/meter switch at this bullet (1-based)
    SW = FST + btimes[sw_i - 1]
    cap = dict(spec["cap"]); cap["e"] = f"Darr nahi, taiyaari! Follow {SITE_HANDLE}"
    capsw = btimes[2]
    # audio
    N = int(total * sr); track = np.zeros(N + sr, dtype=np.float32); t0 = 0
    for n, d in segs:
        if n in aud: i = int((t0 + 0.25) * sr); track[i:i + len(aud[n])] += aud[n]
        t0 += d
    for b in (0.15, 0.55):
        tt = np.arange(int(0.12 * sr)) / sr; i = int(b * sr); track[i:i + len(tt)] += 0.2 * np.sin(2*np.pi*880*tt) * np.hanning(len(tt))
    ding = np.arange(int(0.25 * sr)) / sr
    for bt in btimes:
        i = int((FST + bt) * sr); track[i:i + len(ding)] += 0.06 * np.sin(2*np.pi*1320*ding) * np.exp(-ding*12)
    rng = np.random.default_rng(1); t0 = 0
    for n, d in segs:
        if t0 > 0:
            L = int(0.32 * sr); x = np.arange(L) / L; nse = rng.standard_normal(L)
            nse = np.convolve(nse, np.ones(6) / 6, mode="same") * np.sin(np.pi * x) ** 2
            i = int(max(0, t0 - 0.16) * sr); track[i:i + L] += 0.10 * nse
        if n in ("q", "a"):
            L = int(0.09 * sr); x = np.arange(L) / sr; i = int((t0 + 0.18) * sr)
            track[i:i + L] += 0.12 * np.sin(2 * np.pi * (500 + 3000 * x) * x) * np.exp(-x * 40)
        t0 += d
    track = track[:N]; tt = np.arange(N) / sr
    bed = np.zeros(N); chords = [(261.6, 329.6, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    for i, ch in enumerate(chords * 40):
        a = int(i * 2 * sr); b = min(N, a + 2 * sr)
        if a >= N: break
        s = tt[a:b] - tt[a]; env = np.minimum(1, s / 0.3) * np.exp(-s * 0.6); bed[a:b] += sum(np.sin(2*np.pi*f*s) * 0.33 for f in ch) * env
    track = track + 0.035 * bed; track /= max(1, np.abs(track).max() / 0.95)
    wav = os.path.join(outdir, f"{slug}.wav"); sf.write(wav, track, sr)

    st = spec["stage"]
    def envelope(a):
        hop = sr // FPS; n = len(a) // hop + 1
        e = np.array([np.sqrt(np.mean(a[i*hop:(i+1)*hop] ** 2)) if i*hop < len(a) else 0 for i in range(n)])
        e = e / (e.max() + 1e-6); return np.convolve(e, np.ones(3) / 3, mode="same")
    ENV = {k: envelope(v) for k, v in aud.items()}
    def amp(name, tseg):
        e = ENV.get(name); i = int((tseg - 0.25) * FPS)
        return float(e[i]) if e is not None and 0 <= i < len(e) else 0.0
    _cache = {}
    def scaled(img, k):
        key = (id(img), round(k, 2))
        if key not in _cache:
            if len(_cache) > 400: _cache.clear()
            _cache[key] = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.BILINEAR)
        return _cache[key]
    def ease_out_back(p):
        p = max(0.0, min(1.0, p)); c1 = 1.70158; c3 = c1 + 1; return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
    def ease_out(p): p = max(0.0, min(1.0, p)); return 1 - (1 - p) ** 3
    def pop_layer(im, draw_fn, box, k):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); draw_fn(ImageDraw.Draw(lay))
        if k >= 0.999: im.paste(lay, (0, 0), lay); return
        x0, y0, x1, y1 = box; part = lay.crop(box); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if k <= 0.02: return
        sp = scaled(part, k) if False else part.resize((max(1, int(part.width * k)), max(1, int(part.height * k))), Image.BILINEAR)
        im.paste(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)), sp)
    def char(im, img, x, bottom, k=1.0, talk=0.0, t=0.0):
        kk = k * (1 + 0.025 * talk); c = scaled(img, kk)
        dy = -18 * talk + 4 * math.sin(t * 2.2)
        im.paste(c, (int(x + (img.width - c.width) / 2), int(bottom - c.height + dy)), c)
    p_worried = cast(f"{pt}_worried", 600); p_thank = cast(f"{pt}_thankful", 380)
    d_happy = cast("dr_happy", 600); d_explain = cast("dr_explain", 250); d_port = cast("dr_portrait", 560)
    def tiles(d, t):
        on = t >= SW
        for i, (k, b, a) in enumerate(spec["tiles"]):
            x = 30 + i * 258; v = a if on else b
            col = (OK if on else RED) if a != b else DARK
            glow = on and a != b and t - SW < 0.8
            d.rounded_rectangle([x, 240, x + 246, 420], radius=26, fill=(255, 250, 220) if glow else "white", outline=(255, 190, 0) if glow else GREEN, width=9 if glow else 5)
            d.text((x + 123, 285), k, font=P(28), fill=(70, 110, 80), anchor="mm")
            d.text((x + 123, 360), v, font=P(46 if len(v) <= 6 else 38 if len(v) <= 8 else 32), fill=col, anchor="mm")
    def stage(im, d, t):
        tiles(d, t)
        d.rounded_rectangle([30, 445, 1050, 965], radius=26, fill="white", outline=GREEN, width=6)
        if st["type"] == "checklist":
            d.rectangle([36, 451, 1044, 520], fill=GREEN); d.text((W/2, 486), st["title"], font=P(40), fill="white", anchor="mm")
            for i, r in enumerate(st["rows"]):
                y = 585 + i * 105; tk = FST + btimes[i]; done = t >= tk
                if i: d.line([70, y - 52, 1010, y - 52], fill=(215, 230, 220), width=3)
                icon(d, r["icon"], 120, y)
                lab = r["label"]; d.text((200, y), lab, font=P(38), fill=(150, 160, 150) if done else DARK, anchor="lm")
                if done: d.line([200, y + 2, 200 + d.textlength(lab, font=P(38)), y + 2], fill=(150, 160, 150), width=4)
                bx = 930; d.rounded_rectangle([bx, y - 34, bx + 68, y + 34], radius=14, outline=GREEN, width=6, fill=(225, 245, 230) if done else "white")
                if done:
                    p = min(1, (t - tk) / 0.3); a1 = (bx + 12, y); a2 = (bx + 28, y + 18); a3 = (bx + 58, y - 22)
                    d.line([a1, (a1[0] + (a2[0]-a1[0]) * min(1, p*2), a1[1] + (a2[1]-a1[1]) * min(1, p*2))], fill=OK, width=10)
                    if p > 0.5: q = (p - 0.5) * 2; d.line([a2, (a2[0] + (a3[0]-a2[0]) * q, a2[1] + (a3[1]-a2[1]) * q)], fill=OK, width=10)
        else:
            mn, mx = st["min"], st["max"]; f0, f1 = st["from"], st["to"]
            if t < SW: v = mn + (f0 - mn) * min(1, t / 4)
            else: v = f0 + (f1 - f0) * min(1, (t - SW) / 3)
            good_low = st.get("good_low", True)
            def pc(x):
                p = (x - mn) / (mx - mn); p = p if good_low else 1 - p
                return mix((60, 170, 80), (250, 200, 40), p * 2) if p < 0.5 else mix((250, 200, 40), (220, 40, 40), (p - 0.5) * 2)
            d.text((W/2, 495), st["title"], font=P(36), fill=GREEN, anchor="mm")
            X0, X1, Y = 100, 980, 760
            for k in range(X1 - X0): d.line([X0 + k, Y - 30, X0 + k, Y + 30], fill=pc(mn + (mx - mn) * k / (X1 - X0)))
            d.rounded_rectangle([X0, Y - 30, X1, Y + 30], radius=8, outline=DARK, width=3)
            d.text((X0, Y - 70), st["left"], font=P(30), fill=DARK, anchor="lm"); d.text((X1, Y - 70), st["right"], font=P(30), fill=DARK, anchor="rm")
            d.text((X0, Y + 62), str(mn), font=P(30), fill=DARK, anchor="mm"); d.text((X1, Y + 62), str(mx), font=P(30), fill=DARK, anchor="mm")
            x = X0 + (X1 - X0) * (v - mn) / (mx - mn)
            d.polygon([(x - 24, Y - 50), (x + 24, Y - 50), (x, Y - 24)], fill=DARK)
            lab = (st.get("fmt", "{:.0f}")).format(v) + st.get("unit", "")
            wbox = max(70, d.textlength(lab, font=P(44)) / 2 + 26)
            d.rounded_rectangle([x - wbox, Y + 90, x + wbox, Y + 165], radius=18, fill=pc(v), outline=DARK, width=3)
            d.text((x, Y + 128), lab, font=P(44), fill="white", anchor="mm")
    def frame(name, t, tseg, dseg=5.0):
        im = Image.new("RGB", (W, H), LIGHT); d = ImageDraw.Draw(im)
        c = None
        if name == "e":
            d.ellipse([W/2 - 400, 250, W/2 + 260, 910], fill=(205, 232, 214))
            for k in range(12):
                ang = k * math.pi / 6 + t * 0.4
                d.line([W/2 - 70 + 300 * math.cos(ang), 580 + 300 * math.sin(ang), W/2 - 70 + 360 * math.cos(ang), 580 + 360 * math.sin(ang)], fill=(180, 220, 195), width=10)
            pc = d_port.crop((0, 0, d_port.width, 560)); kin = ease_out_back(tseg / 0.45)
            char(im, pc, W/2 - pc.width/2 - 70, 910, k=max(0.05, kin), talk=amp("e", tseg), t=t)
            pk = ease_out(max(0, tseg - 0.3) / 0.4)
            im.paste(p_thank, (int(W - p_thank.width + 20 + (1 - pk) * 400), 920 - p_thank.height), p_thank)
            def wm(dd):
                w1 = dd.textlength("Surgery", font=P(120)); w2 = dd.textlength("Saathi", font=P(120)); x0 = W/2 - (w1 + w2)/2
                dd.text((x0, 1010), "Surgery", font=P(120), fill=GREEN, anchor="lm"); dd.text((x0 + w1, 1010), "Saathi", font=P(120), fill=RED, anchor="lm")
                dd.text((W/2, 1130), "Darr nahi, taiyaari!", font=P(60), fill=DARK, anchor="mm")
            pop_layer(im, wm, (0, 930, W, 1180), ease_out_back((tseg - 0.2) / 0.4))
            d = ImageDraw.Draw(im); pulse = 1 + 0.05 * math.sin(t * 7)
            bw, bh = 300 * pulse, 45 * pulse
            if tseg > 0.6:
                d.rounded_rectangle([W/2 - bw, 1245 - bh, W/2 + bw, 1245 + bh], radius=45, fill=RED); d.text((W/2, 1245), "SUBSCRIBE", font=P(48), fill="white", anchor="mm")
            d.text((W/2, 1370), SITE_HANDLE, font=P(46), fill=GREEN, anchor="mm")
            d.text((W/2, 1440), "AI character · sirf jaankari ke liye", font=P(32), fill=(60, 90, 70), anchor="mm"); c = cap["e"]
        else:
            stage(im, d, t)
            if name == "intro":
                k1 = ease_out_back(tseg / 0.35); k2 = ease_out_back((tseg - 0.2) / 0.35)
                pop_layer(im, lambda dd: dd.text((W/2, 1200), spec["intro"][0], font=P(96), fill=GREEN, anchor="mm"), (0, 1130, W, 1270), k1)
                pop_layer(im, lambda dd: dd.text((W/2, 1330), spec["intro"][1], font=P(96), fill=RED, anchor="mm"), (0, 1260, W, 1400), k2)
                d = ImageDraw.Draw(im); d.text((W/2, 1450), spec["intro"][2], font=P(40), fill=DARK, anchor="mm")
                pk = ease_out(max(0, tseg - 0.8) / 0.6); peek = cast(f"{pt}_worried", 300)
                im.paste(peek, (W - peek.width - 10, int(1680 - peek.height * 0.55 * pk)), peek)
            if name == "q":
                sl = ease_out_back(tseg / 0.4)
                char(im, p_worried, W - p_worried.width + 40 + (1 - sl) * 500, 1680, talk=amp("q", tseg), t=t)
                pop_layer(im, lambda dd: bubble(dd, [30, 1000, 650, 1300], spec["q_bubble"], P(44), DARK, [(648, 1150), (720, 1190), (648, 1220)]), (20, 990, 730, 1310), ease_out_back((tseg - 0.15) / 0.3))
                c = cap["q"]
            if name == "a":
                sl = ease_out_back(tseg / 0.4)
                char(im, d_happy, -40 - (1 - sl) * 500, 1680, talk=amp("a", tseg), t=t)
                pop_layer(im, lambda dd: bubble(dd, [430, 1000, 1050, 1300], spec["a_bubble"], P(44), RED, [(432, 1150), (360, 1190), (432, 1220)]), (350, 990, 1060, 1310), ease_out_back((tseg - 0.15) / 0.3))
                c = cap["a"]
            if name == "f":
                up = (1 - ease_out(tseg / 0.35)) * 700
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
                dl.rounded_rectangle([30, 990, 1050, 1650], radius=34, fill=GREEN)
                dl.text((60, 1040), "SACH KYA HAI?", font=P(70), fill="white", anchor="lm")
                for i, (ptxt, tm) in enumerate(zip(spec["bullets"], btimes)):
                    if tseg >= tm:
                        p = ease_out((tseg - tm) / 0.3); dx = (1 - p) * -260
                        y = 1180 + i * 120; dl.ellipse([62 + dx, y - 16, 94 + dx, y + 16], fill=(255, 210, 80))
                        col = (255, 255, 255, int(255 * p))
                        for j, l in enumerate(wrap(dl, ptxt, P(40), 760 if i == 0 else 900)[:2]): dl.text((120 + dx, y + j * 50), l, font=P(40), fill=col, anchor="lm")
                im.paste(lay, (0, int(up)), lay)
                char(im, d_explain, W - d_explain.width - 20, 1050 + 120 + up, talk=amp("f", tseg), t=t)
                c = cap["f"] if tseg < capsw else cap["f2"]
        # slow camera push-in on the middle area
        z = 1 + 0.03 * min(1, tseg / max(dseg, 0.1))
        if z > 1.001:
            reg = im.crop((0, 200, W, 1680)); rw, rh = reg.size; cw, ch = rw / z, rh / z
            reg = reg.crop(((rw - cw) / 2, (rh - ch) / 2, (rw + cw) / 2, (rh + ch) / 2)).resize((rw, rh), Image.BILINEAR); im.paste(reg, (0, 200))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, 200], fill=GREEN); d.text((W/2, 100), f"Dr Saathi ke OT Kisse #{num}", font=P(50), fill="white", anchor="mm")
        if c:
            d.rectangle([0, 1680, W, H], fill=GREEN); ls = wrap(d, c, P(40), 980)[:3]; y0 = 1800 - (len(ls) - 1) * 27
            for i, l in enumerate(ls): d.text((W/2, y0 + i * 54), l, font=P(40), fill="white", anchor="mm")
        return im
    # contact sheet for checking
    starts = {}; t0 = 0
    for n, d_ in segs: starts[n] = (t0, d_); t0 += d_
    picks = [("intro", 1.0), ("q", starts["q"][1] - 0.5), ("a", starts["a"][1] - 0.5), ("f", btimes[1] + 0.5), ("f", starts["f"][1] - 0.3), ("e", 1.0)]
    thumbs = [frame(n, starts[n][0] + ts, ts, starts[n][1]).resize((270, 480)) for n, ts in picks]
    sheet = Image.new("RGB", (270 * 3, 960)); [sheet.paste(im, ((i % 3) * 270, (i // 3) * 480)) for i, im in enumerate(thumbs)]
    sheet.save(os.path.join(outdir, f"{slug}_check.jpg"), quality=85)
    frame("q", starts["q"][0] + 1, 1).convert("RGB").save(os.path.join(outdir, f"{slug}_cover.jpg"), quality=88)
    if preview: return dict(ok=True, preview=True, seconds=round(total, 1))
    mp4 = os.path.join(outdir, f"{slug}.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                          "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", "-metadata", f"title={spec['youtube']['title']}", mp4], stdin=subprocess.PIPE)
    for n, d_ in segs:
        s0 = starts[n][0]
        for f in range(int(round(d_ * FPS))): p.stdin.write(frame(n, s0 + f / FPS, f / FPS, d_).tobytes())
    p.stdin.close(); p.wait(); os.remove(wav)
    return dict(ok=p.returncode == 0, mp4=mp4, seconds=round(total, 1), check=os.path.join(outdir, f"{slug}_check.jpg"))

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    errs = check(spec)
    if errs: print(json.dumps(dict(ok=False, invalid=errs), ensure_ascii=False, indent=1)); sys.exit(1)
    print(json.dumps(build(spec, sys.argv[2], "--preview" in sys.argv), ensure_ascii=False))
