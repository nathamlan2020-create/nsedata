"""ORB 15-min (stop other side; exit 1:2 target or 15:15), 12 stocks, 0.10% cost.
Features per trade:
 rv5   = yesterday's volume / avg volume of the 5 days before yesterday
 orv   = today's opening-range (09:15-09:29) volume / avg opening-range volume of last 20 days
 bkv   = breakout-minute volume / avg minute volume inside the opening range
 pivot = classic floor pivots from yesterday: P=(H+L+C)/3, R1=2P-L, S1=2P-H
"""
import glob, os, numpy as np, pandas as pd
from multiprocessing import Pool
COST, N = 0.0010, 15
def run(f):
    sym = os.path.basename(f).split(".")[0]
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    t = df.index.hour*60 + df.index.minute; df = df[(t >= 555) & (t <= 929)]
    D = df.groupby(df.index.normalize()).agg(h=("high","max"), l=("low","min"), c=("close","last"), v=("volume","sum"))
    orvol = df[df.index.hour*60+df.index.minute < 555+N].groupby(lambda x: x.normalize()).volume.sum()
    D["orv"] = orvol / orvol.rolling(20).mean().shift(1)
    D["rv5"] = (D.v / D.v.rolling(5).mean().shift(1)).shift(1)
    P = (D.h + D.l + D.c)/3
    D["P"], D["R1"], D["S1"] = P.shift(1), (2*P - D.l).shift(1), (2*P - D.h).shift(1)
    out = []
    for day, g in df.groupby(df.index.normalize()):
        tm = g.index.hour*60 + g.index.minute; g = g[tm <= 915]
        if len(g) < N + 60 or day not in D.index: continue
        Hh, Ll, Oo, Cc, Vv = (g[c].values for c in ("high","low","open","close","volume"))
        hi, lo = Hh[:N].max(), Ll[:N].min(); mv = Vv[:N].mean()
        H, L, O, C, V = Hh[N:], Ll[N:], Oo[N:], Cc[N:], Vv[N:]
        bu, bd = H > hi, L < lo
        up = bu.argmax() if bu.any() else 10**9; dn = bd.argmax() if bd.any() else 10**9
        if up == dn == 10**9: continue
        d = 1 if up < dn else -1; k = min(up, dn)
        e = max(O[k], hi) if d == 1 else min(O[k], lo); s = lo if d == 1 else hi; r = abs(e-s)
        res = {}
        for name, tg in (("tgt2", 2), ("eod", None)):
            tp = e + d*tg*r if tg else None; x = C[-1]
            for j in range(k, len(H)):
                if (d == 1 and L[j] <= s) or (d == -1 and H[j] >= s):
                    x = s if j == k else (min(O[j], s) if d == 1 else max(O[j], s)); break
                if tp is not None and ((d == 1 and H[j] >= tp) or (d == -1 and L[j] <= tp)):
                    x = tp if j == k else (max(O[j], tp) if d == 1 else min(O[j], tp)); break
            res[name] = d*(x/e-1) - COST
        row = D.loc[day]
        out.append(dict(sym=sym, day=day, dir=d, entry=e, ret_tgt2=res["tgt2"], ret_eod=res["eod"],
                        rv5=row.rv5, orv=row.orv, bkv=V[k]/mv if mv > 0 else np.nan, P=row.P, R1=row.R1, S1=row.S1))
    return out
if __name__ == "__main__":
    with Pool(2) as p: res = p.map(run, sorted(glob.glob("../n50/stocks/*.csv.gz")))
    T = pd.DataFrame([r for rr in res for r in rr]).dropna(); T.to_csv("orb_features.csv.gz", index=False)
    L, S = T.dir == 1, T.dir == -1
    piv  = (L & (T.entry > T.P)) | (S & (T.entry < T.P))        # trade in direction of pivot
    pivR = (L & (T.entry > T.R1)) | (S & (T.entry < T.S1))      # breakout beyond R1/S1
    pivX = (L & (T.entry < T.P)) | (S & (T.entry > T.P))        # against pivot (contrast)
    F = {"none": T.dir != 0, "rv5>1.5": T.rv5 > 1.5, "rv5>2": T.rv5 > 2,
         "orv>1.5": T.orv > 1.5, "orv>2": T.orv > 2, "bkv>2": T.bkv > 2, "bkv>3": T.bkv > 3,
         "pivot side": piv, "beyond R1/S1": pivR, "against pivot": pivX,
         "rv5>1.5 + pivot": (T.rv5 > 1.5) & piv, "rv5>2 + pivot": (T.rv5 > 2) & piv,
         "orv>1.5 + pivot": (T.orv > 1.5) & piv, "orv>2 + pivot": (T.orv > 2) & piv,
         "rv5>1.5 + orv>1.5": (T.rv5 > 1.5) & (T.orv > 1.5),
         "rv5>1.5+orv>1.5+pivot": (T.rv5 > 1.5) & (T.orv > 1.5) & piv,
         "rv5>1.5+orv>1.5+R1/S1": (T.rv5 > 1.5) & (T.orv > 1.5) & pivR,
         "rv5>2+orv>2+pivot": (T.rv5 > 2) & (T.orv > 2) & piv,
         "orv>2 + bkv>2 + pivot": (T.orv > 2) & (T.bkv > 2) & piv}
    idx = pd.bdate_range("2015-03-02", "2026-10-19")
    for col, lab in (("ret_tgt2", "1:2 TARGET"), ("ret_eod", "EXIT 3:15")):
        print(f"\n=== ORB 15m, {lab} | full capital split among that day's signals, 1x ===")
        print(f"{'filter':24s} {'trades':>6s} {'win':>5s} {'avg%':>7s} {'15-21':>7s} {'22-26':>7s} {'CAGR':>6s} {'DD':>6s} losing yrs")
        for fn, m in F.items():
            t = T[m]; 
            if len(t) < 50: continue
            dly = t.groupby("day")[col].mean().reindex(idx).fillna(0)
            eq = (1+dly).cumprod(); cagr = eq.iloc[-1]**(1/11.6)-1; dd = (eq/eq.cummax()-1).min()
            yr = dly.groupby(dly.index.year).apply(lambda r: (1+r).prod()-1)
            print(f"{fn:24s} {len(t):6d} {(t[col]>0).mean()*100:4.0f}% {t[col].mean()*100:+.3f} "
                  f"{t[t.day<'2022'][col].mean()*100:+.3f} {t[t.day>='2022'][col].mean()*100:+.3f} "
                  f"{cagr*100:+5.1f}% {dd*100:5.0f}% {(yr<0).sum()}/12")
