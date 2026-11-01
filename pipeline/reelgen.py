"""Render a Hindi explainer Reel (1080x1920, 30 fps) from a JSON spec.

Spec (one video):
{
  "slug": "h_2026-11-02_fasting",          # file name
  "theme": "health" | "trading",
  "series": "optional small line under the brand",
  "name": "Big Hindi title on the hook",   "en": "English subtitle",
  "icon": "lungs|heart|candles|pill|clock|shield|stomach|brain",
  "scenes": [
    {"kind": "hook",    "cap": [["text", 0], ["highlight", 1]], "vo": ["phrase", ...]},
    {"kind": "steps",   "cap": [...], "items": ["step 1", "step 2", "step 3"], "vo": [one phrase per item]},
    {"kind": "counter", "cap": [...], "to": 28, "unit": "सेकंड", "vo": [...]},
    {"kind": "zones",   "cap": [...], "items": [["range", "meaning", "g|a|r"], ...], "vo": [one phrase per item]},
    {"kind": "chart",   "cap": [...], "pattern": "breakout|fakeout|retest|pullback|downtrend|range|trail",
                        "labels": ["label for key point 1", ...], "vo": [one phrase per label]},
    {"kind": "caution", "cap": [...], "items": ["warning 1", "warning 2"], "vo": [one per item, then the follow line]}
  ]
}
Caption text uses "\n" for a line break; highlight flag 1 colours that part.
The LAST scene must be "caution"; its final vo phrase is the follow line and shows the end card.
"""
import sys, os, json, math, subprocess
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
FN = os.path.join(HERE, "fonts", "NotoSansDevanagari-")
INTER = os.path.join(HERE, "fonts", "Inter-")
LEAD, TAIL = 0.3, 0.5

_fc = {}
def hf(w, s):
    k = (w, s)
    if k not in _fc: _fc[k] = ImageFont.truetype(FN + w + ".ttf", s, layout_engine=ImageFont.Layout.RAQM)
    return _fc[k]
def inter(w, s):
    k = ("I" + w, s)
    if k not in _fc: _fc[k] = ImageFont.truetype(INTER + w + ".otf", s)
    return _fc[k]

BG = (10, 18, 28); CARD = (19, 31, 45); WHITE = (238, 242, 245); MUTED = (128, 144, 160)
GREEN = (82, 206, 142); AMBER = (246, 186, 72); RED = (240, 102, 98)
UP = (38, 196, 180); DOWN = (240, 104, 96)
ZC = {"g": GREEN, "a": AMBER, "r": RED}
THEMES = {
    "health": dict(acc=(92, 202, 236), brand="सेहत दीदी", voice="hf_alpha",
                   end=["सिर्फ़ जानकारी के लिए, यह जाँच का विकल्प नहीं है।", "निदान और इलाज के लिए डॉक्टर से मिलें।", "आवाज़ AI से बनाई गई है।"]),
    "trading": dict(acc=(38, 196, 180), brand="@trading71639", voice="hm_omega",
                    end=["सिर्फ़ शिक्षा के लिए, यह निवेश सलाह नहीं है।", "कोई स्टॉक खरीदने/बेचने की सलाह नहीं।", "आवाज़ AI से बनाई गई है।"]),
}

def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def mix(c, a, base=BG): return tuple(int(base[k] + (c[k] - base[k]) * a) for k in range(3))

# ---- mixed-script text (Devanagari font has no Latin letters) ----
def _lat(f): return inter("SemiBold", int(f.size * 0.92))
def _is_lat(ch): return (ch.isascii() and ch.isalpha()) or ch in "•%₹@×÷−"
def _runs(s):
    out = []
    for ch in s:
        L = _is_lat(ch)
        if out and out[-1][1] == L: out[-1][0] += ch
        else: out.append([ch, L])
    return out
def tw(d, s, f):
    if f.path.endswith(".otf"): return d.textlength(s, font=f)
    return sum(d.textlength(r, font=_lat(f) if L else f) for r, L in _runs(s))
def T(d, xy, s, f, fill):
    if f.path.endswith(".otf"): d.text(xy, s, font=f, fill=fill); return
    x, y = xy; base = y + f.getmetrics()[0]
    for r, L in _runs(s):
        ff = _lat(f) if L else f
        d.text((x, base), r, font=ff, fill=fill, anchor="ls"); x += d.textlength(r, font=ff)
def fit(d, s, weight, size, maxw, minsize=30):
    while size > minsize and tw(d, s, hf(weight, size)) > maxw: size -= 2
    return hf(weight, size)

