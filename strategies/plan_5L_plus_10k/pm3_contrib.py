"""3 PM breakout on Rs 20 lakh from Jan 2007, before and after Indian capital-gains tax (same tax engine as momentum aftertax.py)."""
import pm3_robust as P, pandas as pd, numpy as np
import sys
CAP = 5e5; ADD = 1e4; COST = P.COST
def fy_of(t): return t.year + 1 if t.month >= 4 else t.year
def rates(fy, mode):
    if mode == "none": return 0, 0, 0
    if mode == "current": return .20, .125, 125000
    if fy >= 2025: return .20, .125, 125000
    if fy >= 2019: return .15, .10, 100000
    return .15, 0.0, 0
def run(mode, max_pos=10, w=0.10, stop=0.10):
    dates = P.dates; dts = dates[dates >= pd.Timestamp("2007-01-01")]; di = {d: i for i, d in enumerate(dates)}
    syms = P.syms; col = {s: j for j, s in enumerate(syms)}
    Cv, Lv, Ov, L20, M63, MK = P.C.values, P.L.values, P.O.values, P.low20.values, P.mom63.values, P.mkt_on.values
    sig = (P.base_sig & (P.turn20 >= 5e7)).values
    cash = CAP; pos = {}; vals = []; st = lt = cf_st = cf_lt = 0.0; cur = fy_of(dts[0]); taxes = {}; ntr = 0
    def sell(s, px, d):
        nonlocal cash, st, lt, ntr
        p = pos.pop(s); pr = p["sh"] * px * (1 - COST); cash += pr; g = pr - p["cost"]; ntr += 1
        if (d - p["d"]).days >= 365: lt += g
        else: st += g
    def mtm(i): return cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
    firsts = set(pd.Series(dts, index=dts).groupby(dts.to_period('M')).first())
    for d in dts:
        i = di[d]
        if d in firsts and d != dts[0]: cash += ADD
        if fy_of(d) != cur:
            rs, rl, ex = rates(cur, mode); S_, L_ = st + cf_st, lt + cf_lt
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cf_st, cf_lt = min(S_, 0), min(L_, 0); S_, L_ = max(S_, 0), max(L_, 0)
            tax = (S_ * rs + max(L_ - ex, 0) * rl) * 1.04; eq = mtm(i)
            if tax > 0 and eq > 0:
                f = 1 - tax / eq; cash *= f
                for p in pos.values(): p["sh"] *= f; p["cost"] *= f
            taxes[cur] = tax; st = lt = 0.0; cur = fy_of(d)
        for s in list(pos):
            j = col[s]; sl = pos[s]["px"] * (1 - stop)
            if not np.isnan(Lv[i, j]) and Lv[i, j] <= sl:
                op = Ov[i, j]; sell(s, min(op, sl) if not np.isnan(op) else sl, d)
        for s in list(pos):
            j = col[s]; c = Cv[i, j]
            if np.isnan(c): continue
            if c < L20[i, j] or (not MK[i] and c < pos[s]["px"]): sell(s, c, d)
        eq = mtm(i)
        if MK[i] and len(pos) < max_pos:
            cands = [syms[j] for j in np.flatnonzero(sig[i]) if syms[j] not in pos]
            cands.sort(key=lambda s: -(M63[i, col[s]] if not np.isnan(M63[i, col[s]]) else -9))
            for s in cands[: max_pos - len(pos)]:
                px = Cv[i, col[s]]; val = min(w * eq, cash / (1 + COST))
                if val < 0.01 * eq: break
                cash -= val * (1 + COST); pos[s] = dict(sh=val / px, px=px, d=d, cost=val * (1 + COST))
        vals.append(mtm(i))
    return pd.Series(vals, index=dts), pd.Series(taxes), ntr
out = {}
for mode in ("none", "current", "historical"):
    e, tx, n = run(mode); yrs = (e.index[-1] - e.index[0]).days / 365.25
    out[mode] = e
    print(f"{mode:10s} final {e.iloc[-1]/1e7:6.2f} cr CAGR {((e.iloc[-1]/CAP)**(1/yrs)-1)*100:5.1f}% maxDD {(e/e.cummax()-1).min()*100:5.1f}% tax {tx.sum()/1e7:5.2f} cr trades/yr {n/yrs:.0f}")
Y = pd.DataFrame({k: v.resample("YE").last() for k, v in out.items()}); Y.index = Y.index.year
Y.to_csv("pm3_contrib.csv"); print((Y / 1e5).round(1).to_string())
