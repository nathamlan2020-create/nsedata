"""ORB on stocks, Kite 1-min 2015-2026. Range = first N min from 09:15. Entry on first break (at range level,
or the open if it gaps through). Stop = other side. Exit = target (k x risk) or 15:15. 1 trade/day/stock.
Cost 0.10% round trip (intraday charges + slippage)."""
import sys, glob, os, numpy as np, pandas as pd
from multiprocessing import Pool
COST = 0.0010
VARS = [("15m exit 3:15", 15, None, 0), ("15m 1:2 tgt", 15, 2, 0), ("30m exit 3:15", 30, None, 0),
        ("30m 1:2 tgt", 30, 2, 0), ("15m long only", 15, None, 1), ("60m exit 3:15", 60, None, 0)]
def run_sym(f):
    sym = os.path.basename(f).split(".")[0]
    df = pd.read_csv(f, index_col=0, parse_dates=True)
    t = df.index.hour*60 + df.index.minute; df = df[(t >= 555) & (t <= 915)]
    days = [(d, g.high.values, g.low.values, g.open.values, g.close.values) for d, g in df.groupby(df.index.normalize())]
    out = []
    for name, N, tgt, side in VARS:
        for day, Hh, Ll, Oo, Cc in days:
            if len(Hh) < N + 60: continue
            hi, lo = Hh[:N].max(), Ll[:N].min()
            H, L, O, C = Hh[N:], Ll[N:], Oo[N:], Cc[N:]
            bu, bd = H > hi, L < lo
            up = bu.argmax() if bu.any() else 10**9; dn = bd.argmax() if bd.any() else 10**9
            if up == dn == 10**9: continue
            d = 1 if up < dn else -1
            if side and d != side: continue
            k = min(up, dn); e = max(O[k], hi) if d == 1 else min(O[k], lo); s = lo if d == 1 else hi
            r = abs(e - s); tp = e + d*tgt*r if tgt else None; x = C[-1]
            for j in range(k, len(H)):
                if (d == 1 and L[j] <= s) or (d == -1 and H[j] >= s):
                    x = s if j == k else (min(O[j], s) if d == 1 else max(O[j], s)); break
                if tp is not None and ((d == 1 and H[j] >= tp) or (d == -1 and L[j] <= tp)):
                    x = tp if j == k else (max(O[j], tp) if d == 1 else min(O[j], tp)); break
            out.append((name, sym, day, d, d*(x/e - 1) - COST))
    return out
if __name__ == "__main__":
    files = sorted(glob.glob(sys.argv[1] + "/*.csv.gz"))
    with Pool(min(12, os.cpu_count())) as p: res = p.map(run_sym, files)
    T = pd.DataFrame([r for rr in res for r in rr], columns=["var", "sym", "day", "dir", "ret"])
    T.to_csv("orb_trades.csv.gz", index=False); n = len(files)
    idx = pd.bdate_range("2015-02-02", "2026-10-19")
    print(f"PORTFOLIO: capital split equally over {n} stocks, 1x, after 0.10% cost per trade")
    for name, *_ in VARS:
        t = T[T["var"] == name]
        dly = (t.groupby("day").ret.sum()/n).reindex(idx).fillna(0)
        eq = (1+dly).cumprod(); cagr = eq.iloc[-1]**(1/11.7)-1; dd = (eq/eq.cummax()-1).min()
        ins, oos = t[t.day < "2022"].ret.mean()*100, t[t.day >= "2022"].ret.mean()*100
        yr = (dly.groupby(dly.index.year).apply(lambda r: (1+r).prod()-1)*100).round(1).to_dict()
        print(f"\n{name:14s} trades {len(t)} win {(t.ret>0).mean()*100:.1f}% avg/trade {t.ret.mean()*100:+.3f}% "
              f"(before cost {t.ret.mean()*100+0.1:+.3f}%) | 2015-21 {ins:+.3f}% 2022-26 {oos:+.3f}% | CAGR {cagr*100:+.1f}% DD {dd*100:.1f}%")
        print("  by year %:", yr)
        s = t.groupby("sym").ret.mean().sort_values()*100
        print("  per stock avg%:", " ".join(f"{a}:{b:+.2f}" for a, b in s.items()))
