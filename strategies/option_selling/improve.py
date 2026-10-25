"""Improving the Nifty expiry-day 3-lot straddle (Set A 9:22/9:35/10:05, Set B 9:45/10:05/10:35). Same rebuilt minute prices as entry_time.py.
Each idea is checked on two halves (2016-2022 vs 2023-2026) so only robust changes are kept.
Ideas: SL size | SL of the surviving leg moved to cost after the other leg stops | combined straddle SL | profit target on the straddle |
trailing lock once the straddle has decayed | one re-entry (new ATM straddle) after both legs stop | exit time."""
import numpy as np, pandas as pd
from scipy.special import ndtr
src = open("/home/claude/nsedata/strategies/option_selling/entry_time.py").read().split("def trade(")[0]; exec(src)

def bsv(S, K, T, v, cp):
    T = np.maximum(T, 1e-7); sq = v * np.sqrt(T); d1 = (np.log(S / K) + (R + v * v / 2) * T) / sq; d2 = d1 - sq
    return S * ndtr(d1) - K * np.exp(-R * T) * ndtr(d2) if cp == "C" else K * np.exp(-R * T) * ndtr(-d2) - S * ndtr(-d1)
PRE = []                                                          # per day: minute arrays
for dt, b, iv, _ in days:
    tm = b.index; T = np.array([mins_left(t) for t in tm]) / YM
    PRE.append(dict(dt=dt, t=np.array([t.hour * 60 + t.minute for t in tm]), o=b.open.values, h=b.high.values, l=b.low.values, c=b.close.values, T=T, iv=iv))
def hm(s): h, m_ = map(int, s.split(":")); return h * 60 + m_

def sim(p, entry, sl=0.30, be=False, comb=None, target=None, trail=None, exit_t="15:15", reentry=False):
    t = p["t"]; i0 = np.searchsorted(t, hm(entry)); ie = np.searchsorted(t, hm(exit_t)); iv = p["iv"]
    if i0 >= ie: return 0.0
    pnl = 0.0; legs_round = 0
    def open_pos(i):
        k = round(p["o"][i] / 50) * 50; T = p["T"][i]
        return dict(k=k, e={"C": float(bsv(p["o"][i], k, T, iv, "C")), "P": float(bsv(p["o"][i], k, T, iv, "P"))}, op={"C": True, "P": True},
                    sl={"C": None, "P": None}, low=None)
    pos = open_pos(i0); pos["sl"] = {cp: pos["e"][cp] * (1 + sl) for cp in "CP"}; reentered = False
    k = pos["k"]; T = p["T"]
    Ch = bsv(p["h"], k, T, iv, "C"); Pl = bsv(p["l"], k, T, iv, "P"); Cc = bsv(p["c"], k, T, iv, "C"); Pc = bsv(p["c"], k, T, iv, "P")
    i = i0
    while i < ie:
        e = pos["e"]
        for cp, worst in (("C", Ch[i]), ("P", Pl[i])):
            if pos["op"][cp] and worst >= pos["sl"][cp]:
                x = pos["sl"][cp] * 1.01; pnl += e[cp] - x - cost(e[cp], x); pos["op"][cp] = False
                other = "P" if cp == "C" else "C"
                if be and pos["op"][other]: pos["sl"][other] = e[other]          # surviving leg's stop -> cost
        if not (pos["op"]["C"] or pos["op"]["P"]):
            if reentry and not reentered and t[i] < hm("13:00"):
                reentered = True; j = i + 1
                if j >= ie: break
                pos = open_pos(j); pos["sl"] = {cp: pos["e"][cp] * (1 + sl) for cp in "CP"}; k = pos["k"]
                Ch = bsv(p["h"], k, T, iv, "C"); Pl = bsv(p["l"], k, T, iv, "P"); Cc = bsv(p["c"], k, T, iv, "C"); Pc = bsv(p["c"], k, T, iv, "P"); i = j; continue
            return pnl
        # straddle-level rules on the minute close (only while both legs are open)
        if pos["op"]["C"] and pos["op"]["P"]:
            v = Cc[i] + Pc[i]; e0 = e["C"] + e["P"]; pos["low"] = v if pos["low"] is None else min(pos["low"], v)
            hit = (comb and v >= e0 * (1 + comb)) or (target and v <= e0 * (1 - target)) or \
                  (trail and pos["low"] <= e0 * (1 - trail[0]) and v >= pos["low"] + e0 * trail[1])
            if hit:
                for cp, x in (("C", Cc[i]), ("P", Pc[i])): pnl += e[cp] - x - cost(e[cp], x)
                return pnl
        i += 1
    for cp, arr in (("C", Cc), ("P", Pc)):
        if pos["op"][cp]: x = arr[min(ie, len(arr) - 1)]; pnl += pos["e"][cp] - x - cost(pos["e"][cp], x)
    return pnl

