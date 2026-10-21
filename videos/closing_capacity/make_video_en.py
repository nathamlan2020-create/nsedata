"""English 1080x1920 explainer video with Kokoro TTS voiceover: closing capacity."""
import subprocess, numpy as np, soundfile as sf
from PIL import Image, ImageDraw, ImageFont
from kokoro_onnx import Kokoro

W, H, FPS, SR = 1080, 1920, 30, 24000
VOICE, SPEED, LEAD, TAIL = "am_michael", 1.0, 0.4, 0.7

NARRATION = [
    "Here's a must-know question for F E T and NEET S S. Why does oxygenation fall in elderly patients? Let's break it down.",
    "Closing capacity is the lung volume at which the small airways in the dependent parts of the lung begin to close during expiration.",
    "Remember the formula. Closing capacity equals closing volume plus residual volume. It's measured by the single breath nitrogen washout test, where the start of phase four marks airway closure.",
    "Closing capacity rises with age, while F R C changes very little. Closing capacity equals F R C at about forty four years when supine, and at about sixty six years when standing.",
    "Once closing capacity exceeds F R C, some airways close even during normal tidal breathing. Those alveoli are perfused but not ventilated. That's shunt, so P A O two and S P O two fall. Under anaesthesia and lying supine, F R C falls further, so elderly patients desaturate faster.",
    "Follow for one high yield topic every day, and comment the topic you want next. Coming up: the oxygen dissociation curve.",
]

# ---------------------------------------------------------------- voice
k = Kokoro("tts/kokoro-v1.0.onnx", "tts/voices-v1.0.bin")
clips = []
for line in NARRATION:
    s, sr = k.create(line, voice=VOICE, speed=SPEED, lang="en-us")
    assert sr == SR
    clips.append(s.astype(np.float32))
durs = [LEAD + len(c) / SR + TAIL for c in clips]
audio = np.concatenate([np.concatenate([np.zeros(int(LEAD * SR)), c, np.zeros(int(TAIL * SR))]) for c in clips])
audio = audio / max(1e-6, np.abs(audio).max()) * 0.9
sf.write("voice_en.wav", audio, SR)
print("scene durations:", [round(d, 1) for d in durs], "total", round(sum(durs), 1))

# ---------------------------------------------------------------- drawing helpers
FONT = "dev.ttf"
_cache = {}
def F(size, wght=700):
    key = (size, wght)
    if key not in _cache:
        f = ImageFont.truetype(FONT, size, layout_engine=ImageFont.Layout.RAQM)
        f.set_variation_by_axes([wght, 100]); _cache[key] = f
    return _cache[key]
BG, FG, MUTED, ACC, ACC2, RED, GRID, GREEN, CARD = (14, 23, 38), (245, 247, 250), (160, 172, 190), (64, 196, 255), (255, 196, 64), (255, 92, 92), (40, 54, 76), (120, 220, 160), (24, 38, 60)

def wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines
def block(d, y, text, size, color=FG, wght=700, maxw=920, gap=1.3):
    f = F(size, wght)
    for line in wrap(d, text, f, maxw):
        d.text(((W - d.textlength(line, font=f)) / 2, y), line, font=f, fill=color); y += int(size * gap)
    return y
def ease(t):
    t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)
def base(progress):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 14], fill=GRID); d.rectangle([0, 0, int(W * progress), 14], fill=ACC)
    d.text((80, 60), "Anaesthesia Physiology · Quick revision", font=F(34, 500), fill=MUTED)
    return im, d

# ---------------------------------------------------------------- scenes: painter(d, t, dur)
def s_hook(d, t, T):
    block(d, 440, "MUST-KNOW FOR FET / NEET-SS", 54, ACC2)
    y = block(d, 640, "Why does oxygenation fall in the elderly?", 100)
    if t > T * 0.55: block(d, y + 80, "Let's break it down", 60, MUTED, 500)

def s_def(d, t, T):
    block(d, 330, "Closing capacity (CC)", 88, ACC)
    block(d, 560, "The lung volume at which small airways in dependent lung begin to close during expiration", 64)
    k = ease(t / (T * 0.8)); cx, cy = W // 2, 1320; gap = 70 * (1 - k) + 6
    d.rounded_rectangle([cx - 300, cy - 70, cx + 300, cy + 70], radius=70, outline=MUTED, width=6)
    d.rectangle([cx - 290, cy - gap, cx + 290, cy + gap], fill=(30, 80, 120))
    block(d, cy + 140, "Small airway narrowing and closing on expiration", 46, MUTED, 500)

def s_formula(d, t, T):
    block(d, 380, "Remember the formula", 64, MUTED, 500)
    f = F(150, 800); txt = "CC = CV + RV"
    d.text(((W - d.textlength(txt, font=f)) / 2, 640), txt, font=f, fill=ACC2)
    if t > T * 0.25:
        block(d, 960, "CV = closing volume", 60); block(d, 1060, "RV = residual volume", 60)
    if t > T * 0.55:
        block(d, 1300, "Measured by single-breath nitrogen washout: start of phase 4 = airway closure", 46, MUTED, 500)

