"""Operating-theatre background for SurgerySaathi 'ot' layout (1080 x 1480 area, drawn under the header).
static_bg() -> RGB image (cached); dynamic(im, d, t, oy) draws the animated parts (monitor waves, lap screen, light glow).
Coordinates are frame coordinates (header ends at y=200)."""
import math
from PIL import Image, ImageDraw, ImageFilter, ImageFont
W, H = 1080, 1920
DARK = (25, 45, 30)
_bg = None

def _font(path, s): return ImageFont.truetype(path, s)

def static_bg(font_path):
    global _bg
    if _bg is not None: return _bg
    im = Image.new("RGB", (W, H), (200, 228, 214)); d = ImageDraw.Draw(im)
    # walls: vertical gradient teal-green
    for y in range(200, 1300):
        p = (y - 200) / 1100
        d.line([0, y, W, y], fill=(int(150 + 40 * p), int(205 + 15 * p), int(190 + 15 * p)))
    # wall panels
    for x in range(0, W, 270):
        d.rectangle([x + 8, 230, x + 262, 1270], outline=(135, 190, 172), width=4)
    # floor
    for y in range(1300, 1680):
        p = (y - 1300) / 380
        d.line([0, y, W, y], fill=(int(120 - 20 * p), int(170 - 20 * p), int(160 - 20 * p)))
    for x in range(-600, W + 600, 120):
        d.line([W / 2 + (x - W / 2) * 0.35, 1300, x, 1680], fill=(105, 152, 142), width=3)
    for y in (1340, 1400, 1480, 1580):
        d.line([0, y, W, y], fill=(105, 152, 142), width=3)
    d.line([0, 1300, W, 1300], fill=(90, 140, 128), width=6)
    # ---- laparoscopy tower (right) : cart + stacked units + screen on top
    cx0, cx1 = 820, 1060
    d.rounded_rectangle([cx0, 520, cx1, 1290], radius=14, fill=(225, 230, 235), outline=(110, 120, 130), width=5)
    units = [("INSUFFLATOR", (40, 60, 80)), ("LIGHT SOURCE", (40, 60, 80)), ("CAMERA", (40, 60, 80)), ("SUCTION", (40, 60, 80))]
    fs = _font(font_path, 18)
    for i, (lab, col) in enumerate(units):
        y = 560 + i * 150
        d.rounded_rectangle([cx0 + 18, y, cx1 - 18, y + 120], radius=10, fill=(245, 247, 250), outline=(140, 150, 160), width=3)
        d.text((cx0 + 32, y + 20), lab, font=fs, fill=(70, 80, 95))
        d.rounded_rectangle([cx0 + 30, y + 50, cx0 + 140, y + 100], radius=6, fill=(20, 30, 35))
        for k in range(3): d.ellipse([cx0 + 160 + k * 24, y + 64, cx0 + 178 + k * 24, y + 82], fill=(90, 100, 110))
    d.rectangle([cx0 + 20, 1290, cx0 + 40, 1330], fill=(90, 95, 100)); d.rectangle([cx1 - 40, 1290, cx1 - 20, 1330], fill=(90, 95, 100))
    d.ellipse([cx0 + 12, 1320, cx0 + 48, 1350], fill=(50, 55, 60)); d.ellipse([cx1 - 48, 1320, cx1 - 12, 1350], fill=(50, 55, 60))
    # lap screen frame (content drawn dynamically)
    d.rectangle([cx0 + 110, 470, cx0 + 130, 520], fill=(120, 125, 130))
    d.rounded_rectangle([cx0 - 30, 300, cx1 + 10, 480], radius=12, fill=(30, 35, 40), outline=(90, 95, 100), width=6)
    # ---- monitor (left) on a wall arm
    d.rectangle([20, 290, 40, 330], fill=(120, 125, 130)); d.line([30, 310, 70, 310], fill=(120, 125, 130), width=14)
    d.rounded_rectangle([40, 250, 330, 480], radius=14, fill=(40, 45, 50), outline=(100, 105, 110), width=6)
    # ---- OT light (ceiling, centre)
    d.line([540, 200, 540, 240], fill=(160, 170, 175), width=22)
    d.line([540, 240, 620, 270], fill=(160, 170, 175), width=18)
    d.ellipse([400, 250, 700, 400], fill=(215, 222, 226), outline=(120, 130, 135), width=6)
    # ---- OT table (foreground) : drawn in table_front()
    _bg = im
    return im

def glow(im, t):
    """soft light cone under the OT lamp"""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    a = int(55 + 8 * math.sin(t * 1.3))
    d.polygon([(430, 380), (670, 380), (900, 1260), (180, 1260)], fill=(255, 250, 215, a))
    lay = lay.filter(ImageFilter.GaussianBlur(40))
    im.paste(lay, (0, 0), lay)

