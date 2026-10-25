"""Nifty 3 lots (Tue) + Sensex 3 lots (Thu) with a 'Rs 1 hedge': at each straddle entry also BUY 1 far CE and 1 far PE costing ~Rs 1
(strike found with the real-data skew: IV x 1.40 for calls, x 2.25 for puts, from hedge_calib.py), held to 15:15. Compared with unhedged.
Hedge costs: Rs 40 brokerage per leg round trip + 0.1 pt slippage per side + 0.04% charges; exit value floored at Rs 0.05."""
import os, pandas as pd, numpy as np
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"; CAP = 7.5e5; RC, RP = 1.403, 2.252
src = open("sensex_expiry.py").read(); fn = src[src.index("def straddle("):src.index("V = {")]
os.environ["SCALE_RANGE"] = "1"; SS = {}; exec(src[:src.index("V = {")], SS); SS["LOTQ"] = 20
NS = {}; exec(open("improve.py").read().split("def sim(")[0], NS); NS["STEP"] = 50; exec(fn, NS); NS["LOTQ"] = 65
def hedge(ns, p, entry, target=1.0):
    bsv, hm, step, lotq = ns["bsv"], ns["hm"], ns["STEP"], ns["LOTQ"]
    t = p["t"]; T = p["T"]; iv = p["iv"]; i0 = np.searchsorted(t, hm(entry)); ie = np.searchsorted(t, hm("15:15"))
    s0 = p["o"][i0]; out = 0.0; info = {}
    for cp, r, sgn in (("C", RC, 1), ("P", RP, -1)):
        ks = np.round(s0 / step) * step + sgn * step * np.arange(1, 400); ks = ks[(ks > 0.8 * s0) & (ks < 1.2 * s0)]
        with np.errstate(all="ignore"): pr = bsv(s0, ks, T[i0], iv * r, cp)
        j = int(np.nanargmin(np.abs(pr - target))); k = ks[j]; e = max(float(pr[j]), 0.05)
        x = max(float(bsv(p["c"][ie], k, T[ie], iv * r, cp)), 0.05)
        out += (x - e) - (47.2 / lotq + 0.2 + (e + x) * 0.0004); info[cp] = abs(k / s0 - 1) * 100
    return out, info
def run(ns, legs, hedged):
    s = {}; dist = []
    for p in ns["PRE"]:
        tot = 0.0
        for kw in legs:
            x = ns["straddle"](p, **kw)
            if x is None: continue
            tot += x
            if hedged:
                h, info = hedge(ns, p, kw["entry"]); tot += h; dist.append(info)
        s[p["dt"]] = tot * ns["LOTQ"]
    return pd.Series(s), pd.DataFrame(dist)
NL = [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:22", "09:35", "10:05")]
SL_ = [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:45", "10:05", "10:35")]
res = {}
for hedged in (False, True):
    n, dn = run(NS, NL, hedged); s, ds = run(SS, SL_, hedged)
    res[hedged] = (n, s)
    if hedged: print("avg hedge distance at entry  Nifty CE %.2f%% PE %.2f%% | Sensex CE %.2f%% PE %.2f%%" % (dn.C.mean(), dn.P.mean(), ds.C.mean(), ds.P.mean())); DN, DS = dn, ds
start = res[True][1].index[0]
rows = []; Ms = {}
for hedged in (False, True):
    n, s = res[hedged]
    for nm_, ser in (("Nifty 3 lots (2019-26)", n[n.index >= "2019-01-01"]), ("Sensex 3 lots", s)):
        eq = ser.cumsum(); yrs = (ser.index[-1] - ser.index[0]).days / 365.25; yr = ser.groupby(ser.index.year).sum()
        rows.append(dict(book=nm_, hedge="Rs 1 hedge" if hedged else "none", rs_yr=round(ser.sum() / yrs), worst_day=round(ser.min()),
                         max_dd=round((eq - eq.cummax()).min()), win=round((ser > 0).mean() * 100, 1), losing_yrs=int((yr < 0).sum())))
    comb = pd.concat([n[n.index >= start], s]).groupby(level=0).sum().sort_index(); eq = comb.cumsum(); yrs = (comb.index[-1] - comb.index[0]).days / 365.25
    M = comb.groupby(comb.index.to_period("M")).sum(); Ms[hedged] = M
    rows.append(dict(book="PLAN Nifty3+Sensex3 (May23-Oct26)", hedge="Rs 1 hedge" if hedged else "none", rs_yr=round(comb.sum() / yrs), worst_day=round(comb.min()),
                     max_dd=round((eq - eq.cummax()).min()), win=round((comb > 0).mean() * 100, 1), losing_yrs=int((comb.groupby(comb.index.year).sum() < 0).sum()),
                     losing_months=int((M < 0).sum()), pct_on_7_5L=round(comb.sum() / yrs / CAP * 100, 1)))
R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("hedge_summary.csv", index=False)
MM = pd.DataFrame({"no_hedge": Ms[False], "rs1_hedge": Ms[True]}); MM["hedge_cost"] = MM.no_hedge - MM.rs1_hedge; print(MM.round(0).to_string()); MM.to_csv("plan_6lots_hedged_monthly.csv")
# rough margin per hedged lot ~ max loss = (far-side distance) x qty  (worst side of the fly; credit ignored)
for nm_, d, lvl, q in (("Nifty", DN, 25000, 65), ("Sensex", DS, 82000, 20)):
    print(f"{nm_}: hedged max loss per lot ~ Rs {max(d.C.mean(), d.P.mean())/100*lvl*q:,.0f} (vs naked margin ~ Rs {0.14*lvl*q:,.0f})")
