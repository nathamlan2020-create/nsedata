"""7 hedged lots per expiry day on Rs 7.5 lakh: Nifty Tue 2 lots @9:22 + 2 @9:35 + 3 @10:05; Sensex Thu 2 @9:45 + 2 @10:05 + 3 @10:35.
Same rules (40% SL/leg, other leg to cost, 1 re-entry before 13:00, exit 15:15) + Rs 1 hedges. Extra slippage for size: +0.5 pt/side on every short leg."""
exec(open("plan_6lots_hedged.py").read().split("NL = [")[0])
import pandas as pd, numpy as np
for ns, extra in ((NS, 1.0), (SS, 1.0)):                                       # +0.5 pt per side extra on short legs for bigger size
    c0 = ns["cost"]; ns["cost"] = (lambda c0: (lambda a, b: c0(a, b) + extra))(c0)
def per_entry(ns, entry):
    kw = dict(entry=entry, sl=0.40, be=True, reentry=True); s = {}
    for p in ns["PRE"]:
        x = ns["straddle"](p, **kw)
        if x is None: continue
        h, _ = hedge(ns, p, entry); s[p["dt"]] = (x + h) * ns["LOTQ"]
    return pd.Series(s)
N = sum(w * per_entry(NS, e) for e, w in (("09:22", 2), ("09:35", 2), ("10:05", 3)))
S = sum(w * per_entry(SS, e) for e, w in (("09:45", 2), ("10:05", 2), ("10:35", 3)))
start = S.index[0]; N = N[N.index >= start]
D = pd.DataFrame({"nifty": N, "sensex": S}).fillna(0).sort_index(); D["total"] = D.nifty + D.sensex
M = D.groupby(D.index.to_period("M")).sum(); M["pct_7_5L"] = M.total / CAP * 100; M["cum"] = M.total.cumsum()
Y = D.groupby(D.index.year)[["nifty", "sensex", "total"]].sum(); Y["pct_7_5L"] = Y.total / CAP * 100
eq = D.total.cumsum(); yrs = (D.index[-1] - D.index[0]).days / 365.25
pd.set_option("display.width", 200); pd.set_option("display.max_rows", 100)
print(M.round(0).to_string()); print(Y.round(1).to_string())
print(f"avg/yr Rs {D.total.sum()/yrs:,.0f} ({D.total.sum()/yrs/CAP*100:.0f}% of 7.5L) | worst day Rs {D.total.min():,.0f} | max DD Rs {(eq-eq.cummax()).min():,.0f} | losing months {(M.total<0).sum()}/{len(M)} | worst month Rs {M.total.min():,.0f}")
M.to_csv("plan_7lots_hedged_monthly.csv"); pd.to_pickle(dict(M=M, Y=Y, D=D), f"{SP}/plan7.pkl")
