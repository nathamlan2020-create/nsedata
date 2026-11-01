"""Batch-build Reels.  python3 make.py SPECS_DIR OUT_DIR [--jobs 3]
SPECS_DIR holds one JSON spec per video (see reelgen.py). Prints a JSON summary.
Needs: pip install kokoro-onnx soundfile ; Kokoro model in $KOKORO_DIR (downloaded if missing)."""
import sys, os, json, glob, subprocess, urllib.request, shutil
from concurrent.futures import ThreadPoolExecutor
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
KD = os.environ.get("KOKORO_DIR", os.path.expanduser("~/kokoro"))
REL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
SR = 44100
KINDS = {"hook", "steps", "counter", "zones", "chart", "caution"}
PATTERNS = {"breakout", "fakeout", "retest", "pullback", "downtrend", "range", "trail"}
NKEYS = {"breakout": 3, "fakeout": 3, "retest": 3, "pullback": 3, "downtrend": 3, "range": 2, "trail": 3}

def validate(sp):
    e = []
    if sp.get("theme") not in ("health", "trading"): e.append("theme must be health or trading")
    sc = sp.get("scenes") or []
    if not sc or sc[0]["kind"] != "hook": e.append("first scene must be hook")
    if not sc or sc[-1]["kind"] != "caution": e.append("last scene must be caution")
    for i, s in enumerate(sc):
        k = s.get("kind")
        if k not in KINDS: e.append(f"scene {i}: bad kind {k}"); continue
        if not s.get("vo"): e.append(f"scene {i}: no vo")
        if any(ch.isascii() and ch.isalpha() for ph in s.get("vo", []) for ch in ph): e.append(f"scene {i}: vo has Latin letters (write in Devanagari)")
        if k in ("steps", "zones") and len(s["vo"]) < len(s.get("items", [])): e.append(f"scene {i}: need one vo phrase per item")
        if k == "caution" and len(s["vo"]) != len(s.get("items", [])) + 1: e.append(f"scene {i}: caution needs one vo per item + follow line")
        if k == "chart":
            if s.get("pattern") not in PATTERNS: e.append(f"scene {i}: bad pattern")
            elif len(s.get("labels", [])) > NKEYS[s["pattern"]]: e.append(f"scene {i}: max {NKEYS[s['pattern']]} labels for {s['pattern']}")
        if k == "counter" and not isinstance(s.get("to"), (int, float)): e.append(f"scene {i}: counter needs numeric 'to'")
    return e

def ensure_model():
    os.makedirs(KD, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = os.path.join(KD, f)
        if not os.path.exists(p) or os.path.getsize(p) < 1e6:
            subprocess.run(["curl", "-sSL", "-m", "900", "-o", p, REL + f], check=True)

def voice_all(jobs):
    from kokoro_onnx import Kokoro
    import soundfile as sf
    sys.path.insert(0, HERE); from reelgen import THEMES
    k = Kokoro(os.path.join(KD, "kokoro-v1.0.onnx"), os.path.join(KD, "voices-v1.0.bin"))
    for sp, vd in jobs:
        os.makedirs(vd, exist_ok=True); voice = sp.get("voice") or THEMES[sp["theme"]]["voice"]; timing = []
        for si, sc in enumerate(sp["scenes"]):
            parts, offs, pos, sr = [], [], 0.0, 24000
            for pi, ph in enumerate(sc["vo"]):
                spd = 1.04 if (si == 0 and pi == 0) else (0.93 if sc["kind"] == "caution" and pi == 0 else 0.98)
                a, sr = k.create(ph, voice=voice, speed=spd, lang="hi")
                offs.append(pos); parts.append(a); pos += len(a) / sr
                if pi < len(sc["vo"]) - 1: parts.append(np.zeros(int(sr * 0.32))); pos += 0.32
            sf.write(f"{vd}/s{si}.wav", np.concatenate(parts), sr); timing.append(dict(dur=pos, offs=offs))
        json.dump(timing, open(f"{vd}/timing.json", "w"))

def music_mix(R, vd, out_wav):
    import soundfile as sf
    T = R.total; n = int(SR * T); t = np.arange(n) / SR
    trading = R.s["theme"] == "trading"
    chords = ([[220, 261.6, 329.6], [174.6, 220, 261.6], [196, 261.6, 329.6], [196, 246.9, 293.7]] if trading else
              [[261.6, 329.6, 392.0], [246.9, 293.7, 392.0], [220.0, 261.6, 329.6], [174.6, 220.0, 261.6]])
    mus = np.zeros(n); seg = 2.4 if trading else 3.2; k = 0; a0 = 0.0
    while a0 < T:
        a = int(a0 * SR); b = min(n, int((a0 + seg) * SR)); tt = t[a:b] - t[a]
        env = np.minimum(1, tt / 0.7) * np.minimum(1, (seg - tt) / 0.7)
        for f in chords[k % 4]: mus[a:b] += env * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(2 * np.pi * f * 2.004 * tt))
        k += 1; a0 += seg
    if trading:
        for bt in np.arange(0, T, 0.6):
            a = int(bt * SR); L = min(int(0.25 * SR), n - a); tt = np.arange(L) / SR
            mus[a:a + L] += 3 * np.exp(-tt * 18) * np.sin(2 * np.pi * (55 + 60 * np.exp(-tt * 30)) * tt)
    sfx = np.zeros(n)
    def blip(t0, f, amp, dec):
        a = int(t0 * SR); L = min(int(0.35 * SR), n - a)
        if L > 0: tt = np.arange(L) / SR; sfx[a:a + L] += amp * np.exp(-tt * dec) * np.sin(2 * np.pi * f * tt)
    for sc in R.scenes:
        blip(sc["start"] + 0.05, 660, 0.12, 14)
        if sc["kind"] in ("steps", "zones", "caution", "chart"):
            for c in sc["cues"]: blip(c, 990, 0.14, 16); blip(c + 0.05, 1480, 0.07, 18)
    mus /= np.abs(mus).max(); sfx /= max(np.abs(sfx).max(), 1e-9)
    voice = np.zeros(n)
    for si, sc in enumerate(R.scenes):
        v, vsr = sf.read(f"{vd}/s{si}.wav")
        v = np.interp(np.arange(int(len(v) * SR / vsr)) * vsr / SR, np.arange(len(v)), v)
        a = int(sc["vo_start"] * SR); voice[a:a + len(v)] += v[:n - a]
    voice /= np.abs(voice).max()
    env = np.convolve(np.abs(voice), np.ones(4410) / 4410, "same")
    duck = np.convolve(np.where(env > 0.02, 0.3, 1.0), np.ones(8820) / 8820, "same")
    m = 0.9 * voice + 0.22 * mus * duck + 0.25 * sfx
    m[-int(SR * 1.5):] *= np.linspace(1, 0, int(SR * 1.5))
    sf.write(out_wav, m / np.abs(m).max() * 0.9, SR)

