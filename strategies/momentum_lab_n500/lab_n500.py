"""'Momentum backtest lab' rules re-run on the Nifty 500 (clean data, current constituents), Oct 2006 - Oct 2026.
Part A  daily timing of the Nifty 500 index: signal on today's close, trade at the next close, 0.10% per switch,
        6%/yr (liquid fund / T-bill proxy) when out. Price index (no dividends).
Part B  monthly stock momentum: signals on the last trading day of the month at the close, 0.20% per trade,
        6%/yr on idle cash. Trend filter = Nifty 500 above its 10-month average of month-end closes.
        Eligible: price > 50, 20-day turnover > Rs 5 cr, >= 13 months history.  Tax (STCG 20% / LTCG 12.5% > 1.25L + cess)
        computed for the stock strategies on Rs 5 lakh."""
import numpy as np, pandas as pd
import momentum_rotation as M
START = pd.Timestamp("2006-10-01"); RF = 0.06; LIQ = RF / 252
ic = M.ic; Cf = M.Cf; days = M.dates[M.dates >= START]

def stats(e, inv=None, rt=None, win=None, turn=None):
    yrs = (e.index[-1] - e.index[0]).days / 365.25; dr = e.pct_change().dropna()
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1; dd = (e / e.cummax() - 1).min(); vol = dr.std() * np.sqrt(252)
    yr = e.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] / e.iloc[0] - 1
    return dict(CAGR=cagr * 100, vol=vol * 100, sharpe=(dr.mean() * 252 - RF) / vol, maxDD=dd * 100, cagr_dd=cagr / -dd,
                worst_yr=yret.min() * 100, rt_yr=rt / yrs if rt is not None else np.nan, win=win, turn_yr=turn / yrs if turn is not None else np.nan,
                invested=inv)

# ---------------- Part A: index timing ----------------
c = ic.reindex(M.dates)
sma = lambda n: c.rolling(n).mean(); ema = lambda n: c.ewm(span=n, adjust=False).mean()
me = c.groupby(c.index.to_period("M")).transform("last"); is_me = c.index.isin(c.groupby(c.index.to_period("M")).tail(1).index)
mc = c[is_me]; m10 = mc.rolling(10).mean()
monthly10 = pd.Series(np.nan, index=c.index); monthly10[is_me] = (mc > m10).astype(float); monthly10 = monthly10.ffill()
def band(lo_hi):
    up, dn = lo_hi; s = pd.Series(np.nan, index=c.index); s[up] = 1; s[dn] = 0; return s.ffill().fillna(0)
