"""SurgerySaathi compilation (16:9) from finished Shorts.
Usage: python3 comp_make.py comp_spec.json OUTDIR
comp_spec: {slug, lang, title, subtitle, intro_vo, outro_vo:[[text,pause],...], clips:[{mp4, q}], youtube}
Each Short is placed at the left over a blurred copy of itself, with a side panel "SAWAAL i/n" + question.
End cards of every Short except the last are trimmed. Prints chapter timestamps.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, soundfile as sf
from PIL import Image, ImageDraw
import ss_make as S

W, H = 1920, 1080
TX = {"hi": dict(q="SAWAAL {i}/{n}", ai="AI character · sirf jaankari ke liye", tag="Darr nahi, taiyaari!", ask="Apna sawaal comment mein likhiye!"),
      "bn": dict(q="প্রশ্ন {i}/{n}", ai="AI চরিত্র · শুধু জানার জন্য", tag="ভয় নয়, প্রস্তুতি!", ask="আপনার প্রশ্ন কমেন্টে লিখুন!")}
def run(*a): subprocess.run(a, check=True)
def dur(f): return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f], capture_output=True, text=True).stdout)

def endcard_start(mp4):
    """first time (s) in the last 7 s where the frame centre turns into the light end card"""
    D = dur(mp4); st = max(0, D - 7)
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{st}", "-i", mp4, "-vf", "fps=10,scale=54:96", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 96, 54, 3)
    for i, f in enumerate(fr):
        c = f[40:60, 5:15].reshape(-1, 3).mean(0)   # left-middle patch: wall in OT, light green on end card
        if abs(c[0] - 232) < 18 and abs(c[1] - 245) < 14 and abs(c[2] - 236) < 18: return st + i / 10 - 0.25
    return D

def still(img, wav, out, d):
    img.save(out + ".png")
    run("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", out + ".png", "-i", wav, "-t", f"{d:.2f}",
        "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k", out)

def card(spec, title, sub, cast_left, cast_right):
    P = S.P; im = Image.new("RGB", (W, H), S.GREEN); d = ImageDraw.Draw(im)
    for r in range(0, 1400, 70): d.ellipse([W / 2 - r, H / 2 - r, W / 2 + r, H / 2 + r], outline=(24, 95, 50), width=3)
    if cast_left: c = S.cast(cast_left, 620); im.paste(c, (40, H - c.height), c)
    if cast_right: c = S.cast(cast_right, 620); im.paste(c, (W - 40 - c.width, H - c.height), c)
    for i, l in enumerate(S.wrap(d, title, P(84), 1100)[:2]): d.text((W / 2, 260 + i * 100), l, font=P(84), fill="white", anchor="mm")
    d.text((W / 2, 500), sub, font=P(46), fill=(255, 210, 80), anchor="mm")
    d.text((W / 2, 40 + 20), "SurgerySaathi", font=S.LATIN(40), fill="white", anchor="mm")
    return im

def main(spec, outdir):
    os.makedirs(outdir, exist_ok=True); L = spec.get("lang", "hi"); S.LANG = L; T = TX[L]; P = S.P
    tmp = os.path.join(outdir, "parts"); os.makedirs(tmp, exist_ok=True); parts = []; chapters = []; t = 0.0
    # intro
    a, sr, _ = S.say_role("dr", [[spec["intro_vo"], 0.1]]); a = np.concatenate([np.zeros(int(0.4 * sr), np.float32), a, np.zeros(int(0.8 * sr), np.float32)])
    sf.write(tmp + "/intro.wav", a, sr); di = len(a) / sr
    still(card(spec, spec["title"], spec["subtitle"], "uncle_worried", "dr_happy"), tmp + "/intro.wav", tmp + "/p00.mp4", di)
    parts.append(tmp + "/p00.mp4"); chapters.append(("00:00", "Shuruaat" if L == "hi" else "শুরু")); t += dur(tmp + "/p00.mp4")
    n = len(spec["clips"])
    for i, c in enumerate(spec["clips"]):
        mp4 = c["mp4"]; end = dur(mp4) if i == n - 1 else endcard_start(mp4)
        pan = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(pan)
        d.rounded_rectangle([900, 250, 1840, 830], radius=36, fill=(16, 70, 36, 235), outline="white", width=5)
        d.text((960, 310), T["q"].format(i=i + 1, n=n), font=S.LATIN(52) if L == "hi" else P(52), fill=(255, 210, 80))
        for j, l in enumerate(S.wrap(d, c["q"], P(70), 820)[:3]): d.text((960, 410 + j * 90), l, font=P(70), fill="white")
        d.text((960, 760), "SurgerySaathi · " + S.SITE_HANDLE, font=S.LATIN(34), fill=(200, 230, 210))
        pan.save(f"{tmp}/pan{i}.png")
        out = f"{tmp}/p{i + 1:02d}.mp4"
        run("ffmpeg", "-y", "-loglevel", "error", "-i", mp4, "-i", f"{tmp}/pan{i}.png", "-t", f"{end:.2f}", "-filter_complex",
            "[0:v]split[a][b];[a]scale=1920:-2,crop=1920:1080,boxblur=24:3,eq=brightness=-0.12[bg];[b]scale=-2:1080[fg];"
            "[bg][fg]overlay=180:0[v1];[v1][1:v]overlay=0:0,fps=30,format=yuv420p[v]",
            "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k", out)
        parts.append(out); chapters.append((f"{int(t // 60):02d}:{int(t % 60):02d}", c["q"])); t += dur(out)
    # outro
    a, sr, _ = S.say_role("dr", spec["outro_vo"]); a = np.concatenate([np.zeros(int(0.3 * sr), np.float32), a, np.zeros(int(1.5 * sr), np.float32)])
    sf.write(tmp + "/outro.wav", a, sr)
    im = card(spec, "SurgerySaathi", T["tag"], "dr_happy", "uncle_thankful"); d = ImageDraw.Draw(im)
    d.rounded_rectangle([W / 2 - 200, 580, W / 2 + 200, 680], radius=50, fill=S.RED); d.text((W / 2, 630), "SUBSCRIBE", font=S.LATIN(48), fill="white", anchor="mm")
    d.text((W / 2, 740), S.SITE_HANDLE, font=S.LATIN(46), fill="white", anchor="mm"); d.text((W / 2, 830), T["ask"], font=P(44), fill="white", anchor="mm")
    d.text((W / 2, 1040), T["ai"], font=P(28), fill=(200, 230, 210), anchor="mm")
    still(im, tmp + "/outro.wav", tmp + "/p99.mp4", len(a) / sr); parts.append(tmp + "/p99.mp4")
    lst = tmp + "/list.txt"; open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    final = os.path.join(outdir, spec["slug"] + ".mp4")
    run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-movflags", "+faststart", final)
    card(spec, spec["title"], spec["subtitle"], "uncle_worried", "dr_happy").resize((1280, 720)).save(os.path.join(outdir, spec["slug"] + "_thumb.jpg"), quality=90)
    # check sheet
    D = dur(final); fr = []
    for k in range(9):
        x = D * (k + 0.5) / 9
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{x}", "-i", final, "-frames:v", "1", "-vf", "scale=640:360", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        fr.append(Image.frombytes("RGB", (640, 360), raw))
    sh = Image.new("RGB", (1920, 1080)); [sh.paste(f, ((k % 3) * 640, (k // 3) * 360)) for k, f in enumerate(fr)]
    sh.save(os.path.join(outdir, spec["slug"] + "_check.jpg"), quality=85)
    print(json.dumps(dict(ok=True, mp4=final, seconds=round(D, 1), chapters=chapters), ensure_ascii=False))

if __name__ == "__main__":
    main(json.load(open(sys.argv[1])), sys.argv[2])