# ---- synthetic chart patterns (educational, no real stocks) ----
def pattern(name):
    """returns candles [(o,h,l,c,v)], level lines [(price, label, colour)], key points [(idx, price, colour)]"""
    import random
    rnd = random.Random(name)
    C = []; p = 100.0
    def add(o, c, v=50, wick=1.2):
        h = max(o, c) + rnd.uniform(0.2, wick); l = min(o, c) - rnd.uniform(0.2, wick)
        C.append((o, h, l, c, v))
    def walk(n, drift, vol=1.6, v=45):
        nonlocal p
        for _ in range(n):
            c = p + drift + rnd.uniform(-vol, vol); add(p, c, v + rnd.uniform(-10, 10)); p = c
    def clamp_walk(n, lo, hi, v=45):
        nonlocal p
        for _ in range(n):
            c = min(hi, max(lo, p + rnd.uniform(-2.2, 2.2))); add(p, c, v + rnd.uniform(-10, 10)); p = c
    if name == "breakout":
        clamp_walk(16, 92, 99); lvl = 100
        add(p, 104.5, 130); p = 104.5; k1 = len(C) - 1
        walk(4, 1.0); walk(3, -1.1); k2 = len(C) - 1; walk(6, 1.4)
        return C, [(lvl, "रेज़िस्टेंस", MUTED)], [(k1, C[k1][3], UP), (k1, None, AMBER), (k2, C[k2][2], AMBER)]
    if name == "fakeout":
        clamp_walk(16, 92, 99); lvl = 100
        add(p, 103.5, 120); p = 103.5; k1 = len(C) - 1
        walk(1, 0.3); add(p, 98.6, 90); p = 98.6; k2 = len(C) - 1; walk(6, -1.2)
        return C, [(lvl, "रेज़िस्टेंस", MUTED), (C[k1][2] - 0.4, "स्टॉप लॉस", RED)], [(k1, C[k1][3], UP), (k2, C[k2][3], RED), (len(C) - 1, C[-1][3], MUTED)]
    if name == "retest":
        clamp_walk(14, 92, 99); lvl = 100
        add(p, 104, 120); p = 104; k1 = len(C) - 1; walk(3, 1.2)
        for c in (104, 102, 100.6): add(p, c, 40); p = c
        k2 = len(C) - 1; walk(7, 1.5)
        return C, [(lvl, "अब सपोर्ट", MUTED)], [(k1, C[k1][3], UP), (k2, C[k2][2], AMBER), (len(C) - 1, C[-1][3], UP)]
    if name == "pullback":
        walk(10, 1.1); k0 = len(C) - 1; walk(4, -1.3); k1 = len(C) - 1; walk(8, 1.3)
        return C, [], [(k0, C[k0][1], MUTED), (k1, C[k1][2], AMBER), (len(C) - 1, C[-1][3], UP)]
    if name == "downtrend":
        walk(6, -1.2); k0 = len(C) - 1; walk(3, 1.0); k1 = len(C) - 1; walk(8, -1.4)
        return C, [], [(k0, C[k0][2], DOWN), (k1, C[k1][1], AMBER), (len(C) - 1, C[-1][3], DOWN)]
    if name == "range":
        clamp_walk(26, 94, 104)
        hi_i = max(range(26), key=lambda i: C[i][1]); lo_i = min(range(26), key=lambda i: C[i][2])
        return C, [(C[hi_i][1] + 0.3, "रेज़िस्टेंस", RED), (C[lo_i][2] - 0.3, "सपोर्ट", GREEN)], [(hi_i, C[hi_i][1], RED), (lo_i, C[lo_i][2], GREEN)]
    if name == "trail":
        walk(8, 1.0); k0 = len(C) - 1; walk(8, 1.2); k1 = len(C) - 1; walk(3, -2.0); k2 = len(C) - 1
        return C, [], [(k0, C[k0][2], AMBER), (k1, C[k1][2], AMBER), (k2, C[k2][3], RED)]
    raise ValueError("unknown pattern " + name)

