"""Momentum rotation drawdown-control experiments (clean Nifty 500 data, 2007-2026, Rs 5 lakh, costs 0.15%/side).
Base = blend score (3/6/12M), top N, keep while in top 2N, monthly rebalance, sell all when Nifty 500 < 50 EMA.
Levers: N (20/30), score (blend / 6M-vol-adjusted), per-stock stop (from buy or trailing from peak), invested fraction
(rest in a liquid fund earning 6%/yr), portfolio drawdown brake (halve exposure when equity is X% below its peak; back to
full when the drawdown recovers to half of X), stricter filter (also Nifty 500 > 200 DMA).
Tax: STCG 20% / LTCG 12.5% above Rs 1.25L + 4% cess on realised gains, paid at each FY end (liquid-fund income untaxed here)."""
import numpy as np, pandas as pd, itertools, sys
import momentum_rotation as M
COST = M.COST; CAP = 5e5; LIQ = 0.06 / 252
ic = M.ic
F50 = M.FLT["50EMA->cash"]; F200 = ic > ic.rolling(200).mean()
SC = {"blend": M.SC["blend"], "voladj": M.SC["6M/vol"]}
def fy(t): return t.year + 1 if t.month >= 4 else t.year

def sim(N=20, score="blend", stop=None, trail=None, invest=1.0, brake=None, strict=False, tax=True, K=2, daily=False):
    S = SC[score]; on = (F50 & F200) if strict else F50
    cash = CAP; pos = {}; was_on = True; vals = []; st = lt = cfs = cfl = 0.0; cur = fy(M.days[0]); peak = CAP; braked = False
    def sell(s, px, t):
        nonlocal cash, st, lt
        sh, cost, d0, pk = pos.pop(s); pr = sh * px * (1 - COST); cash += pr; g = pr - cost
        if (t - d0).days >= 365: lt += g
        else: st += g
    for t in M.days:
        px = M.Cf.loc[t]; lo = M.C.loc[t]
        if tax and fy(t) != cur:
            S_, L_ = st + cfs, lt + cfl
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cfs, cfl = min(S_, 0), min(L_, 0)
            cash -= (max(S_, 0) * 0.20 + max(max(L_, 0) - 125000, 0) * 0.125) * 1.04
            st = lt = 0.0; cur = fy(t)
        cash += max(cash, 0) * LIQ                                         # idle cash in a liquid fund
        f = bool(on.loc[t]); reb = daily or (t in M.first)
        # per-stock stops at the close (alert-style)
        for s in list(pos):
            p = px[s]; pos[s][3] = max(pos[s][3], p)
            if (stop and p <= pos[s][1] / pos[s][0] * (1 - stop)) or (trail and p <= pos[s][3] * (1 - trail)): sell(s, p, t)
        eq = cash + sum(p[0] * px[s] for s, p in pos.items()); peak = max(peak, eq)
        new_brake = braked
        if brake:
            dd = eq / peak - 1
            if not braked and dd <= -brake: new_brake = True
            elif braked and dd >= -brake / 2: new_brake = False
        if not f and pos:
            for s in list(pos): sell(s, px[s], t)
        expo = invest * (0.5 if new_brake else 1.0)
        if f and (reb or not was_on or new_brake != braked):
            sc = S.loc[t].where(M.elig.loc[t]).dropna().sort_values(ascending=False); ok = set(sc.index[:int(K * N)])
            for s in [s for s in pos if s not in ok]: sell(s, px[s], t)
            eq = cash + sum(p[0] * px[s] for s, p in pos.items()); tgt = eq * expo / N
            if new_brake and not braked:                                      # cut each holding to half size
                for s in list(pos):
                    sh = pos[s][0]; cut = sh * 0.5; pr = cut * px[s] * (1 - COST); cash += pr
                    g = pr - pos[s][1] * 0.5; (st := st + g) if (t - pos[s][2]).days < 365 else None
                    if (t - pos[s][2]).days >= 365: lt += g
                    pos[s][0] -= cut; pos[s][1] *= 0.5
            for s in sc.index[:N]:
                if len(pos) >= N: break
                if s in pos: continue
                amt = min(tgt, cash)
                if amt <= 0: break
                pos[s] = [amt * (1 - COST) / px[s], amt, t, px[s]]; cash -= amt
        braked = new_brake; was_on = f
        vals.append(cash + sum(p[0] * px[s] for s, p in pos.items()))
    e = pd.Series(vals, index=M.days); yrs = (e.index[-1] - e.index[0]).days / 365.25
    yr = e.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] / CAP - 1
    s3 = e[e.index >= e.index[-1] - pd.DateOffset(years=3)]
    return dict(CAGR=(e.iloc[-1] / CAP) ** (1 / yrs) - 1, maxDD=(e / e.cummax() - 1).min(), final=e.iloc[-1],
                last3y=(s3.iloc[-1] / s3.iloc[0]) ** (1 / 3) - 1, worst_yr=yret.min(), losing=(yret < 0).sum()), e

if __name__ == "__main__":
    V = [("BASE top20 blend", {}),
         ("top30", dict(N=30)),
         ("vol-adjusted score", dict(score="voladj")),
         ("top30 vol-adjusted", dict(N=30, score="voladj")),
         ("stop 15% from buy", dict(stop=0.15)), ("stop 20% from buy", dict(stop=0.20)),
         ("trail 15% from peak", dict(trail=0.15)), ("trail 20% from peak", dict(trail=0.20)),
         ("85% invested + liquid", dict(invest=0.85)), ("75% invested + liquid", dict(invest=0.75)),
         ("DD brake 10%", dict(brake=0.10)), ("DD brake 15%", dict(brake=0.15)),
         ("filter 50EMA + 200DMA", dict(strict=True)),
         ("top30 + trail 20%", dict(N=30, trail=0.20)),
         ("top30 + trail 20% + 85% invested", dict(N=30, trail=0.20, invest=0.85)),
         ("top30 voladj + trail 20%", dict(N=30, score="voladj", trail=0.20)),
         ("trail 20% + DD brake 15%", dict(trail=0.20, brake=0.15)),
         ("top30 + DD brake 15%", dict(N=30, brake=0.15)),
         ("top30 + 85% invested", dict(N=30, invest=0.85)),
         ("85% invested + DD brake 15%", dict(invest=0.85, brake=0.15))]
    rows = []; curves = {}
    for name, kw in V:
        for tax in (False, True):
            r, e = sim(**kw, tax=tax); curves[name + (" AT" if tax else "")] = e
            rows.append((name, tax, r))
        print(name, "done", flush=True)
    out = []
    for name, kw in V:
        pre = [r for n, t, r in rows if n == name and not t][0]; at = [r for n, t, r in rows if n == name and t][0]
        out.append(dict(variant=name, CAGR=round(pre["CAGR"] * 100, 1), maxDD=round(pre["maxDD"] * 100, 1),
                        CAGR_after_tax=round(at["CAGR"] * 100, 1), maxDD_after_tax=round(at["maxDD"] * 100, 1),
                        last3y_at=round(at["last3y"] * 100, 1), worst_year_at=round(at["worst_yr"] * 100, 1), losing_yrs_at=at["losing"],
                        final_after_tax_L=round(at["final"] / 1e5, 1)))
    R = pd.DataFrame(out); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("dd_control_summary.csv", index=False)
    pd.DataFrame(curves).to_csv("dd_control_equity.csv.gz")