def main():
    sd, od = sys.argv[1], sys.argv[2]; jobs_n = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 3
    os.makedirs(od, exist_ok=True); work = os.path.join(od, "_work"); os.makedirs(work, exist_ok=True)
    specs, bad = [], {}
    for p in sorted(glob.glob(os.path.join(sd, "*.json"))):
        try: sp = json.load(open(p))
        except Exception as ex: bad[p] = [f"JSON error: {ex}"]; continue
        e = validate(sp)
        if e: bad[p] = e
        else: specs.append((p, sp))
    if bad: print(json.dumps(dict(ok=False, invalid=bad), ensure_ascii=False, indent=1)); sys.exit(2)
    ensure_model()
    voice_all([(sp, os.path.join(work, sp["slug"], "vo")) for _, sp in specs])
    sys.path.insert(0, HERE); from reelgen import load
    tasks = []
    for p, sp in specs:
        vd = os.path.join(work, sp["slug"], "vo")
        for k in range(len(sp["scenes"])): tasks.append((p, vd, k, os.path.join(work, sp["slug"], f"s{k}.mp4")))
    def run(tk):
        p, vd, k, out = tk
        r = subprocess.run([sys.executable, os.path.join(HERE, "reelgen.py"), p, vd, str(k), out], capture_output=True, text=True)
        return out, r.returncode, r.stderr[-400:]
    with ThreadPoolExecutor(jobs_n) as ex: res = list(ex.map(run, tasks))
    fails = [r for r in res if r[1] != 0 or not os.path.exists(r[0])]
    if fails: print(json.dumps(dict(ok=False, render_errors=fails), indent=1)); sys.exit(3)
    done = []
    for p, sp in specs:
        wd = os.path.join(work, sp["slug"]); vd = os.path.join(wd, "vo"); R = load(p, vd)
        with open(f"{wd}/list.txt", "w") as f:
            for k in range(len(sp["scenes"])): f.write(f"file 's{k}.mp4'\n")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{wd}/list.txt", "-c", "copy", f"{wd}/video.mp4"], check=True)
        music_mix(R, vd, f"{wd}/mix.wav")
        out = os.path.join(od, sp["slug"] + ".mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{wd}/video.mp4", "-i", f"{wd}/mix.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                        "-af", "highpass=f=70,acompressor=threshold=-18dB:ratio=3:attack=5:release=120,loudnorm=I=-14:TP=-1.5",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", out], check=True)
        # cover check frame (hook at 3 s)
        R.frame(3.0).convert("RGB").save(os.path.join(work, sp["slug"] + "_cover.jpg"), quality=85)
        done.append(dict(slug=sp["slug"], file=out, seconds=round(R.total, 1), mb=round(os.path.getsize(out) / 1e6, 2)))
    print(json.dumps(dict(ok=True, videos=done), ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
