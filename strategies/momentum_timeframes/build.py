"""Per-day snapshot prices + first-crossing times on 5/15/60m bars, from 1-min Kite data."""
import glob, os, numpy as np, pandas as pd
from multiprocessing import Pool
CHK = [930, 945, 1015, 1100, 1200, 1300, 1400]
TH = {"idx": [0.0025, 0.005, 0.0075, 0.01], "stk": [0.005, 0.01, 0.015, 0.02]}

def one(f):
    sym = "NIFTY" if "nifty50" in f else os.path.basename(f).split(".")[0]
    kind = "idx" if sym == "NIFTY" else "stk"
    d = pd.read_csv(f, index_col=0, parse_dates=True)
    t = d.index.hour * 100 + d.index.minute
    d = d[(t >= 915) & (t <= 1529)]
    d["day"] = d.index.normalize(); d["t"] = d.index.hour * 100 + d.index.minute
    g = d.groupby("day")
    out = pd.DataFrame({"open": g.open.first(), "close": g.close.last(), "n": g.size()})
    for T in CHK + [1515]:
        out[f"p{T}"] = d[d.t < T].groupby("day").close.last()
    # first bar (5/15/60m) whose close is beyond +/-x of day open, entry at that bar close
    for tf in (5, 15, 60):
        b = d.resample(f"{tf}min", origin="start_day", offset="9h15min", label="left").agg(
            {"open": "first", "close": "last"}).dropna()
        b["day"] = b.index.normalize(); b["end"] = (b.index + pd.Timedelta(minutes=tf))
        b["te"] = b.end.dt.hour * 100 + b.end.dt.minute
        b = b[b.te <= 1500]                       # no new entries after 15:00
        b["o"] = b.groupby("day").open.transform("first")
        b["r"] = b.close / b.o - 1
        for x in TH[kind]:
            hit = b[b.r.abs() > x]
            fst = hit.groupby("day").first()
            out[f"b{tf}_{x}_px"] = fst.close; out[f"b{tf}_{x}_dir"] = np.sign(fst.r)
    out = out[out.n > 300]
    out["pc"] = out.close.shift(1); out["sym"] = sym; out["kind"] = kind
    return out.reset_index()

if __name__ == "__main__":
    fs = sorted(glob.glob("../n50/stocks/*.csv.gz")) + ["/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz"]
    with Pool(2) as p: res = p.map(one, fs)
    F = pd.concat(res); F.to_pickle("days.pkl"); print(F.shape, F.sym.nunique())
