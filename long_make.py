"""SurgerySaathi long-form (16:9) video engine.
Usage: python3 long_make.py spec.json OUTDIR [--preview]
Builds OUTDIR/<slug>.mp4 (1920x1080), <slug>_thumb.jpg (1280x720) and <slug>_check.jpg (contact sheet).
Spec: {slug, lang, patient, title, subtitle, intro_vo:[voice, caption], chapters:[{title, lines:[[role, voice, caption, expr, reveal]], bullets:[..]}], youtube:{...}}
 role = "p" (patient) or "dr"; expr = worried/doubt/relieved/thankful (patient) or happy/explain/reassure/surprised (dr);
 reveal = number of bullets visible from this line on (optional).
"""
import json, math, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from PIL import Image, ImageDraw, ImageFilter
import ss_make as S

W, H = 1920, 1080; FPS = 25
GREEN, LIGHT, RED, DARK, OK = S.GREEN, S.LIGHT, S.RED, S.DARK, S.OK
NAMES = {"hi": {"uncle": "Uncle", "dadi": "Dadi", "didi": "Didi", "dr": "Dr Saathi"},
         "bn": {"uncle": "কাকু", "dadi": "দিদা", "didi": "দিদি", "dr": "ডাঃ সাথী"}}
TXT = {"hi": dict(step="STEP {i}/{n}", tag="Darr nahi, taiyaari!", ai="AI character · sirf jaankari ke liye", sub="SUBSCRIBE",
                  ask="Apna sawaal comment mein likhiye!"),
       "bn": dict(step="ধাপ {i}/{n}", tag="ভয় নয়, প্রস্তুতি!", ai="AI চরিত্র · শুধু জানার জন্য", sub="SUBSCRIBE",
                  ask="আপনার প্রশ্ন কমেন্টে লিখুন!")}

def bg_img():
    im = Image.new("RGB", (W, H), (200, 228, 214)); d = ImageDraw.Draw(im)
    for y in range(80, 760):
        p = (y - 80) / 680; d.line([0, y, W, y], fill=(int(150 + 40 * p), int(205 + 15 * p), int(190 + 15 * p)))
    for x in range(0, W, 240): d.rectangle([x + 8, 100, x + 232, 740], outline=(135, 190, 172), width=4)
    for y in range(760, 940):
        p = (y - 760) / 180; d.line([0, y, W, y], fill=(int(120 - 20 * p), int(170 - 20 * p), int(160 - 20 * p)))
    for x in range(-800, W + 800, 140): d.line([W / 2 + (x - W / 2) * 0.35, 760, x, 940], fill=(105, 152, 142), width=3)
    d.line([0, 760, W, 760], fill=(90, 140, 128), width=6)
    # monitor (left, wall arm)
    d.rounded_rectangle([40, 110, 330, 300], radius=14, fill=(40, 45, 50), outline=(100, 105, 110), width=6)
    # IV stand (right)
    d.line([1880, 120, 1880, 740], fill=(150, 160, 165), width=10); d.line([1840, 130, 1915, 130], fill=(150, 160, 165), width=8)
    d.rounded_rectangle([1848, 140, 1878, 220], radius=8, fill=(230, 240, 245), outline=(140, 150, 160), width=3)
    return im

def monitor(d, t):
    x0, y0 = 52, 122; d.rectangle([x0, y0, 318, 288], fill=(10, 14, 16))
    pts = []
    for i in range(170):
        ph = (i / 60 + t * 1.2) % 1.0
        v = 0 if ph < 0.4 else -48 if ph < 0.44 else 18 if ph < 0.48 else 0 if ph < 0.6 else -10 * math.sin((ph - 0.6) / 0.2 * math.pi) if ph < 0.8 else 0
        pts.append((x0 + 8 + i, y0 + 70 + v))
    d.line(pts, fill=(60, 230, 90), width=3)
    f = S.LATIN(26); d.text((x0 + 186, y0 + 14), "HR 76", font=f, fill=(60, 230, 90))
    d.text((x0 + 186, y0 + 54), "SpO2", font=S.LATIN(20), fill=(80, 190, 255)); d.text((x0 + 186, y0 + 76), "99%", font=f, fill=(80, 190, 255))
    d.text((x0 + 10, y0 + 128), "NIBP 118/76", font=S.LATIN(24), fill=(255, 210, 80))

