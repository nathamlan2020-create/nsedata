"""Momentum rotation (blend, top 20, buffer 40, 50EMA->cash) on Rs 5 lakh with Indian capital-gains tax.
Tax per financial year (Apr-Mar) on realised gains, paid at FY end by selling a pro-rata slice of everything.
STCG (held < 12 months) and LTCG (>= 12 months); ST losses offset ST then LT gains, LT losses only LT; net losses carried forward.
'current' : STCG 20%, LTCG 12.5% above Rs 1.25 lakh exemption (rules from 23 Jul 2024), applied to every year
'historical': STCG 15% (20% from FY2024-25), LTCG 0% to FY2017-18, 10% above 1 lakh FY2018-19..FY2023-24, 12.5% above 1.25 lakh after
(plus 4% cess on tax). Costs 0.15% per side already in. Surcharge, slab rules and dividends ignored."""
import momentum_rotation as M, pandas as pd, numpy as np
S = M.SC["blend"]; on = M.FLT["50EMA->cash"]; N = 20; COST = M.COST; CAP = 500000
def rates(fy, mode):
    if mode == "none": return 0, 0, 0
    if mode == "current": return .20, .125, 125000
    if fy >= 2025: return .20, .125, 125000          # FY2024-25 onward (approx; budget change mid-FY)
    if fy >= 2019: return .15, .10, 100000
    return .15, 0.0, 0
def fy_of(t): return t.year + 1 if t.month >= 4 else t.year     # FY ending in March of this year
def run(mode):
    cash = CAP; pos = {}; was_on = True; st = lt = 0.0; cf_st = cf_lt = 0.0; cur_fy = fy_of(M.days[0]); vals = []; taxes = {}
    def sell(s, px, t):
        nonlocal cash, st, lt
        sh, cost, d0 = pos.pop(s); pr = sh * px * (1 - COST); cash += pr; g = pr - cost
        if (t - d0).days >= 365: lt += g
        else: st += g
    for t in M.days:
        if fy_of(t) != cur_fy:                       # settle tax for the finished FY
            rs, rl, ex = rates(cur_fy, mode)
            S_, L_ = st + cf_st, lt + cf_lt
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cf_st = min(S_, 0); cf_lt = min(L_, 0); S_ = max(S_, 0); L_ = max(L_, 0)
            tax = (S_ * rs + max(L_ - ex, 0) * rl) * 1.04
            px = M.Cf.loc[t]; eq = cash + sum(p[0] * px[s] for s, p in pos.items())
            if tax > 0 and eq > 0:
                f = 1 - tax / eq; cash *= f
                for s in pos: pos[s][0] *= f; pos[s][1] *= f
            taxes[cur_fy] = tax; st = lt = 0.0; cur_fy = fy_of(t)
        px = M.Cf.loc[t]; f = bool(on.loc[t]); reb = t in M.first
        if not f and pos:
            for s in list(pos): sell(s, px[s], t)
        if f and (reb or not was_on):
            sc = S.loc[t].where(M.elig.loc[t]).dropna().sort_values(ascending=False); ok = set(sc.index[:2 * N])
            for s in [s for s in pos if s not in ok]: sell(s, px[s], t)
            eq = cash + sum(p[0] * px[s] for s, p in pos.items())
            for s in sc.index[:N]:
                if len(pos) >= N: break
                if s in pos: continue
                amt = min(eq / N, cash)
                if amt <= 0: break
                pos[s] = [amt * (1 - COST) / px[s], amt, t]; cash -= amt
        was_on = f
        vals.append(cash + sum(p[0] * px[s] for s, p in pos.items()))
    e = pd.Series(vals, index=M.days)
    return e, pd.Series(taxes)
res = {}
for mode in ("none", "historical", "current"):
    e, tx = run(mode); yrs = (e.index[-1] - e.index[0]).days / 365.25
    res[mode] = (e, tx)
    print(f"{mode:10s} final Rs {e.iloc[-1]/1e7:6.2f} cr  CAGR {((e.iloc[-1]/CAP)**(1/yrs)-1)*100:5.1f}%  maxDD {(e/e.cummax()-1).min()*100:5.1f}%  total tax Rs {tx.sum()/1e7:5.2f} cr")
Y = pd.DataFrame({m: res[m][0].resample("YE").last() for m in res}); Y.index = Y.index.year
R = Y.pct_change(); R.iloc[0] = Y.iloc[0] / CAP - 1
out = pd.DataFrame({"pre_tax_value_L": (Y["none"] / 1e5).round(1), "pre_tax_ret%": (R["none"] * 100).round(1),
                    "after_tax_value_L(current)": (Y["current"] / 1e5).round(1), "after_tax_ret%(current)": (R["current"] * 100).round(1),
                    "after_tax_value_L(historical)": (Y["historical"] / 1e5).round(1)})
tx = res["current"][1]; tx.index = [f"FY{i-1}-{str(i)[2:]}" for i in tx.index]
print(out.to_string()); print("\ntax paid per FY, current rules (Rs lakh):"); print((tx / 1e5).round(1).to_string())
out.to_csv("momentum_aftertax_yearly.csv")