rf_n = lambda n: (1 + RF) ** (n / 252) - 1
rsi = (lambda d: 100 - 100 / (1 + d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean() / (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()))(c.diff())
don = band((c >= c.shift(1).rolling(100).max(), c <= c.shift(1).rolling(50).min()))
RULES = {"Buy & hold Nifty 500": pd.Series(1.0, index=c.index),
         "Price > 200-day SMA": (c > sma(200)).astype(float),
         "Price > 200-day SMA with 2% band": band((c > sma(200) * 1.02, c < sma(200) * 0.98)),
         "Price > 50-day EMA (your filter)": (c > ema(50)).astype(float),
         "Golden cross 50/200 SMA": (sma(50) > sma(200)).astype(float),
         "Crossover 20/50 SMA": (sma(20) > sma(50)).astype(float),
         "Crossover 10/30 EMA": (ema(10) > ema(30)).astype(float),
         "12-month momentum (252d return > 6%)": (c / c.shift(252) - 1 > rf_n(252)).astype(float),
         "6-month momentum (126d return > 3%)": (c / c.shift(126) - 1 > rf_n(126)).astype(float),
         "Donchian: buy 100d high, sell 50d low": don,
         "RSI(14) > 50": (rsi > 50).astype(float),
         "Monthly: price > 10-month SMA": monthly10}
A = []; acurves = {}
r = c.pct_change().reindex(days).fillna(0)
for name, sig in RULES.items():
    pos = sig.shift(1).reindex(days).fillna(0)                       # decided at yesterday's close, trade at today's close... held from next bar
    pos = sig.shift(2).reindex(days).fillna(0) if name != "Buy & hold Nifty 500" else pd.Series(1.0, index=days)
    sw = pos.diff().abs().fillna(0)
    dr = pos * r + (1 - pos) * LIQ - sw * 0.0010
    e = (1 + dr).cumprod(); acurves[name] = e
    # trades: entries/exits
    ent = days[(pos.diff() == 1).values]; ex = days[(pos.diff() == -1).values]
    tr = []
    for d0 in ent:
        d1 = ex[ex > d0]; d1 = d1[0] if len(d1) else days[-1]
        tr.append(e.loc[d1] / e.loc[d0] - 1)
    s = stats(e, inv=pos.mean() * 100, rt=len(ent), win=(np.array(tr) > 0).mean() * 100 if tr else np.nan)
    A.append(dict(rule=name, **s))
A = pd.DataFrame(A)

# ---------------- Part B: monthly stock momentum ----------------
def fy(t): return t.year + 1 if t.month >= 4 else t.year
last = pd.Series(days, index=days).groupby(days.to_period("M")).last().values; LAST = set(last)
T10 = monthly10                                                   # filter state at each month end
hist = Cf.notna().cumsum() >= 253                                  # 12 months + 1 day (data starts Sep 2005)
EL = M.elig & hist
SCORE = {"12-1": Cf.shift(21) / Cf.shift(252) - 1, "6-1": Cf.shift(21) / Cf.shift(126) - 1,
         "52wk-high proximity": Cf / Cf.rolling(252).max(), "blend 3/6/12 (yours)": M.SC["blend"]}
ABS12 = Cf.shift(21) / Cf.shift(252) - 1
TOP200 = (M.C * M.V).rolling(126, min_periods=60).mean().where(EL).rank(axis=1, ascending=False) <= 200
CAP = 5e5; COST = 0.0020

def simB(score="12-1", N=50, keep=None, flt=None, absmom=False, univ="n500", ew=False, tax=False, daily50=False):
    S = SCORE[score]; keep = keep or N
    cash = CAP; pos = {}; vals = []; inv = []; st = lt = cfs = cfl = 0.0; cur = fy(days[0]); traded = 0.0
    def sell(s, px, t, frac=1.0):
        nonlocal cash, st, lt, traded
        sh, cost, d0 = pos[s]; q = sh * frac; pr = q * px * (1 - COST); cash += pr; g = pr - cost * frac; traded += q * px
        if (t - d0).days >= 365: lt += g
        else: st += g
        if frac >= 1: pos.pop(s)
        else: pos[s] = [sh - q, cost * (1 - frac), d0]
    def buy(s, amt, px, t):
        nonlocal cash, traded
        if amt <= 0: return
        if s in pos: sh, cost, d0 = pos[s]; pos[s] = [sh + amt * (1 - COST) / px[s], cost + amt, d0]
        else: pos[s] = [amt * (1 - COST) / px[s], amt, t]
        cash -= amt; traded += amt
    E50 = M.FLT["50EMA->cash"]
    for t in days:
        px = Cf.loc[t]
        if tax and fy(t) != cur:
            S_, L_ = st + cfs, lt + cfl
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cfs, cfl = min(S_, 0), min(L_, 0)
            cash -= (max(S_, 0) * 0.20 + max(max(L_, 0) - 125000, 0) * 0.125) * 1.04
            st = lt = 0.0; cur = fy(t)
        cash += max(cash, 0) * LIQ
        if daily50 and pos and not E50.loc[t]:
            for s in list(pos): sell(s, px[s], t)
        if t in LAST or (daily50 and E50.loc[t] and not pos and t != days[0] and not E50.shift(1).loc[t]):
            on = True
            if flt == "10M": on = bool(T10.loc[t] == 1)
            if daily50: on = bool(E50.loc[t])
            if not on:
                for s in list(pos): sell(s, px[s], t)
            else:
                el = EL.loc[t] & (TOP200.loc[t] if univ == "n200" else True)
                eq = cash + sum(p[0] * px[s] for s, p in pos.items())
                if ew:
                    names = list(el[el].index); tgt = eq / max(len(names), 1)
                    for s in [s for s in pos if s not in names]: sell(s, px[s], t)
                    for s in names:
                        v = pos[s][0] * px[s] if s in pos else 0
                        if v > tgt * 1.0001: sell(s, px[s], t, (v - tgt) / v)
                    for s in names:
                        v = pos[s][0] * px[s] if s in pos else 0
                        if v < tgt: buy(s, min(tgt - v, cash), px, t)
                else:
                    sc = S.loc[t].where(el).dropna()
                    if absmom: sc = sc[ABS12.loc[t].reindex(sc.index) > 0]
                    sc = sc.sort_values(ascending=False); ok = set(sc.index[:keep])
                    for s in [s for s in pos if s not in ok]: sell(s, px[s], t)
                    eq = cash + sum(p[0] * px[s] for s, p in pos.items())
                    for s in sc.index[:N]:
                        if len(pos) >= N: break
                        if s not in pos: buy(s, min(eq / N, cash), px, t)
        eqv = cash + sum(p[0] * px[s] for s, p in pos.items()); vals.append(eqv); inv.append(1 - max(cash, 0) / eqv)
    e = pd.Series(vals, index=days)
    return e, np.mean(inv) * 100, traded / e.mean()

V = [("Equal-weight all eligible Nifty 500 (survivors)", dict(ew=True)),
     ("12-1 momentum: top 50", dict(score="12-1", N=50)),
     ("6-1 momentum: top 50", dict(score="6-1", N=50)),
     ("52-week-high proximity: top 50", dict(score="52wk-high proximity", N=50)),
     ("Dual momentum: 12-1 top 50 + 10M trend filter", dict(score="12-1", N=50, flt="10M")),
     ("Dual momentum: 12-1 top 20 + 10M trend filter", dict(score="12-1", N=20, flt="10M")),
     ("12-1 top 50, each stock abs. momentum > 0", dict(score="12-1", N=50, absmom=True)),
     ("LAB RECOMMENDED: 12-1 top 20, keep 40, 10M filter", dict(score="12-1", N=20, keep=40, flt="10M")),
     ("Lab recommended on Nifty 200 proxy", dict(score="12-1", N=20, keep=40, flt="10M", univ="n200")),
     ("YOUR MODEL: blend top 20, keep 40, daily 50 EMA", dict(score="blend 3/6/12 (yours)", N=20, keep=40, daily50=True)),
     ("Your blend score + lab's 10M filter (monthly)", dict(score="blend 3/6/12 (yours)", N=20, keep=40, flt="10M"))]
B = []; bcurves = {}
for name, kw in V:
    e, inv, tv = simB(**kw); et, _, _ = simB(**kw, tax=True); bcurves[name] = e
    s = stats(e, inv=inv, turn=tv); st_ = stats(et)
    B.append(dict(strategy=name, **s, CAGR_after_tax=st_["CAGR"], maxDD_after_tax=st_["maxDD"], final_after_tax_L=et.iloc[-1] / 1e5))
    print(name, f"{s['CAGR']:.1f} {s['maxDD']:.1f} | AT {st_['CAGR']:.1f}", flush=True)
B = pd.DataFrame(B)
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30)
print(A.round(2).to_string(index=False)); print(B.round(2).to_string(index=False))
A.round(2).to_csv("lab_n500_index_timing.csv", index=False); B.round(2).to_csv("lab_n500_stock_momentum.csv", index=False)
pd.DataFrame({**acurves, **bcurves}).to_csv("lab_n500_equity.csv.gz")
# 2008-09 per-year return for the headline
for k in ("12-1 momentum: top 50", "LAB RECOMMENDED: 12-1 top 20, keep 40, 10M filter", "YOUR MODEL: blend top 20, keep 40, daily 50 EMA"):
    e = bcurves[k]; x = e[(e.index >= "2008-01-01") & (e.index <= "2009-12-31")]; print(k, "2008-09 p.a.", round(((x.iloc[-1] / x.iloc[0]) ** 0.5 - 1) * 100, 1))
