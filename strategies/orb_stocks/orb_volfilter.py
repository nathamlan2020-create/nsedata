"""ORB + previous-day volume filter. rv = prev day volume / average of the 20 days before it.
Uses trades from orb_stocks.py (same rules, 0.10% cost). Capital 1/12 per stock, unused capital idle."""
import glob, os, pandas as pd
T = pd.read_csv("orb_trades.csv.gz", parse_dates=["day"])
rv = []
for f in glob.glob("../n50/stocks/*.csv.gz"):
    s = os.path.basename(f).split(".")[0]
    v = pd.read_csv(f, index_col=0, parse_dates=True, usecols=["date", "volume"]).volume
    dv = v.groupby(v.index.normalize()).sum()
    r = (dv / dv.rolling(20).mean().shift(1)).shift(1)   # yesterday's vol vs 20d avg before yesterday
    rv.append(pd.DataFrame({"sym": s, "day": r.index, "rv": r.values}))
T = T.merge(pd.concat(rv), on=["sym", "day"], how="left").dropna(subset=["rv"])
idx = pd.bdate_range("2015-03-02", "2026-10-19")
filters = [("no filter", 0, 99), ("rv > 1.0", 1.0, 99), ("rv > 1.5", 1.5, 99), ("rv > 2.0", 2.0, 99),
           ("rv > 3.0", 3.0, 99), ("rv < 0.7 (quiet)", 0, 0.7)]
for v in T["var"].unique():
    print(f"\n=== {v} ===")
    for fn, a, b in filters:
        t = T[(T["var"] == v) & (T.rv > a) & (T.rv < b)]
        dly = (t.groupby("day").ret.sum()/12).reindex(idx).fillna(0)
        eq = (1+dly).cumprod(); cagr = eq.iloc[-1]**(1/11.6)-1; dd = (eq/eq.cummax()-1).min()
        i, o = t[t.day < "2022"].ret.mean()*100, t[t.day >= "2022"].ret.mean()*100
        print(f"{fn:17s} trades {len(t):6d} win {(t.ret>0).mean()*100:4.1f}% avg {t.ret.mean()*100:+.3f}% "
              f"| 15-21 {i:+.3f}% 22-26 {o:+.3f}% | CAGR {cagr*100:+5.1f}% DD {dd*100:6.1f}%")

print("\n=== FULL CAPITAL split only among that day's signals (1x, and 3x intraday leverage) ===")
for v in ["15m exit 3:15", "15m 1:2 tgt"]:
    for fn, a in [("rv > 1.5", 1.5), ("rv > 2.0", 2.0)]:
        t = T[(T["var"] == v) & (T.rv > a)]
        for lev in (1, 3):
            dly = (t.groupby("day").ret.mean()*lev).reindex(idx).fillna(0)
            eq = (1+dly).cumprod(); cagr = eq.iloc[-1]**(1/11.6)-1; dd = (eq/eq.cummax()-1).min()
            yr = (dly.groupby(dly.index.year).apply(lambda r: (1+r).prod()-1)*100).round(0).astype(int).to_dict()
            print(f"{v:14s} {fn} {lev}x: days traded {t.day.nunique()} CAGR {cagr*100:+.1f}% DD {dd*100:.1f}% | {yr}")
