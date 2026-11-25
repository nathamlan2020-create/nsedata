"""Momentum rotation (blend top 20, keep in top 40, monthly, 50 EMA -> cash) from 1 Nov 2021 with real capital,
liquidity filter, size-dependent slippage, optional liquid-fund yield on idle cash and optional 1-day delay. Taxed at FY end.
Needs ../n500 (unzip daily/nse500_daily_2005-2026.zip there, plus daily/indices/IDX_CRSLDX.csv).
Usage: python3 capital_slippage.py   (run from strategies/momentum_rotation)"""
import sys, os, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
import momentum_rotation as M

START = "2021-11-01"
days = M.days[M.days >= START]
first = set(pd.Series(days, index=days).groupby(days.to_period("M")).first().values)
S = M.SC["blend"]; ON = M.FLT["50EMA->cash"]
vol20 = M.ret1.rolling(20, min_periods=10).std()
def fy(t): return t.year + 1 if t.month >= 4 else t.year

def sim(cap, min_turn_cr=5, impact=False, liq=0.0, delay=0, tax=True, N=20):
    elig = (M.C > 50) & (M.turn > min_turn_cr * 1e7) & M.C.notna()
    exe = M.Cf.shift(-delay) if delay else M.Cf
    cash = cap; pos = {}; was_on = True; vals = []; st = lt = cfs = cfl = 0.0; cur = fy(days[0])
    pending = None; slip_paid = 0.0; taxes = 0.0; traded = 0.0
    def cost(s, amt, t):
        c = M.COST
        if impact:
            adv = M.turn.loc[t, s]; v = vol20.loc[t, s]
            if np.isfinite(adv) and adv > 0 and np.isfinite(v): c += min(v * np.sqrt(amt / adv), 0.03)
        return c
    def sell(s, t):
        nonlocal cash, st, lt, slip_paid, traded
        sh, basis, d0 = pos.pop(s); p = exe.loc[t, s]; gross = sh * p; c = cost(s, gross, t)
        pr = gross * (1 - c); cash += pr; slip_paid += gross * (c - M.COST); traded += gross; g = pr - basis
        if (t - d0).days >= 365: lt += g
        else: st += g
    def buy(s, amt, t):
        nonlocal cash, slip_paid, traded
        p = exe.loc[t, s]; c = cost(s, amt, t)
        pos[s] = [amt * (1 - c) / p, amt, t]; cash -= amt; slip_paid += amt * (c - M.COST); traded += amt
    for t in days:
        px = M.Cf.loc[t]
        if tax and fy(t) != cur:
            S_, L_ = st + cfs, lt + cfl
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cfs, cfl = min(S_, 0), min(L_, 0)
            tx = (max(S_, 0) * 0.20 + max(max(L_, 0) - 125000, 0) * 0.125) * 1.04
            cash -= tx; taxes += tx; st = lt = 0.0; cur = fy(t)
        cash += max(cash, 0) * liq / 252
        if t == days[-1] and delay: pass
        f = bool(ON.loc[t])
        if not f and pos:
            for s in list(pos): sell(s, t)
        if f and (t in first or not was_on):
            sc = S.loc[t].where(elig.loc[t]).dropna().sort_values(ascending=False); ok = set(sc.index[:2 * N])
            for s in [s for s in pos if s not in ok]: sell(s, t)
            eq = cash + sum(p[0] * px[s] for s, p in pos.items()); tgt = eq / N
            for s in sc.index[:N]:
                if len(pos) >= N: break
                if s in pos: continue
                amt = min(tgt, cash)
                if amt <= 0: break
                buy(s, amt, t)
        was_on = f
        vals.append(cash + sum(p[0] * px[s] for s, p in pos.items()))
    e = pd.Series(vals, index=days)
    if delay: e = e.iloc[:-delay]
    return e, dict(slip=slip_paid, tax=taxes, traded=traded)

def summ(e, cap):
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    m = e.resample("ME").last(); start = m.shift(1); start.iloc[0] = cap
    mr = m / start - 1
    return dict(final=e.iloc[-1], CAGR=(e.iloc[-1] / cap) ** (1 / yrs) - 1, maxDD_daily=(e / e.cummax() - 1).min(),
                maxDD_monthend=(m / m.cummax().clip(lower=cap) - 1).min(), worst_month=mr.min(), up=(mr > 0).sum(), n=len(mr))

if __name__ == "__main__":
    out = {}
    V = [("A as before (Rs 5cr turnover, 0.15% cost)", dict()),
         ("B + size-based slippage", dict(impact=True)),
         ("C + only stocks > Rs 50cr turnover", dict(impact=True, min_turn_cr=50)),
         ("D = C + idle cash in liquid fund 6%", dict(impact=True, min_turn_cr=50, liq=0.06)),
         ("E = D + 1-day delay", dict(impact=True, min_turn_cr=50, liq=0.06, delay=1)),
         ("F = B + liquid 6% (no 50cr filter)", dict(impact=True, liq=0.06))]
    for cap in (5e5, 15e5, 50e5):
        for name, kw in V:
            for tax in (False, True):
                e, x = sim(cap, tax=tax, **kw); s = summ(e, cap); s.update(x)
                out[f"{int(cap/1e5)}L|{name}|{'after tax' if tax else 'pre tax'}"] = s
                print(f"{int(cap/1e5):>3}L {name:42s} {'AT ' if tax else 'pre'} final {s['final']/1e5:7.1f}L CAGR {s['CAGR']*100:5.1f}% "
                      f"DDd {s['maxDD_daily']*100:6.1f}% DDm {s['maxDD_monthend']*100:6.1f}% worstM {s['worst_month']*100:6.1f}% "
                      f"up {s['up']}/{s['n']} slip {x['slip']/1e5:5.2f}L tax {x['tax']/1e5:5.2f}L", flush=True)
    pd.DataFrame(out).T.to_csv("capital_slippage_summary.csv")
    # month-by-month at Rs 50 lakh, after tax: best case (slippage + liquid) and conservative (> Rs 50 cr turnover)
    cols = {}
    for k, kw in {"best": dict(impact=True, liq=0.06), "conservative": dict(impact=True, min_turn_cr=50, liq=0.06)}.items():
        e, _ = sim(50e5, tax=True, **kw); m = e.resample("ME").last(); s = m.shift(1); s.iloc[0] = 50e5
        cols[f"{k}_value"] = m.round(0); cols[f"{k}_return_%"] = ((m / s - 1) * 100).round(2)
        cols[f"{k}_drawdown_%"] = ((m / m.cummax().clip(lower=50e5) - 1) * 100).round(1)
    out_m = pd.DataFrame(cols); out_m.index = out_m.index.strftime("%Y-%m"); out_m.index.name = "month"
    out_m.to_csv("capital_slippage_monthly_50L_aftertax.csv")
