"""Vertical 1080x1920 explainer video: closing capacity (Hindi), ~60 s, no voice."""
import subprocess, math
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
FONT = "dev.ttf"
def F(size, wght=700):
    f = ImageFont.truetype(FONT, size, layout_engine=ImageFont.Layout.RAQM)
    try:
        f.set_variation_by_axes([wght, 100])
    except Exception:
        pass
    return f

BG, FG, MUTED, ACC, ACC2, RED, GRID = (14, 23, 38), (245, 247, 250), (160, 172, 190), (64, 196, 255), (255, 196, 64), (255, 92, 92), (40, 54, 76)

def wrap(d, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines

def block(d, y, text, size, color=FG, wght=700, maxw=920, gap=1.35, align="center"):
    f = F(size, wght)
    for line in wrap(d, text, f, maxw):
        w = d.textlength(line, font=f)
        x = (W - w) / 2 if align == "center" else 80
        d.text((x, y), line, font=f, fill=color)
        y += int(size * gap)
    return y

def ease(t):
    t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)

def base(progress):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 14], fill=GRID)
    d.rectangle([0, 0, int(W * progress), 14], fill=ACC)
    d.text((80, 60), "Anaesthesia Physiology · 1 मिनट", font=F(34, 500), fill=MUTED)
    return im, d

def fade(im, a):
    if a >= 1:
        return im
    return Image.blend(Image.new("RGB", (W, H), BG), im, max(0, a))

# ---------------------------------------------------------------- scenes (start, end, painter)
def s_hook(d, t):
    block(d, 420, "FET / NEET-SS का पक्का सवाल", 58, ACC2)
    y = block(d, 620, "बुज़ुर्गों में ऑक्सीजन क्यों गिरती है?", 96)
    if t > 1.5:
        block(d, y + 80, "एक मिनट में समझिए", 60, MUTED, 500)

def s_def(d, t):
    block(d, 330, "क्लोज़िंग कैपेसिटी (CC)", 84, ACC)
    block(d, 560, "वह लंग वॉल्यूम, जिस पर फेफड़ों के नीचे की छोटी एयरवेज़ बंद होने लगती हैं", 66)
    # small airway icon: closing tube
    k = ease(t / 4)
    cx, cy = W // 2, 1300
    gap = 70 * (1 - k) + 6
    d.rounded_rectangle([cx - 300, cy - 70, cx + 300, cy + 70], radius=70, outline=MUTED, width=6)
    d.rectangle([cx - 290, cy - gap, cx + 290, cy + gap], fill=(30, 80, 120))
    block(d, cy + 140, "साँस छोड़ते-छोड़ते छोटी एयरवेज़ सिकुड़कर बंद", 46, MUTED, 500)

def s_formula(d, t):
    block(d, 380, "फ़ॉर्मूला याद रखें", 64, MUTED, 500)
    f = F(150, 800)
    txt = "CC = CV + RV"
    w = d.textlength(txt, font=f)
    d.text(((W - w) / 2, 640), txt, font=f, fill=ACC2)
    if t > 1.2:
        block(d, 960, "CV = क्लोज़िंग वॉल्यूम", 58)
        block(d, 1060, "RV = रेज़िडुअल वॉल्यूम", 58)
    if t > 3:
        block(d, 1300, "नापने का तरीका: सिंगल-ब्रेथ नाइट्रोजन वॉशआउट (फ़ेज़ 4)", 46, MUTED, 500)

