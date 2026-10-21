"""Momentum rotation (blend 3/6/12M, top 20, keep while top 40, 50EMA market filter -> cash) + per-stock 34-EMA trailing stop.
ema_tf : 'D' = stock closes below its 34-day EMA;  'W' = weekly close below its 34-week EMA (checked at the week's last day)
refill : False = the freed slot waits for the next monthly rebalance;  True = refill the same day with the best-ranked stock
         (inside the top 20... then top 40) that is above its own 34 EMA
entry_above : only buy stocks trading above their 34 EMA
Clean data, Rs 5L, 0.15%/side, idle cash 6%/yr liquid fund, tax STCG 20% / LTCG 12.5% (>1.25L) + cess at each FY end."""
import numpy as np, pandas as pd
import momentum_rotation as M
COST = M.COST; CAP = 5e5; LIQ = 0.06 / 252
F50 = M.FLT["50EMA->cash"]; S = M.SC["blend"]
ED = M.Cf.ewm(span=34, adjust=False).mean()
wk = M.Cf.groupby(M.Cf.index.to_period("W-FRI")).tail(1)
EW = wk.ewm(span=34, adjust=False).mean().reindex(M.Cf.index).ffill()
WEND = pd.Series(M.Cf.index.isin(wk.index), index=M.Cf.index)
def fy(t): return t.year + 1 if t.month >= 4 else t.year

def sim(ema_tf=None, refill=False, entry_above=False, N=20, tax=True):
    cash = CAP; pos = {}; was_on = True; vals = []; st = lt = cfs = cfl = 0.0; cur = fy(M.days[0]); nstop = 0
    def sell(s, px, t):
        nonlocal cash, st, lt
        sh, cost, d0 = pos.pop(s); pr = sh * px * (1 - COST); cash += pr; g = pr - cost
        if (t - d0).days >= 365: lt += g
        else: st += g
    def buy(cands, t, px, tgt):
        nonlocal cash
        for s in cands:
            if len(pos) >= N: break
            if s in pos: continue
            if entry_above or refill_now:
                e = (ED if ema_tf != "W" else EW).at[t, s]
                if not (px[s] > e): continue
            amt = min(tgt, cash)
            if amt <= 0: break
            pos[s] = [amt * (1 - COST) / px[s], amt, t]; cash -= amt
    for t in M.days:
        px = M.Cf.loc[t]
        if tax and fy(t) != cur:
            S_, L_ = st + cfs, lt + cfl
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cfs, cfl = min(S_, 0), min(L_, 0)
            cash -= (max(S_, 0) * 0.20 + max(max(L_, 0) - 125000, 0) * 0.125) * 1.04
            st = lt = 0.0; cur = fy(t)
        cash += max(cash, 0) * LIQ
        f = bool(F50.loc[t]); reb = t in M.first; stopped = False
        if ema_tf and pos:
            for s in list(pos):
                if ema_tf == "D" and px[s] < ED.at[t, s]: sell(s, px[s], t); nstop += 1; stopped = True
                elif ema_tf == "W" and WEND.loc[t] and px[s] < EW.at[t, s]: sell(s, px[s], t); nstop += 1; stopped = True
        if not f and pos:
            for s in list(pos): sell(s, px[s], t)
        refill_now = False
        if f and (reb or not was_on):
            sc = S.loc[t].where(M.elig.loc[t]).dropna().sort_values(ascending=False); ok = set(sc.index[:2 * N])
            for s in [s for s in pos if s not in ok]: sell(s, px[s], t)
            eq = cash + sum(p[0] * px[s] for s, p in pos.items())
            buy(sc.index[:N], t, px, eq / N)
            if entry_above and len(pos) < N: buy(sc.index[N:2 * N], t, px, eq / N)
        elif f and refill and stopped:
            refill_now = True
            sc = S.loc[t].where(M.elig.loc[t]).dropna().sort_values(ascending=False)
            eq = cash + sum(p[0] * px[s] for s, p in pos.items())
            buy(sc.index[:2 * N], t, px, eq / N)
        was_on = f
        vals.append(cash + sum(p[0] * px[s] for s, p in pos.items()))
    e = pd.Series(vals, index=M.days); yrs = (e.index[-1] - e.index[0]).days / 365.25
    yr = e.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] / CAP - 1
    s3 = e[e.index >= e.index[-1] - pd.DateOffset(years=3)]
    return dict(CAGR=(e.iloc[-1] / CAP) ** (1 / yrs) - 1, maxDD=(e / e.cummax() - 1).min(), final=e.iloc[-1], stops_yr=nstop / yrs,
                last3y=(s3.iloc[-1] / s3.iloc[0]) ** (1 / 3) - 1, worst=yret.min(), losing=int((yret < 0).sum())), e

if __name__ == "__main__":
    V = [("Current model (no EMA stop)", dict()),
         ("Daily 34 EMA stop, wait for rebalance", dict(ema_tf="D")),
         ("Daily 34 EMA stop, refill same day", dict(ema_tf="D", refill=True)),
         ("Daily 34 EMA stop + buy only above 34 EMA, refill", dict(ema_tf="D", refill=True, entry_above=True)),
         ("Weekly 34 EMA stop, wait for rebalance", dict(ema_tf="W")),
         ("Weekly 34 EMA stop, refill same day", dict(ema_tf="W", refill=True)),
         ("Weekly 34 EMA stop + buy only above, refill", dict(ema_tf="W", refill=True, entry_above=True))]
    rows = []; curves = {}
    for name, kw in V:
        a, _ = sim(**kw, tax=False); b, e = sim(**kw, tax=True); curves[name] = e
        rows.append(dict(variant=name, CAGR=round(a["CAGR"] * 100, 1), maxDD=round(a["maxDD"] * 100, 1), CAGR_after_tax=round(b["CAGR"] * 100, 1),
                         maxDD_after_tax=round(b["maxDD"] * 100, 1), last3y_at=round(b["last3y"] * 100, 1), worst_year_at=round(b["worst"] * 100, 1),
                         losing_yrs=b["losing"], ema_exits_yr=round(b["stops_yr"]), final_after_tax_L=round(b["final"] / 1e5, 1)))
        print(name, "done", flush=True)
    R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("mom_ema34_summary.csv", index=False)
    Y = pd.DataFrame({k: v.resample("YE").last() for k, v in curves.items()}); YR = Y.pct_change(); YR.iloc[0] = Y.iloc[0] / CAP - 1
    YR.index = YR.index.year; print((YR * 100).round(1).to_string()); YR.to_csv("mom_ema34_yearly.csv")