def s_chart(d, t, T):
    block(d, 200, "CC rises with age", 76)
    x0, x1, y0, y1 = 150, 990, 1450, 520; a0, a1, v0, v1 = 20, 80, 1.2, 3.1
    X = lambda a: x0 + (a - a0) / (a1 - a0) * (x1 - x0); Y = lambda v: y0 - (v - v0) / (v1 - v0) * (y0 - y1)
    for a in range(20, 81, 10):
        d.line([X(a), y1, X(a), y0], fill=GRID, width=2)
        lab = str(a); d.text((X(a) - d.textlength(lab, font=F(34, 500)) / 2, y0 + 16), lab, font=F(34, 500), fill=MUTED)
    d.line([x0, y0, x1, y0], fill=MUTED, width=4); d.line([x0, y0, x0, y1], fill=MUTED, width=4)
    d.text((x1 - 190, y0 + 64), "Age (years)", font=F(36, 500), fill=MUTED)
    d.text((x0 - 10, y1 - 70), "Lung volume", font=F(36, 500), fill=MUTED)
    frc_st, frc_su = 2.6, 2.0
    cc = lambda a: frc_su + (a - 44) * (frc_st - frc_su) / (66 - 44)
    d.line([X(a0), Y(frc_st), X(a1), Y(frc_st)], fill=GREEN, width=8)
    d.text((X(21), Y(frc_st) - 60), "FRC (standing)", font=F(38, 700), fill=GREEN)
    d.line([X(a0), Y(frc_su), X(a1), Y(frc_su)], fill=ACC, width=8)
    d.text((X(21), Y(frc_su) + 14), "FRC (supine)", font=F(38, 700), fill=ACC)
    aend = a0 + (a1 - a0) * ease(t / (T * 0.85))
    pts = [(X(a), Y(cc(a))) for a in [a0 + i * (aend - a0) / 60 for i in range(61)]]
    d.line(pts, fill=ACC2, width=10, joint="curve")
    d.text((pts[-1][0] - 90, pts[-1][1] - 70), "CC", font=F(48, 800), fill=ACC2)
    for age, v, lab in ((44, frc_su, "~44 yrs (supine)"), (66, frc_st, "~66 yrs (standing)")):
        if aend >= age:
            d.ellipse([X(age) - 16, Y(v) - 16, X(age) + 16, Y(v) + 16], fill=RED)
            d.text((X(age) + 24, Y(v) + 20) if age == 44 else (X(age) - 340, Y(v) - 80), lab, font=F(36, 700), fill=RED)
    block(d, 1600, "At these ages CC = FRC", 56)
    d.text((80, 1780), "Schematic, not to scale", font=F(30, 500), fill=MUTED)

def s_effect(d, t, T):
    block(d, 300, "When CC > FRC", 92, ACC2)
    steps = ["Airways close even during normal tidal breathing", "Perfused but not ventilated alveoli = shunt", "PaO2 and SpO2 fall"]
    y = 600
    for i, s in enumerate(steps):
        if t > T * (0.03 + 0.2 * i):
            d.rounded_rectangle([90, y - 20, W - 90, y + 200], radius=36, fill=CARD)
            block(d, y + 20, s, 54)
            if i < 2: d.polygon([(W / 2 - 30, y + 225), (W / 2 + 30, y + 225), (W / 2, y + 270)], fill=MUTED)
        y += 300
    if t > T * 0.65:
        block(d, 1560, "Anaesthesia and supine position reduce FRC further, so the elderly desaturate faster", 44, MUTED, 500)

def s_cta(d, t, T):
    block(d, 520, "One topic a day", 104, ACC)
    block(d, 720, "Follow for FET / NEET-SS prep", 64)
    block(d, 1000, "Comment the topic you want next", 58, ACC2)
    block(d, 1300, "Next: oxygen dissociation curve", 52, MUTED, 500)

PAINTERS = [s_hook, s_def, s_formula, s_chart, s_effect, s_cta]
starts = np.concatenate([[0], np.cumsum(durs)]); TOTAL = starts[-1]
p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                      "-i", "voice_en.wav", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                      "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", "closing_capacity_english.mp4"], stdin=subprocess.PIPE)
blank = Image.new("RGB", (W, H), BG)
for n in range(int(TOTAL * FPS)):
    sec = n / FPS
    i = min(int(np.searchsorted(starts, sec, side="right") - 1), len(PAINTERS) - 1)
    a, b = starts[i], starts[i + 1]
    im, d = base(sec / TOTAL); PAINTERS[i](d, sec - a, b - a)
    alpha = min(1, (sec - a) / 0.35, (b - sec) / 0.35)
    p.stdin.write((im if alpha >= 1 else Image.blend(blank, im, max(0, alpha))).tobytes())
    if abs(sec - (a + (b - a) * 0.9)) < 0.5 / FPS: im.save(f"en_prev_{i}.png")
p.stdin.close(); p.wait(); print("done", p.returncode)