class Reel:
    def __init__(self, spec, timing):
        self.s = spec; th = THEMES[spec.get("theme", "health")]
        self.acc, self.brand, self.end = th["acc"], th["brand"], th["end"]
        self.scenes, S = [], 0.0
        n = len(timing)
        for si, (sc, t) in enumerate(zip(spec["scenes"], timing)):
            L = t["dur"] + LEAD + TAIL + (1.5 if si == n - 1 else 0)
            sc = dict(sc, start=S, end=S + L, cues=[S + LEAD + o for o in t["offs"]], vo_start=S + LEAD)
            if sc["kind"] == "chart": sc["_pat"] = pattern(sc["pattern"])
            self.scenes.append(sc); S += L
        self.total = S

    # -- pieces --
    def header(self, d):
        T(d, (60, 120), self.brand, hf("SemiBold", 36), WHITE)
        x = 60 + tw(d, self.brand, hf("SemiBold", 36)) + 20
        d.rounded_rectangle([x, 126, x + 150, 172], radius=23, outline=self.acc, width=2)
        T(d, (x + 75 - tw(d, "AI आवाज़", hf("SemiBold", 28)) / 2, 128), "AI आवाज़", hf("SemiBold", 28), self.acc)
        if self.s.get("series"): T(d, (60, 190), self.s["series"], hf("Regular", 34), MUTED)

    def caption(self, d, parts, a, yoff):
        lines = [[]]
        for txt, hl in parts:
            for j, s in enumerate(txt.split("\n")):
                if j: lines.append([])
                if s: lines[-1].append((s, hl))
        y = 300 + yoff
        for ln in lines:
            f = fit(d, "".join(s for s, _ in ln), "Bold", 66, 980)
            x = (W - sum(tw(d, s, f) for s, _ in ln)) / 2
            for s, hl in ln:
                T(d, (x, y), s, f, mix(self.acc if hl else WHITE, a)); x += tw(d, s, f)
            y += 96

    def ring(self, d, cx, cy, r, frac, col, w=22):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CARD, width=w)
        if frac > 0: d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + 360 * min(frac, 1), fill=col, width=w)

    def icon(self, d, kind, cx, cy, sc, col, w=9):
        if kind == "lungs":
            d.line([(cx, cy - 190 * sc), (cx, cy - 60 * sc)], fill=col, width=w)
            d.line([(cx, cy - 60 * sc), (cx - 60 * sc, cy)], fill=col, width=w); d.line([(cx, cy - 60 * sc), (cx + 60 * sc, cy)], fill=col, width=w)
            d.rounded_rectangle([cx - 230 * sc, cy - 130 * sc, cx - 45 * sc, cy + 190 * sc], radius=int(95 * sc), outline=col, width=w)
            d.rounded_rectangle([cx + 45 * sc, cy - 130 * sc, cx + 230 * sc, cy + 190 * sc], radius=int(95 * sc), outline=col, width=w)
        elif kind == "heart":
            r = 95 * sc
            d.arc([cx - 2 * r, cy - 1.4 * r, cx, cy + 0.6 * r], 135, 360, fill=col, width=w)
            d.arc([cx, cy - 1.4 * r, cx + 2 * r, cy + 0.6 * r], 180, 405, fill=col, width=w)
            d.line([(cx - 1.7 * r, cy + 0.15 * r), (cx, cy + 1.9 * r), (cx + 1.7 * r, cy + 0.15 * r)], fill=col, width=w)
        elif kind == "candles":
            for k, (x, o, c, hi, lo) in enumerate([(-150, 60, -40, 120, -90), (0, -10, -150, 40, -190), (150, -120, -230, -80, -270)]):
                colr = UP if c < o else DOWN
                d.line([(cx + x * sc, cy + hi * sc + 80 * sc), (cx + x * sc, cy + lo * sc + 80 * sc)], fill=colr, width=w)
                d.rectangle([cx + (x - 40) * sc, cy + min(o, c) * sc + 80 * sc, cx + (x + 40) * sc, cy + max(o, c) * sc + 80 * sc], fill=colr)
        elif kind == "pill":
            d.rounded_rectangle([cx - 220 * sc, cy - 85 * sc, cx + 220 * sc, cy + 85 * sc], radius=int(85 * sc), outline=col, width=w)
            d.line([(cx, cy - 85 * sc), (cx, cy + 85 * sc)], fill=col, width=w)
        elif kind == "clock":
            d.ellipse([cx - 200 * sc, cy - 200 * sc, cx + 200 * sc, cy + 200 * sc], outline=col, width=w)
            d.line([(cx, cy), (cx, cy - 130 * sc)], fill=col, width=w); d.line([(cx, cy), (cx + 95 * sc, cy + 40 * sc)], fill=col, width=w)
        elif kind == "shield":
            d.line([(cx, cy - 210 * sc), (cx + 180 * sc, cy - 140 * sc), (cx + 160 * sc, cy + 60 * sc), (cx, cy + 210 * sc),
                    (cx - 160 * sc, cy + 60 * sc), (cx - 180 * sc, cy - 140 * sc), (cx, cy - 210 * sc)], fill=col, width=w, joint="curve")
            d.line([(cx - 70 * sc, cy), (cx - 15 * sc, cy + 60 * sc), (cx + 85 * sc, cy - 60 * sc)], fill=col, width=w)
        elif kind == "stomach":
            pts = [(40, -240), (40, -130), (110, -80), (150, 20), (120, 130), (30, 200), (-90, 210), (-180, 150), (-200, 70),
                   (-150, 40), (-80, 90), (0, 80), (40, 20), (20, -60), (-30, -110), (-30, -240)]
            d.line([(cx + x * sc, cy + y * sc) for x, y in pts], fill=col, width=w, joint="curve")
        else:  # brain / default: concentric circle motif
            for k in range(3): d.ellipse([cx - (200 - 60 * k) * sc, cy - (200 - 60 * k) * sc, cx + (200 - 60 * k) * sc, cy + (200 - 60 * k) * sc], outline=col, width=w)

    # -- scene visuals --
    def v_hook(self, d, sc, t):
        lt = t - sc["start"]; a = ease(lt / 0.6); cx, cy = W // 2, 960
        self.ring(d, cx, cy, 300, ease(lt / 1.2), self.acc, 14)
        breath = 1 + 0.05 * math.sin(lt * 2 * math.pi / 3.0)
        self.icon(d, self.s.get("icon", "brain"), cx, cy + 20, 0.95 * breath * (0.8 + 0.2 * a), mix(self.acc, a))
        b = ease((lt - 0.5) / 0.5)
        f = fit(d, self.s["name"], "Bold", 84, 980)
        T(d, ((W - tw(d, self.s["name"], f)) / 2, 1320 + (1 - b) * 20), self.s["name"], f, mix(WHITE, b))
        e = self.s.get("en", ""); fe = inter("Medium", 40)
        T(d, ((W - tw(d, e, fe)) / 2, 1450 + (1 - b) * 20), e, fe, mix(MUTED, b))

    def _cards(self, d, sc, t, items, color_of, text_of, sub_of=None, hgt=200, gap=50, y0=640):
        cues = sc["cues"]
        for i, it in enumerate(items):
            c = cues[min(i, len(cues) - 1)]
            if t < c: continue
            a = ease((t - c) / 0.4)
            active = (i == len(items) - 1) or t < cues[min(i + 1, len(cues) - 1)]
            y = y0 + i * (hgt + gap); x = 70 + (1 - a) * 120
            yield i, it, a, active, x, y

    def v_steps(self, d, sc, t):
        n = len(sc["items"]); hgt = 200 if n <= 3 else 160
        for i, txt, a, active, x, y in self._cards(d, sc, t, sc["items"], None, None, hgt=hgt, gap=50 if n <= 3 else 30):
            d.rounded_rectangle([x, y, x + 940, y + hgt], radius=28, fill=mix(CARD, a), outline=mix(self.acc if active else CARD, a), width=3)
            d.ellipse([x + 40, y + hgt / 2 - 45, x + 130, y + hgt / 2 + 45], fill=mix(self.acc if active else MUTED, a))
            s = str(i + 1); fi = inter("Bold", 44); T(d, (x + 85 - tw(d, s, fi) / 2, y + hgt / 2 - 30), s, fi, BG)
            f = fit(d, txt, "SemiBold", 48, 740)
            T(d, (x + 165, y + hgt / 2 - 30), txt, f, mix(WHITE if active else (190, 200, 210), a))

    def v_zones(self, d, sc, t):
        n = len(sc["items"]); hgt = {1: 300, 2: 300, 3: 230}.get(n, 180)
        for i, (rng, mean, z), a, active, x, y in self._cards(d, sc, t, sc["items"], None, None, hgt=hgt, gap=36, y0=620):
            col = ZC.get(z, self.acc)
            d.rounded_rectangle([x, y, x + 940, y + hgt], radius=28, fill=mix(CARD, a))
            d.rounded_rectangle([x, y, x + 18, y + hgt], radius=9, fill=mix(col, a))
            d.ellipse([x + 60, y + hgt / 2 - 22, x + 104, y + hgt / 2 + 22], fill=mix(col, a))
            T(d, (x + 140, y + hgt / 2 - 80), rng, fit(d, rng, "Bold", 50, 770), mix(WHITE, a))
            T(d, (x + 140, y + hgt / 2 + 6), mean, fit(d, mean, "Regular", 42, 770), mix(col, a))

    def v_counter(self, d, sc, t):
        lt = t - sc["vo_start"]; dur = sc["end"] - sc["vo_start"] - 0.8
        g = ease(lt / max(dur, 1.0)) if lt > 0 else 0
        val = sc["to"] * g; s = (f"{val:.1f}" if isinstance(sc["to"], float) and sc["to"] % 1 else str(int(round(val))))
        cx, cy = W // 2, 1000
        self.ring(d, cx, cy, 300, g, self.acc, 26)
        fn = inter("Bold", 210 if len(s) <= 3 else 150)
        T(d, (cx - tw(d, s, fn) / 2, cy - 160 if len(s) <= 3 else cy - 120), s, fn, WHITE)
        u = sc.get("unit", ""); fu = hf("SemiBold", 52); T(d, (cx - tw(d, u, fu) / 2, cy + 90), u, fu, self.acc)

    def v_chart(self, d, sc, t):
        C, levels, keys = sc["_pat"]
        labels = sc.get("labels", [])
        X0, X1, Y0, Y1, VY0, VY1 = 70, 1010, 640, 1330, 1360, 1490
        lo = min(c[2] for c in C) - 2; hi = max(c[1] for c in C) + 3
        for lv, _, _ in levels: lo, hi = min(lo, lv - 2), max(hi, lv + 3)
        N = len(C); step = (X1 - X0) / N; cw = step * 0.6
        px = lambda i: X0 + step * (i + 0.5); py = lambda p: Y1 - (p - lo) / (hi - lo) * (Y1 - Y0)
        vmax = max(c[4] for c in C)
        cues = sc["cues"]; last_cue = cues[min(len(keys), len(cues)) - 1] if keys else sc["vo_start"]
        # candles reveal: up to key point k by cue k, the rest after the last cue
        def rtime(i):
            for k, (ki, _, _) in enumerate(keys):
                if i <= ki:
                    c0 = sc["start"] + 0.2 if k == 0 else cues[min(k, len(cues) - 1)] - 0.1
                    prev = -1 if k == 0 else keys[k - 1][0]
                    span = max(ki - prev, 1); return c0 + (i - prev - 1) / span * (0.9 if k else min(1.6, cues[0] - sc["start"]))
            tail0 = last_cue + 0.6; rest = N - 1 - (keys[-1][0] if keys else -1)
            return tail0 + (i - (keys[-1][0] if keys else -1) - 1) * min(0.15, 1.2 / max(rest, 1))
        la = ease((t - sc["start"] - 0.2) / 0.6)
        for lv, name, col in levels:
            y = py(lv); x = X0
            while x < X0 + (X1 - X0) * la: d.line([(x, y), (min(x + 18, X1), y)], fill=mix(col, la), width=3); x += 30
            fs = hf("Regular", 32); nw = tw(d, name, fs)
            d.rectangle([X1 - nw - 12, y - 48, X1 + 4, y - 6], fill=BG); T(d, (X1 - nw - 4, y - 46), name, fs, mix(col, la))
        for i, (o, h, l, c, v) in enumerate(C):
            r = rtime(i)
            if t < r: continue
            g = ease((t - r) / 0.22); cc = o + (c - o) * g
            hh = max(o, cc) + (h - max(o, c)) * g; ll = min(o, cc) - (min(o, c) - l) * g
            col = UP if cc >= o else DOWN; x = px(i)
            d.line([(x, py(hh)), (x, py(ll))], fill=col, width=3)
            yt, yb = py(max(o, cc)), py(min(o, cc)); yb = max(yb, yt + 3)
            d.rectangle([x - cw / 2, yt, x + cw / 2, yb], fill=col)
            vh = (VY1 - VY0) * v / vmax * g
            d.rectangle([x - cw / 2, VY1 - vh, x + cw / 2, VY1], fill=tuple(int(k * 0.45 + BG[j] * 0.55) for j, k in enumerate(col)))
        for k, (ki, price, col) in enumerate(keys):
            if k >= len(labels) or k >= len(cues): break
            c0 = cues[k] + 0.35
            if t < c0: continue
            a = ease((t - c0) / 0.3)
            nxt = cues[k + 1] + 0.35 if (k + 1 < len(labels) and k + 1 < len(cues)) else None
            box_a = a * (1 - ease((t - nxt) / 0.25)) if nxt else a
            x = px(ki); txt = labels[k]; f = fit(d, txt, "SemiBold", 36, 560); w = tw(d, txt, f)
            if price is None:  # volume marker
                y = VY0 - 10
                d.rectangle([x - cw / 2 - 4, VY0, x + cw / 2 + 4, VY1], outline=mix(col, a), width=3)
                tx, ty = max(30, min(W - 30 - w, x - w / 2)), VY0 - 70
            else:
                y = py(price); rr = 26 * (0.6 + 0.4 * a)
                d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=mix(col, a), width=4)
                above = y > (Y0 + Y1) / 2
                tx = max(30, min(W - 30 - w, x - w / 2)); ty = (y - 110) if above else (y + 50)
            if box_a > 0.01:
                d.rounded_rectangle([tx - 16, ty - 8, tx + w + 16, ty + 52], radius=12, fill=BG, outline=mix(col, box_a * 0.7), width=2)
                T(d, (tx, ty), txt, f, mix(col, box_a))

    def v_caution(self, d, sc, t):
        items, cues = sc["items"], sc["cues"]; endc = cues[-1]
        fade = 1 - ease((t - endc) / 0.4) * 0.65
        for i, txt in enumerate(items):
            c = cues[min(i, len(cues) - 1)]
            if t < c: continue
            a0 = ease((t - c) / 0.4); a = a0 * fade
            y = 640 + i * 220; x = 70 + (1 - a0) * 120
            d.rounded_rectangle([x, y, x + 940, y + 180], radius=28, fill=mix(CARD, a), outline=mix(AMBER, a), width=3)
            tx, ty = x + 85, y + 90
            d.polygon([(tx, ty - 42), (tx - 46, ty + 36), (tx + 46, ty + 36)], fill=mix(AMBER, a))
            T(d, (tx - 6, ty - 22), "!", inter("Bold", 44), BG)
            T(d, (x + 165, y + 60), txt, fit(d, txt, "SemiBold", 48, 740), mix(WHITE, a))
        if t >= endc:
            a = ease((t - endc) / 0.5); s1 = "फ़ॉलो करें  •  शेयर करें"; fu = hf("SemiBold", 52)
            yb = 640 + len(items) * 220 + 60
            d.rounded_rectangle([170, yb, 910, yb + 110], radius=55, fill=mix(self.acc, a))
            T(d, ((W - tw(d, s1, fu)) / 2, yb + 16), s1, fu, BG)
            fs = hf("Regular", 34)
            for k, s in enumerate(self.end):
                T(d, ((W - tw(d, s, fs)) / 2, yb + 170 + k * 56), s, fs, mix(MUTED, a))

    def frame(self, t):
        im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
        for sc in self.scenes:
            last = sc is self.scenes[-1]
            if sc["start"] <= t < sc["end"] or (last and t >= sc["end"]):
                lt = t - sc["start"]; a_in = ease(lt / 0.35)
                a_out = 1 if last else 1 - ease((t - (sc["end"] - 0.25)) / 0.25)
                self.caption(d, sc["cap"], a_in * a_out, (1 - a_in) * 30)
                getattr(self, "v_" + sc["kind"])(d, sc, t)
                if a_out < 1:
                    im = Image.blend(Image.new("RGB", (W, H), BG), im, a_out); d = ImageDraw.Draw(im)
                break
        self.header(d)
        d.rectangle([0, H - 10, W * min(1, t / self.total), H], fill=self.acc)
        return im

def load(spec_path, vo_dir):
    spec = json.load(open(spec_path)); timing = json.load(open(os.path.join(vo_dir, "timing.json")))
    return Reel(spec, timing)

if __name__ == "__main__":
    # reelgen.py SPEC VO_DIR scene_index OUT.mp4   |   reelgen.py SPEC VO_DIR still T OUT.png
    spec, vo_dir, mode = sys.argv[1], sys.argv[2], sys.argv[3]
    R = load(spec, vo_dir)
    if mode == "still":
        R.frame(float(sys.argv[4])).save(sys.argv[5]); raise SystemExit
    k, out = int(mode), sys.argv[4]; sc = R.scenes[k]; tmp = out[:-4] + ".part.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    for n in range(round(sc["start"] * FPS), round(sc["end"] * FPS)):
        p.stdin.write(R.frame(n / FPS).tobytes())
    p.stdin.close()
    if p.wait() == 0: os.replace(tmp, out)
    else: sys.exit(1)
