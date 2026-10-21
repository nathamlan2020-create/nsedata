"""Per stock-day snapshot prices from 1-min Kite data (price 'at HH:MM' = close of the HH:MM-1 minute bar)."""
import glob, os, numpy as np, pandas as pd
from multiprocessing import Pool
T = {"p920": 920, "p930": 930, "p945": 945, "p1015": 1015, "p1200": 1200, "p1400": 1400, "p1445": 1445,
     "p1500": 1500, "p1515": 1515}

def hm(ix): return ix.hour * 100 + ix.minute

def one(f):
    sym = os.path.basename(f).split(".")[0].replace("nifty50_1min_kite_2015-2026", "NIFTY")
    d = pd.read_csv(f, index_col=0, parse_dates=True)
    if "volume" not in d: d["volume"] = 0
    d = d[(hm(d.index) >= 915) & (hm(d.index) <= 1529)]
    d["day"] = d.index.normalize(); d["t"] = hm(d.index)
    g = d.groupby("day")
    out = pd.DataFrame({"open": g.open.first(), "close": g.close.last(), "high": g.high.max(), "low": g.low.min(),
                        "vol": g.volume.sum(), "nbar": g.size()})
    pv = d.close * d.volume
    for k, tt in T.items():
        # last close strictly before tt
        out[k] = d[d.t < tt].groupby("day").close.last()
        if k in ("p1015", "p1445"):
            m = d.t < tt
            out["vwap" + k[1:]] = pv[m].groupby(d.day[m]).sum() / d.volume[m].groupby(d.day[m]).sum()
    m = d.t < 930
    out["v15"] = d.volume[m].groupby(d.day[m]).sum()
    out["hi15"] = d.high[m].groupby(d.day[m]).max(); out["lo15"] = d.low[m].groupby(d.day[m]).min()
    out = out[out.nbar > 300]
    out["pc"] = out.close.shift(1); out["ph"] = out.high.shift(1); out["pl"] = out.low.shift(1)
    out["sym"] = sym
    return out.reset_index()

if __name__ == "__main__":
    fs = sorted(glob.glob("../n50/stocks/*.csv.gz")) + ["/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz"]
    with Pool(2) as p: res = p.map(one, fs)
    F = pd.concat(res); F.to_pickle("days.pkl"); print(F.shape, F.sym.nunique()); print(F.tail(2).T)