def build(spec, outdir, preview=False):
    os.makedirs(outdir, exist_ok=True)
    L = spec.get("lang", "hi"); S.LANG = L; T = TXT[L]; N = NAMES[L]; P = S.P
    pt = spec.get("patient", "uncle"); slug = spec["slug"]
    # ---------- audio & timeline ----------
    sr = 24000
    def clip(role, text):
        a, _, _ = S.say_role(pt if role == "p" else "dr", [[text, 0.05]]); return a
    segs = []   # dict(kind, dur, ...)
    a = clip("dr", spec["intro_vo"][0])
    segs.append(dict(kind="title", dur=max(4.0, len(a) / sr + 1.2), audio=a, cap=spec["intro_vo"][1], role="dr"))
    nch = len(spec["chapters"])
    for ci, ch in enumerate(spec["chapters"]):
        segs.append(dict(kind="card", dur=2.4, ci=ci))
        shown = 0
        for ln in ch["lines"]:
            role, voice, cap, expr = ln[:4]
            if len(ln) > 4: shown = ln[4]
            a = clip(role, voice)
            segs.append(dict(kind="line", dur=len(a) / sr + 0.45, audio=a, cap=cap, role=role, expr=expr, ci=ci, shown=shown))
    a, _, _ = S.say_role("dr", spec.get("end_vo") or (S.END_VO_BN if L == "bn" else S.END_VO))
    segs.append(dict(kind="end", dur=len(a) / sr + 2.5, audio=a, role="dr"))
    t0 = 0
    for s in segs: s["t0"] = t0; t0 += s["dur"]
    total = t0; NS = int(total * sr)
    track = np.zeros(NS + sr, dtype=np.float32)
    rng = np.random.default_rng(1)
    for s in segs:
        if "audio" in s: i = int((s["t0"] + 0.25) * sr); track[i:i + len(s["audio"])] += s["audio"]
        if s["kind"] in ("card", "end") or s is segs[0]:
            Lw = int(0.4 * sr); x = np.arange(Lw) / Lw; nse = np.convolve(rng.standard_normal(Lw), np.ones(6) / 6, mode="same") * np.sin(np.pi * x) ** 2
            i = int(max(0, s["t0"] - 0.1) * sr); track[i:i + Lw] += 0.10 * nse
    # dings when bullets appear
    ding = np.arange(int(0.25 * sr)) / sr; prev = 0
    for s in segs:
        if s["kind"] == "line":
            if s["shown"] > prev: i = int((s["t0"] + 0.15) * sr); track[i:i + len(ding)] += 0.06 * np.sin(2 * np.pi * 1320 * ding) * np.exp(-ding * 12)
            prev = s["shown"]
        elif s["kind"] == "card": prev = 0
    tt = np.arange(NS) / sr; bed = np.zeros(NS)
    chords = [(261.6, 329.6, 392.0), (220.0, 261.6, 329.6), (174.6, 220.0, 261.6), (196.0, 246.9, 293.7)]
    for i in range(int(total / 2) + 2):
        ch = chords[i % 4]; a0 = int(i * 2 * sr); b0 = min(NS, a0 + 2 * sr)
        if a0 >= NS: break
        s_ = tt[a0:b0] - tt[a0]; env = np.minimum(1, s_ / 0.3) * np.exp(-s_ * 0.6); bed[a0:b0] += sum(np.sin(2 * np.pi * f * s_) * 0.33 for f in ch) * env
    track = track[:NS] + 0.028 * bed; track /= max(1, np.abs(track).max() / 0.95)
    wav = os.path.join(outdir, f"{slug}.wav"); sf.write(wav, track, sr)
    hop = sr // FPS
    for s in segs:
        if "audio" in s:
            a = s["audio"]; n = len(a) // hop + 1
            e = np.array([np.sqrt(np.mean(a[i * hop:(i + 1) * hop] ** 2)) if i * hop < len(a) else 0 for i in range(n)])
            s["env"] = np.convolve(e / (e.max() + 1e-6), np.ones(3) / 3, mode="same")
    def amp(s, ts):
        e = s.get("env"); i = int((ts - 0.25) * FPS)
        return float(e[i]) if e is not None and 0 <= i < len(e) else 0.0

    # ---------- art ----------
    BG = bg_img(); CH = 560
    PI = {k: S.cast(f"{pt}_{k}", CH) for k in ("worried", "doubt", "relieved", "thankful")}
    DI = {k: S.cast(f"dr_{k}", CH) for k in ("happy", "explain", "reassure", "surprised")}
    port = S.cast("dr_portrait", 820); pport = S.cast(f"{pt}_thankful", 520)
    board_cache = {}
    def board(ci, shown):
        k = (ci, shown)
        if k in board_cache: return board_cache[k]
        ch = spec["chapters"][ci]; lay = Image.new("RGBA", (840, 640), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.rounded_rectangle([6, 6, 834, 634], radius=30, fill=(16, 70, 36, 245), outline=(255, 255, 255), width=5)
        d.text((40, 40), T["step"].format(i=ci + 1, n=nch), font=S.LATIN(28), fill=(255, 210, 80))
        tl = S.wrap(d, ch["title"], P(58), 760)[:2]
        for i, l in enumerate(tl): d.text((40, 82 + i * 66), l, font=P(58), fill="white")
        y = 110 + 66 * len(tl) + 24
        for i, b in enumerate(ch["bullets"][:shown]):
            d.ellipse([40, y + 8, 84, y + 52], fill=(60, 200, 100)); d.line([(51, y + 30), (60, y + 41), (75, y + 20)], fill="white", width=6)
            for j, l in enumerate(S.wrap(d, b, P(44), 700)[:2]): d.text((104, y + j * 54), l, font=P(44), fill="white")
            y += 54 * min(2, len(S.wrap(d, b, P(44), 700))) + 26
        board_cache[k] = lay; return lay
    def ease_out(p): p = max(0.0, min(1.0, p)); return 1 - (1 - p) ** 3
    def caption(d, text, who):
        d.rectangle([0, 940, W, H], fill=GREEN)
        full = f"{N[who]}: {text}" if who else text
        ls = S.wrap(d, full, P(38), 1800)[:3]; y0 = 1010 - (len(ls) - 1) * 24
        for i, l in enumerate(ls): d.text((W / 2, y0 + i * 48), l, font=P(38), fill="white", anchor="mm")
    def header(d, right=""):
        d.rectangle([0, 0, W, 80], fill=GREEN)
        d.text((40, 40), "SurgerySaathi", font=S.LATIN(38), fill="white", anchor="lm")
        d.text((W / 2, 40), spec["title"], font=P(38), fill="white", anchor="mm")
        if right: d.text((W - 40, 40), right, font=S.LATIN(30), fill=(255, 210, 80), anchor="rm")

    def scene(t, ts, s):
        im = BG.copy(); d = ImageDraw.Draw(im); monitor(d, t)
        role = s.get("role"); talk = amp(s, ts) if s["kind"] == "line" else 0
        pexpr = s["expr"] if role == "p" else s.get("pexpr", "doubt")
        dexpr = s["expr"] if role == "dr" else "happy"
        pim, dim = PI[pexpr], DI[dexpr]
        def put(img, x, act):
            k = 1 + (0.03 * talk if act else 0); c = img.resize((int(img.width * k), int(img.height * k)), Image.BILINEAR) if act and talk > 0.05 else img
            dy = (-14 * talk if act else 0) + 4 * math.sin(t * 2.2 + x)
            if not act: c = c  # idle
            im.paste(c, (int(x + (img.width - c.width) / 2), int(940 - c.height + dy)), c)
        put(pim, 20, role == "p"); put(dim, W - 20 - dim.width, role == "dr")
        b = board(s["ci"], s["shown"]); im.paste(b, (540, 100), b)
        # speaker marker
        d = ImageDraw.Draw(im)
        if role == "p": d.polygon([(20 + pim.width // 2 - 18, 330), (20 + pim.width // 2 + 18, 330), (20 + pim.width // 2, 354)], fill=(255, 210, 80))
        else: d.polygon([(W - 20 - dim.width // 2 - 18, 330), (W - 20 - dim.width // 2 + 18, 330), (W - 20 - dim.width // 2, 354)], fill=(255, 210, 80))
        header(d, T["step"].format(i=s["ci"] + 1, n=nch)); caption(d, s["cap"], role and ("dr" if role == "dr" else pt))
        return im

    def title_frame(t, ts, s):
        im = BG.copy().filter(ImageFilter.GaussianBlur(6)); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W, H], fill=None)
        k = ease_out(ts / 0.8)
        ov = Image.new("RGBA", (W, H), (16, 70, 36, 200)); im.paste(ov, (0, 0), ov); d = ImageDraw.Draw(im)
        x = int(-600 + 640 * k); im.paste(PI["worried"], (x, 940 - CH + 140), PI["worried"])
        dx = int(W + 600 - 640 * k - DI["happy"].width); im.paste(DI["happy"], (dx, 940 - CH + 140), DI["happy"])
        a = min(1, max(0, (ts - 0.3) / 0.6))
        d.text((W / 2, 300), spec["title"], font=P(int(96 * (0.8 + 0.2 * a))), fill="white", anchor="mm")
        d.text((W / 2, 410), spec["subtitle"], font=P(48), fill=(255, 210, 80), anchor="mm")
        d.text((W / 2, 500), "Dr Saathi ke OT Kisse · Special", font=S.LATIN(34), fill=(220, 240, 225), anchor="mm")
        caption(d, s["cap"], "dr"); return im

    def card_frame(t, ts, s):
        ci = s["ci"]; im = Image.new("RGB", (W, H), GREEN); d = ImageDraw.Draw(im)
        for r in range(0, 1400, 70): d.ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], outline=(24, 95, 50), width=3)
        k = ease_out(ts / 0.5)
        d.text((W / 2, 400 - 40 * (1 - k)), T["step"].format(i=ci + 1, n=nch), font=S.LATIN(56), fill=(255, 210, 80), anchor="mm")
        d.text((W / 2, 540), spec["chapters"][ci]["title"], font=P(int(100 * (0.85 + 0.15 * k))), fill="white", anchor="mm")
        c = S.cast("dr_explain", 300) if ci == 0 else None
        d.rectangle([W / 2 - 300 * k, 640, W / 2 + 300 * k, 650], fill=(255, 210, 80))
        return im

    def end_frame(t, ts, s):
        im = Image.new("RGB", (W, H), LIGHT); d = ImageDraw.Draw(im)
        for r in range(0, 900, 60): d.ellipse([480 - r, 560 - r, 480 + r, 560 + r], outline=(210, 232, 216), width=3)
        k = ease_out(ts / 0.6)
        im.paste(port, (int(80 - 300 * (1 - k)), H - port.height), port)
        im.paste(pport, (int(600 + 300 * (1 - k)), H - pport.height), pport)
        d.text((1450, 300), "Surgery", font=S.LATIN(110), fill=GREEN, anchor="rm"); d.text((1450, 300), "Saathi", font=S.LATIN(110), fill=RED, anchor="lm")
        d.text((1450, 420), T["tag"], font=P(60), fill=DARK, anchor="mm")
        pulse = 1 + 0.04 * math.sin(ts * 6)
        bw, bh = 360 * pulse, 90 * pulse
        d.rounded_rectangle([1450 - bw / 2, 520 - bh / 2, 1450 + bw / 2, 520 + bh / 2], radius=45, fill=RED)
        d.text((1450, 520), T["sub"], font=S.LATIN(44), fill="white", anchor="mm")
        d.text((1450, 630), S.SITE_HANDLE, font=S.LATIN(46), fill=GREEN, anchor="mm")
        d.text((1500, 730), T["ask"], font=P(42), fill=DARK, anchor="mm")
        d.text((1450, 1030), T["ai"], font=P(28), fill=(90, 110, 95), anchor="mm")
        return im

    # patient expression carried into Dr lines (last patient expr)
    last = "worried"
    for s in segs:
        if s["kind"] == "line":
            if s["role"] == "p": last = s["expr"]
            else: s["pexpr"] = last
    FR = dict(title=title_frame, card=card_frame, line=scene, end=end_frame)
    def frame(t):
        for s in segs:
            if s["t0"] <= t < s["t0"] + s["dur"]: return FR[s["kind"]](t, t - s["t0"], s)
        s = segs[-1]; return FR[s["kind"]](t, t - s["t0"], s)

    # check sheet: title, one card, 6 line frames, end
    picks = [segs[0]["t0"] + 2] + [s["t0"] + 1.2 for s in segs if s["kind"] == "card"][:1]
    lines = [s for s in segs if s["kind"] == "line"]
    picks += [lines[int(i * (len(lines) - 1) / 5)]["t0"] + 0.8 for i in range(6)] + [segs[-1]["t0"] + 1.5]
    th = [frame(x).resize((640, 360)) for x in picks]
    sheet = Image.new("RGB", (640 * 3, 360 * 3)); [sheet.paste(im, ((i % 3) * 640, (i // 3) * 360)) for i, im in enumerate(th)]
    sheet.save(os.path.join(outdir, f"{slug}_check.jpg"), quality=85)
    # thumbnail
    tim = title_frame(0, 3, segs[0]).resize((1280, 720)); td = ImageDraw.Draw(tim); td.rectangle([0, 620, 1280, 720], fill=GREEN)
    td.text((640, 670), spec.get("thumb_text", spec["subtitle"]), font=P(52), fill="white", anchor="mm")
    tim.save(os.path.join(outdir, f"{slug}_thumb.jpg"), quality=90)
    if preview: os.remove(wav); return dict(ok=True, preview=True, seconds=round(total, 1))
    mp4 = os.path.join(outdir, f"{slug}.mp4")
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", wav,
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                          "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", mp4], stdin=subprocess.PIPE)
    for f in range(int(total * FPS)): p.stdin.write(frame(f / FPS).tobytes())
    p.stdin.close(); p.wait(); os.remove(wav)
    return dict(ok=p.returncode == 0, mp4=mp4, seconds=round(total, 1), check=os.path.join(outdir, f"{slug}_check.jpg"))

if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    print(json.dumps(build(spec, sys.argv[2], "--preview" in sys.argv), ensure_ascii=False))
