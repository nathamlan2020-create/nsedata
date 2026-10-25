"""Nifty 3 lots (Tue) + Sensex 3 lots (Thu) on Rs 7.5 lakh capital. Margin is reused: each day's positions are closed by 15:15.
Sensex 3-lot variants are compared first; the best (highest return per unit of drawdown) is used in the combined plan."""
import os, pandas as pd, numpy as np
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"; CAP = 7.5e5
src = open("sensex_expiry.py").read(); fn = src[src.index("def straddle("):src.index("V = {")]
os.environ["SCALE_RANGE"] = "1"; SS = {}; exec(src[:src.index("V = {")], SS)
NS = {}; exec(open("improve.py").read().split("def sim(")[0], NS); NS["STEP"] = 50; exec(fn, NS)
def series(ns, legs, lot, gross=False):
    c0 = ns["cost"]
    if gross: ns["cost"] = lambda a, b: 0.0
    s = pd.Series({p["dt"]: sum(x for x in (ns["straddle"](p, **kw) for kw in legs) if x is not None) * lot for p in ns["PRE"]})
    ns["cost"] = c0; return s
SV = {"3 x 10:05, 30% SL/leg": [dict(entry="10:05")] * 3,
      "9:45/10:05/10:35, 30% SL/leg": [dict(entry=e) for e in ("09:45", "10:05", "10:35")],
      "9:45/10:05/10:35, 40% SL + cost + re-entry": [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:45", "10:05", "10:35")],
      "9:22/9:35/10:05, 40% SL + cost + re-entry": [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:22", "09:35", "10:05")],
      "10:05/10:35/11:05, 30% SL/leg": [dict(entry=e) for e in ("10:05", "10:35", "11:05")]}
rows = []; keep = {}
for name, legs in SV.items():
    s = series(SS, legs, 20); keep[name] = s; eq = s.cumsum(); yrs = (s.index[-1] - s.index[0]).days / 365.25
    yr = s.groupby(s.index.year).sum(); dd = (eq - eq.cummax()).min()
    rows.append(dict(sensex_3lots=name, rs_yr=round(s.sum() / yrs), worst_day=round(s.min()), max_dd=round(dd), ret_dd=round(s.sum() / yrs / -dd, 2),
                     win=round((s > 0).mean() * 100, 1), losing_yrs=int((yr < 0).sum()), **{f"y{k}": round(v) for k, v in yr.items()}))
S = pd.DataFrame(rows).sort_values("ret_dd", ascending=False); pd.set_option("display.width", 250); print(S.to_string(index=False))
best = S.iloc[0].sensex_3lots; print("BEST:", best)
ND = [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:22", "09:35", "10:05")]
n_net, n_gr = series(NS, ND, 65), series(NS, ND, 65, gross=True)
s_net, s_gr = keep[best], series(SS, SV[best], 20, gross=True)
start = s_net.index[0]
df = pd.concat([pd.DataFrame({"nifty_gross": n_gr, "nifty_net": n_net}), pd.DataFrame({"sensex_gross": s_gr, "sensex_net": s_net})]).fillna(0)
df = df[df.index >= start].groupby(level=0).sum().sort_index()
M = df.groupby(df.index.to_period("M")).sum()
M["costs"] = (M.nifty_gross - M.nifty_net) + (M.sensex_gross - M.sensex_net); M["gross"] = M.nifty_gross + M.sensex_gross; M["net"] = M.nifty_net + M.sensex_net
M["ret_pct_on_7.5L"] = M.net / CAP * 100; M["cum_net"] = M.net.cumsum()
daily_eq = CAP + df.nifty_net.add(df.sensex_net).cumsum(); dd = (daily_eq / daily_eq.cummax() - 1).min() * 100
Y = M.groupby(M.index.year)[["gross", "costs", "nifty_net", "sensex_net", "net"]].sum(); Y["ret_pct_on_7.5L"] = Y.net / CAP * 100
print(M.round(1).to_string()); print(Y.round(1).to_string())
yrs = (df.index[-1] - df.index[0]).days / 365.25
print(f"avg net/yr Rs {M.net.sum()/yrs:,.0f} = {M.net.sum()/yrs/CAP*100:.1f}% of 7.5L (simple) | worst month Rs {M.net.min():,.0f} | losing months {(M.net<0).sum()}/{len(M)} | max DD {dd:.1f}% of capital | worst day Rs {(df.nifty_net+df.sensex_net).min():,.0f}")
pd.to_pickle(dict(S=S, M=M, Y=Y, best=best, dd=dd, df=df), f"{SP}/plan6.pkl"); S.to_csv("sensex_3lot_variants.csv", index=False); M.to_csv("plan_6lots_monthly.csv")