SETS = {"Set A": ["09:22", "09:35", "10:05"], "Set B": ["09:45", "10:05", "10:35"]}
V = [("Base: SL 30%/leg, exit 15:15", dict()),
     ("SL 20%", dict(sl=0.20)), ("SL 25%", dict(sl=0.25)), ("SL 40%", dict(sl=0.40)), ("SL 50%", dict(sl=0.50)),
     ("SL 30% + other leg to cost", dict(be=True)), ("SL 40% + other leg to cost", dict(sl=0.40, be=True)),
     ("Combined SL 20% (no leg SL)", dict(sl=9, comb=0.20)), ("Combined SL 30% (no leg SL)", dict(sl=9, comb=0.30)),
     ("Leg SL 30% + combined SL 20%", dict(comb=0.20)),
     ("Target: straddle -50%", dict(target=0.50)), ("Target: straddle -70%", dict(target=0.70)),
     ("Trail: after -40%, exit on 15% bounce", dict(trail=(0.40, 0.15))), ("Trail: after -50%, exit on 10% bounce", dict(trail=(0.50, 0.10))),
     ("Re-enter once after both legs stop", dict(reentry=True)), ("SL 30% + other to cost + re-enter", dict(be=True, reentry=True)),
     ("Exit 14:30", dict(exit_t="14:30")), ("Exit 15:00", dict(exit_t="15:00")), ("Exit 15:25", dict(exit_t="15:25"))]
rows = []; daily = {}
for sname, legs in SETS.items():
    for vname, kw in V:
        s = pd.Series({p["dt"]: sum(sim(p, et, **kw) for et in legs) for p in PRE}) * LOT
        daily[(sname, vname)] = s; eq = s.cumsum(); yr = s.groupby(s.index.year).sum()
        rows.append(dict(set=sname, variant=vname, rs_total=round(s.sum()), rs_yr_2019_26=round(s[s.index >= "2019-01-01"].sum() / 7.8),
                         h1_2016_22=round(s[s.index < "2023-01-01"].sum()), h2_2023_26=round(s[s.index >= "2023-01-01"].sum()),
                         win=round((s > 0).mean() * 100, 1), worst_day=round(s.min()), max_dd=round((eq - eq.cummax()).min()), losing_yrs=int((yr < 0).sum())))
        print(sname, vname, rows[-1]["rs_total"], rows[-1]["max_dd"], flush=True)
R = pd.DataFrame(rows)
for sname in SETS:
    b = R[(R.set == sname) & (R.variant.str.startswith("Base"))].iloc[0]
    R.loc[R.set == sname, "better_both_halves"] = (R.h1_2016_22 > b.h1_2016_22) & (R.h2_2023_26 > b.h2_2023_26)
R.to_csv("improve_summary.csv", index=False); pd.to_pickle(daily, f"{SP}/improve_daily.pkl")
pd.set_option("display.width", 250); print(R.drop(columns="set").to_string(index=False))
