"""Loss-limiting rules for the 7-hedged-lot plan (Nifty Tue 2/2/3 lots, Sensex Thu 2/2/3, Rs 1 hedges, 40% SL/leg, cost-SL, 1 re-entry, exit 15:15).
Each entry is simulated minute by minute to get its running MTM, so a whole-day stop (all positions + hedges) can be applied."""
exec(open("plan_6lots_hedged.py").read().split("NL = [")[0])
import pandas as pd, numpy as np
for ns in (NS, SS):
    c0 = ns["cost"]; ns["cost"] = (lambda c0: (lambda a, b: c0(a, b) + 1.0))(c0)
def path(ns, p, entry, sl=0.40, reentry=True, reentry_if_green=None):
    """per-unit MTM path (incl. hedge) from entry to 15:15; returns array over minutes (0 before entry)."""
    bsv, hm, step, cost = ns["bsv"], ns["hm"], ns["STEP"], ns["cost"]
    t, T, iv = p["t"], p["T"], p["iv"]; n = len(t); i0 = np.searchsorted(t, hm(entry)); ie = np.searchsorted(t, hm("15:15"))
    mtm = np.zeros(n); realized = 0.0
    # hedge (bought at entry, held to 15:15)
    s0 = p["o"][i0]; hv = np.zeros(n); hcost = 0.0
    for cp, r, sgn in (("C", RC, 1), ("P", RP, -1)):
        ks = np.round(s0 / step) * step + sgn * step * np.arange(1, 400); ks = ks[(ks > 0.8 * s0) & (ks < 1.2 * s0)]
        with np.errstate(all="ignore"): pr = bsv(s0, ks, T[i0], iv * r, cp)
        j = int(np.nanargmin(np.abs(pr - 1.0))); k = ks[j]; e = max(float(pr[j]), 0.05)
        hv[i0:] += np.maximum(bsv(p["c"][i0:], k, T[i0:], iv * r, cp), 0.05) - e; hcost += 47.2 / ns["LOTQ"] + 0.2 + 2 * e * 0.0004
    i = i0; reentered = False
    while True:
        s0 = p["o"][i]; k = round(s0 / step) * step
        e = {cp: float(bsv(s0, k, T[i], iv, cp)) for cp in "CP"}; slv = {cp: e[cp] * (1 + sl) for cp in "CP"}; op = {"C": True, "P": True}
        Ch, Pl = bsv(p["h"], k, T, iv, "C"), bsv(p["l"], k, T, iv, "P"); Cc, Pc = bsv(p["c"], k, T, iv, "C"), bsv(p["c"], k, T, iv, "P")
        restart = None; j = i
        while j < ie:
            for cp, w in (("C", Ch[j]), ("P", Pl[j])):
                if op[cp] and w >= slv[cp]:
                    x = slv[cp] * 1.01; realized += e[cp] - x - cost(e[cp], x); op[cp] = False
                    o = "P" if cp == "C" else "C"
                    if op[o]: slv[o] = e[o]
            unreal = sum((e[cp] - (Cc[j] if cp == "C" else Pc[j])) - cost(e[cp], 0) for cp in "CP" if op[cp])
            mtm[j] = realized + unreal
            if not (op["C"] or op["P"]):
                ok = reentry and not reentered and t[j] < hm("13:00") and j + 1 < ie
                if ok and reentry_if_green is not None: ok = reentry_if_green(j)
                if ok: reentered = True; restart = j + 1
                else: mtm[j:] = realized
                break
            j += 1
        if restart is None:
            if j >= ie: mtm[ie:] = mtm[ie - 1]
            break
        i = restart
    return (mtm + hv - hcost * (np.arange(n) >= i0)) * ns["LOTQ"]
PLAN = {"N": (NS, (("09:22", 2), ("09:35", 2), ("10:05", 3))), "S": (SS, (("09:45", 2), ("10:05", 2), ("10:35", 3)))}
def day_pnl(ns, p, legs, day_stop=None, green_reentry=False, lots_scale=1.0):
    ie = np.searchsorted(p["t"], ns["hm"]("15:15"))
    paths = [w * lots_scale * path(ns, p, e) for e, w in legs]
    tot = np.sum(paths, axis=0)
    if green_reentry:   # re-entry only if the whole day's MTM is positive at that minute
        base = tot.copy()
        paths = [w * lots_scale * path(ns, p, e, reentry_if_green=(lambda j, b=base: b[j] > 0)) for e, w in legs]; tot = np.sum(paths, axis=0)
    if day_stop:
        hit = np.where(tot[:ie] <= -day_stop)[0]
        if len(hit): return float(tot[hit[0]]) * 1.0 - 0.0   # exit everything at that minute (MTM already net of costs)
    return float(tot[min(ie, len(tot) - 1)])
start = SS["PRE"][0]["dt"]
DAYS = sorted([("N", p) for p in NS["PRE"] if p["dt"] >= start] + [("S", p) for p in SS["PRE"]], key=lambda x: x[1]["dt"])
def run(day_stop=None, green=False, month_stop=None, month_mode="stop", dd_resize=None):
    out = {}; mtd = {}; eq = 0.0; peak = 0.0
    for key, p in DAYS:
        ns, legs = PLAN[key]; m = p["dt"].to_period("M"); scale = 1.0
        if month_stop is not None and mtd.get(m, 0.0) <= -month_stop:
            if month_mode == "stop": out[p["dt"]] = 0.0; continue
            scale = 3 / 7
        if dd_resize is not None and eq - peak <= -dd_resize: scale = min(scale, 3 / 7)
        v = day_pnl(ns, p, legs, day_stop, green, scale); out[p["dt"]] = v
        mtd[m] = mtd.get(m, 0.0) + v; eq += v; peak = max(peak, eq)
    return pd.Series(out)
V = [("Base: 7 hedged lots, no extra limit", {}),
     ("Day stop -Rs 15k (exit all)", dict(day_stop=15000)), ("Day stop -Rs 20k", dict(day_stop=20000)), ("Day stop -Rs 30k", dict(day_stop=30000)),
     ("Re-enter only if day is green", dict(green=True)),
     ("Month limit -Rs 40k -> stop for month", dict(month_stop=40000)), ("Month limit -Rs 40k -> 3 lots rest of month", dict(month_stop=40000, month_mode="resize")),
     ("Drawdown > Rs 30k -> 3 lots till new high", dict(dd_resize=30000)),
     ("Combo: day stop -20k + re-enter if green + DD>30k -> 3 lots", dict(day_stop=20000, green=True, dd_resize=30000))]
rows = []; keep = {}
for name, kw in V:
    s = run(**kw); keep[name] = s; eq = s.cumsum(); yrs = (s.index[-1] - s.index[0]).days / 365.25; M = s.groupby(s.index.to_period("M")).sum()
    rows.append(dict(rule=name, rs_yr=round(s.sum() / yrs), pct_7_5L=round(s.sum() / yrs / CAP * 100), worst_day=round(s.min()), worst_month=round(M.min()),
                     max_dd=round((eq - eq.cummax()).min()), losing_months=int((M < 0).sum()), days_below_minus15k=int((s < -15000).sum())))
    print(rows[-1], flush=True)
R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("loss_limits_summary.csv", index=False)
pd.DataFrame({k: v.groupby(v.index.to_period("M")).sum() for k, v in keep.items()}).round(0).to_csv("loss_limits_monthly.csv")