def lamp(d):
    for (x, y) in [(470, 300), (550, 290), (630, 300), (500, 345), (600, 345)]:
        d.ellipse([x - 26, y - 20, x + 26, y + 20], fill=(255, 248, 200), outline=(200, 190, 140), width=3)
    d.ellipse([530, 310, 570, 345], fill=(150, 160, 165))

def ecg(ph):
    ph = ph % 1.0
    if ph < 0.1: return 0.15 * math.sin(ph / 0.1 * math.pi)
    if 0.18 < ph < 0.2: return -0.2
    if 0.2 <= ph < 0.23: return 1.0
    if 0.23 <= ph < 0.26: return -0.35
    if 0.4 < ph < 0.55: return 0.3 * math.sin((ph - 0.4) / 0.15 * math.pi)
    return 0

def monitor(d, t, font_path, hr=76):
    x0, y0, x1, y1 = 52, 262, 318, 468
    d.rectangle([x0, y0, x1, y1], fill=(8, 14, 12))
    sx0, sx1 = x0 + 8, x0 + 170; sweep = (t * 0.45) % 1.0; xs = sx0 + (sx1 - sx0) * sweep
    pts = []; pts2 = []
    for k in range(0, sx1 - sx0, 3):
        x = sx0 + k
        back = (xs - x) / (sx1 - sx0) if x <= xs else (xs - x) / (sx1 - sx0) + 1
        tt = t - back / 0.45; ph = tt * hr / 60
        pts.append((x, 318 - 40 * ecg(ph)))
        p2 = ph % 1; pts2.append((x, 410 - 30 * ((p2 / 0.18) if p2 < 0.18 else math.exp(-(p2 - 0.18) * 4.5))))
    d.line(pts, fill=(60, 235, 110), width=3); d.line(pts2, fill=(80, 190, 255), width=3)
    d.rectangle([xs, y0 + 10, xs + 8, y1 - 10], fill=(8, 14, 12))
    f1 = _font(font_path, 20); f2 = _font(font_path, 38); f3 = _font(font_path, 28)
    d.text((x0 + 186, y0 + 8), "HR", font=f1, fill=(60, 235, 110)); d.text((x0 + 186, y0 + 26), f"{hr + int(2 * math.sin(t * 0.7))}", font=f2, fill=(60, 235, 110))
    d.text((x0 + 186, y0 + 78), "SpO2", font=f1, fill=(80, 190, 255)); d.text((x0 + 186, y0 + 96), "99%", font=f2, fill=(80, 190, 255))
    d.text((x0 + 10, y0 + 152), "NIBP 118/76", font=f3, fill=(255, 210, 80))
    d.text((x0 + 186, y0 + 150), "RR 14", font=f1, fill=(255, 255, 255))
    d.text((x0 + 10, y0 + 6), "II", font=f1, fill=(60, 235, 110))

def lapscreen(d, t, font_path):
    x0, y0, x1, y1 = 800, 312, 1058, 468
    d.rectangle([x0, y0, x1, y1], fill=(60, 10, 15))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for r, c in [(70, (150, 40, 50)), (52, (190, 70, 80)), (34, (225, 120, 120))]:
        d.ellipse([cx - r * 1.6 + 6 * math.sin(t * 0.8), cy - r, cx + r * 1.6 + 6 * math.sin(t * 0.8), cy + r], fill=c)
    d.line([cx + 20, y1, cx + 60 + 8 * math.sin(t), cy + 10], fill=(200, 205, 210), width=8)
    d.text((x0 + 8, y0 + 4), "LAP CAM", font=_font(font_path, 18), fill=(255, 255, 255))
    d.text((x1 - 8, y0 + 4), "CO2 12", font=_font(font_path, 18), fill=(120, 255, 160), anchor="ra")

def table_front(d):
    # mattress (patient sits/lies on it), steel side rail, column base
    d.rounded_rectangle([70, 1365, 1010, 1440], radius=26, fill=(40, 95, 110), outline=(20, 55, 65), width=5)
    d.rectangle([80, 1435, 1000, 1465], fill=(185, 192, 198), outline=(120, 128, 135), width=3)
    d.rectangle([470, 1465, 610, 1620], fill=(170, 178, 185), outline=(110, 118, 125), width=4)
    d.rounded_rectangle([330, 1615, 750, 1665], radius=14, fill=(150, 158, 165), outline=(100, 108, 115), width=4)
    d.ellipse([500, 1382, 580, 1422], fill=(55, 115, 130))
