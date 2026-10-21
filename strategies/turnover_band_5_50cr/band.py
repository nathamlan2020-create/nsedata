import sys, runpy, io, contextlib, pandas as pd, numpy as np
LO, HI = 5e7, 5e8
print("===== MOMENTUM, turnover 5-50 cr =====")
import momentum_rotation as M
M.elig = (M.C > 50) & (M.turn > LO) & (M.turn < HI) & M.C.notna()
g = runpy.run_path("aftertax20.py", run_name="__main__")
res = g["res"]; e = res["current"][0]
# delay test (signals 1 day late) pre-tax
base = {k: v.copy() for k, v in M.SC.items()}
for k in M.SC: M.SC[k] = base[k].shift(1)
f0 = M.FLT["50EMA->cash"].copy(); M.FLT["50EMA->cash"] = f0.shift(1).fillna(True).astype(bool)
ed, _ = M.sim("blend", 20, True, "50EMA->cash"); s = M.stats(ed)
print(f"momentum 1-day late (pre-tax): CAGR {s['CAGR']*100:.1f}% DD {s['maxDD']*100:.0f}%")
for k in M.SC: M.SC[k] = base[k]
M.FLT["50EMA->cash"] = f0
# capacity: one position (equity/20) vs that stock's daily turnover at rebalance
mo = e.groupby(e.index.to_period("M")).last(); rows = []
for t in M.first:
    t = pd.Timestamp(t)
    if not M.FLT["50EMA->cash"].loc[t]: continue
    sc = M.SC["blend"].loc[t].where(M.elig.loc[t]).dropna().sort_values(ascending=False).index[:20]
    p = mo.get(t.to_period("M") - 1, 2e6) / 20; tv = M.turn.loc[t, sc]
    rows.append((t.year, p, (p / tv).median() * 100, (p / tv > 0.05).mean() * 100))
cap = pd.DataFrame(rows, columns=["year", "pos", "pct_adv", "share_over5"]).groupby("year").mean()
cap.to_csv("band_capacity_mom.csv")
print("\n===== 3 PM BREAKOUT (live rules incl. top-20% 6M), turnover 5-50 cr =====")
import pm3_robust as P
r6 = P.C / P.C.shift(126) - 1
P.base_sig = P.base_sig & (r6.rank(axis=1, pct=True) >= 0.80) & (P.turn20 < HI)
g2 = runpy.run_path("pm3_aftertax.py", run_name="__main__")
for m in ("next close",):
    e2, tr = P.run(m, LO); s = P.stats(e2, tr)
    print(f"3 PM 1-day late (pre-tax, from 2006): CAGR {s['CAGR']*100:.1f}% DD {s['maxDD']*100:.0f}%")
e3, tr3 = P.run("same close", LO); s3 = P.stats(e3, tr3)
print(f"3 PM same close (pre-tax, from 2006): CAGR {s3['CAGR']*100:.1f}% DD {s3['maxDD']*100:.0f}% 3y {s3['cagr_3y']*100:.1f}% trades/yr {s3['trades_yr']:.0f}")
# capacity for 3PM: position 10% of equity vs turnover on entry day
eq = g2["out"]["current"]
tr3["entry_date"] = pd.to_datetime(tr3.entry_date)
tv = np.array([P.turn20.at[d, s] for d, s in zip(tr3.entry_date, tr3.sym)])
pv = np.array([eq.asof(d) * 0.1 if d >= eq.index[0] else 2e5 for d in tr3.entry_date])
c3 = pd.DataFrame({"year": tr3.entry_date.dt.year, "pos": pv, "pct_adv": pv / tv * 100, "over5": (pv / tv > 0.05) * 100}).groupby("year").agg(
    pos=("pos", "median"), pct_adv=("pct_adv", "median"), share_over5=("over5", "mean"))
c3.to_csv("band_capacity_3pm.csv")
print("\nCAPACITY (position size vs stock's avg daily turnover)")
print(pd.concat({"mom": cap, "3pm": c3}, axis=1).round(1).to_string())