def s_chart(d, t):
    block(d, 200, "उम्र के साथ CC बढ़ती है", 72, FG)
    # axes
    x0, x1, y0, y1 = 150, 990, 1450, 520            # pixel box
    a0, a1, v0, v1 = 20, 80, 1.2, 3.1               # age, litres (schematic)
    X = lambda a: x0 + (a - a0) / (a1 - a0) * (x1 - x0)
    Y = lambda v: y0 - (v - v0) / (v1 - v0) * (y0 - y1)
    for a in range(20, 81, 10):
        d.line([X(a), y1, X(a), y0], fill=GRID, width=2)
        lab = str(a); fw = d.textlength(lab, font=F(34, 500))
        d.text((X(a) - fw / 2, y0 + 16), lab, font=F(34, 500), fill=MUTED)
    d.line([x0, y0, x1, y0], fill=MUTED, width=4); d.line([x0, y0, x0, y1], fill=MUTED, width=4)
    d.text((x1 - 210, y0 + 64), "उम्र (साल)", font=F(36, 500), fill=MUTED)
    d.text((x0 - 10, y1 - 70), "लंग वॉल्यूम", font=F(36, 500), fill=MUTED)
    frc_st, frc_su = 2.6, 2.0
    cc = lambda a: frc_su + (a - 44) * (frc_st - frc_su) / (66 - 44)
    k = ease(t / 5)                                   # draw CC progressively
    d.line([X(a0), Y(frc_st), X(a1), Y(frc_st)], fill=(120, 220, 160), width=8)
    d.text((X(21), Y(frc_st) - 60), "FRC (खड़े)", font=F(38, 700), fill=(120, 220, 160))
    d.line([X(a0), Y(frc_su), X(a1), Y(frc_su)], fill=ACC, width=8)
    d.text((X(21), Y(frc_su) + 14), "FRC (लेटे)", font=F(38, 700), fill=ACC)
    aend = a0 + (a1 - a0) * k
    pts = [(X(a), Y(cc(a))) for a in [a0 + i * (aend - a0) / 60 for i in range(61)]]
    d.line(pts, fill=ACC2, width=10, joint="curve")
    d.text((pts[-1][0] - 90, pts[-1][1] - 70), "CC", font=F(48, 800), fill=ACC2)
    for age, v, lab in ((44, frc_su, "~44 साल (लेटे)"), (66, frc_st, "~66 साल (खड़े)")):
        if aend >= age:
            d.ellipse([X(age) - 16, Y(v) - 16, X(age) + 16, Y(v) + 16], fill=RED)
            d.text((X(age) + 24, Y(v) + 20) if age == 44 else (X(age) - 300, Y(v) - 80), lab, font=F(36, 700), fill=RED)
    block(d, 1600, "इन उम्र पर CC = FRC हो जाती है", 54)
    d.text((80, 1780), "चित्र सांकेतिक है", font=F(30, 500), fill=MUTED)

def s_effect(d, t):
    block(d, 300, "जब CC > FRC", 90, ACC2)
    steps = ["सामान्य साँस में भी कुछ एयरवेज़ बंद", "बंद एल्वियोलाई में ऑक्सीजन नहीं, इसलिए शंट", "SpO2 और PaO2 गिरते हैं"]
    y = 600
    for i, s in enumerate(steps):
        if t > i * 1.6:
            d.rounded_rectangle([90, y - 20, W - 90, y + 200], radius=36, fill=(24, 38, 60))
            block(d, y + 20, s, 54)
            if i < 2:
                d.polygon([(W / 2 - 30, y + 225), (W / 2 + 30, y + 225), (W / 2, y + 270)], fill=MUTED)
        y += 300
    if t > 5:
        block(d, 1560, "एनेस्थीसिया और लेटने पर FRC और घटती है, इसलिए बुज़ुर्गों में जल्दी डीसैचुरेशन", 44, MUTED, 500)

def s_cta(d, t):
    block(d, 520, "रोज़ एक टॉपिक", 100, ACC)
    block(d, 720, "FET / NEET-SS के लिए फ़ॉलो कीजिए", 62)
    block(d, 1000, "कमेंट में बताइए: अगला टॉपिक क्या हो?", 56, ACC2)
    block(d, 1300, "अगला: ऑक्सीजन डिसोसिएशन कर्व", 50, MUTED, 500)

SCENES = [(0, 8, s_hook), (8, 18, s_def), (18, 27, s_formula), (27, 41, s_chart), (41, 53, s_effect), (53, 60, s_cta)]
TOTAL = SCENES[-1][1]

p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                      "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-shortest",
                      "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
                      "-movflags", "+faststart", "closing_capacity_hindi.mp4"], stdin=subprocess.PIPE)
for n in range(TOTAL * FPS):
    sec = n / FPS
    for a, b, fn in SCENES:
        if a <= sec < b:
            im, d = base(sec / TOTAL); fn(d, sec - a)
            alpha = min(1, (sec - a) / 0.4, (b - sec) / 0.4)
            p.stdin.write(fade(im, alpha).tobytes())
            if n % (FPS * 10) == 0:
                fade(im, 1).save(f"preview_{int(sec):02d}.png")
            break
p.stdin.close(); p.wait()
print("done", p.returncode)
