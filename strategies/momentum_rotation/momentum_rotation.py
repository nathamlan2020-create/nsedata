"""Monthly momentum rotation on Nifty 500 (current constituents, adjusted daily data), 2007-2026.

Each month (first trading day, at the close = 3 PM proxy) rank eligible stocks by a momentum score, hold the top N equally.
Scores : 6M   = 126-day return
         12-1M = 252-day return skipping the last 21 days
         6M/vol = 126-day return / 126-day daily volatility
         blend = average rank of 3M, 6M, 12M returns
Holdings: N = 10 or 20.  'buffer' keeps a holding until it falls out of the top 2N (less churn).
Market filter (checked every day at the close on Nifty 500):
         none | 50EMA->cash (sell all when N500 < 50 EMA, buy back the top N the day it turns back on)
         200DMA->cash | 50EMA user-rule (when off: sell only positions below their buy price, no new buys)
Eligibility: price > 50, 20-day avg turnover > Rs 5 cr.  Costs 0.15% per side.  Idle cash earns 0.
Compared on the same dates with the user's 3 PM breakout equity curve (strategies/3pm_vs_heikin_ashi).
"""
import glob, os, sys, json, numpy as np, pandas as pd
D = "../n500"; COST = 0.0015; START = "2007-01-01"
TPM = "/home/claude/nsedata/strategies/3pm_vs_heikin_ashi/results/equity_all.csv"

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    return d[~d.index.duplicated()].sort_index()[["close", "volume"]].astype(float)
idx = load(f"{D}/IDX_CRSLDX.csv").close
dates = idx.index[idx.index >= "2005-06-01"]
C, V = {}, {}
for f in glob.glob(f"{D}/*.NS.csv"):
    s = os.path.basename(f)[:-7]; d = load(f); d = d[d.close > 0].reindex(dates); C[s], V[s] = d.close, d.volume
C, V = pd.DataFrame(C), pd.DataFrame(V)
r = C.pct_change(fill_method=None)
C[(r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)] = np.nan          # bad ticks
Cf = C.ffill()
ret1 = Cf.pct_change(fill_method=None)
turn = (C * V).rolling(20, min_periods=10).mean()
elig = (C > 50) & (turn > 5e7) & C.notna()
vol126 = ret1.rolling(126).std()
SC = {"6M": Cf / Cf.shift(126) - 1,
      "12-1M": Cf.shift(21) / Cf.shift(252) - 1,
      "6M/vol": (Cf / Cf.shift(126) - 1) / vol126,
      "blend": sum((Cf / Cf.shift(k) - 1).rank(axis=1, pct=True) for k in (63, 126, 252)) / 3}
ic = idx.reindex(dates).ffill()
FLT = {"none": pd.Series(True, index=dates),
       "50EMA->cash": ic > ic.ewm(span=50, adjust=False).mean(),
       "200DMA->cash": ic > ic.rolling(200).mean(),
       "50EMA user-rule": ic > ic.ewm(span=50, adjust=False).mean()}
days = dates[dates >= START]
first = pd.Series(days, index=days).groupby(days.to_period("M")).first().values

def sim(score, N, buffer, flt):
    S = SC[score]; on = FLT[flt]; cashrule = flt.endswith("cash")
    cash, pos, eq, trades = 1.0, {}, [], 0                 # pos: sym -> [shares, buy price]
    was_on = True
    for t in days:
        px = Cf.loc[t]
        f_on = bool(on.loc[t])
        reb = t in first
        if not f_on:
            if cashrule and pos:                            # go to cash
                for s, (sh, bp) in pos.items(): cash += sh * px[s] * (1 - COST); trades += 1
                pos = {}
            elif flt == "50EMA user-rule":                  # sell only losers
                for s in [s for s, (sh, bp) in pos.items() if px[s] < bp]:
                    cash += pos[s][0] * px[s] * (1 - COST); del pos[s]; trades += 1
        if f_on and (reb or (cashrule and not was_on)):
            sc = S.loc[t].where(elig.loc[t]).dropna().sort_values(ascending=False)
            keep_rank = 2 * N if buffer else N
            top = list(sc.index[:N]); ok = set(sc.index[:keep_rank])
            for s in [s for s in pos if s not in ok]:
                cash += pos[s][0] * px[s] * (1 - COST); del pos[s]; trades += 1
            equity = cash + sum(sh * px[s] for s, (sh, bp) in pos.items())
            for s in top:
                if len(pos) >= N: break
                if s in pos: continue
                amt = min(equity / N, cash)
                if amt <= 0: break
                pos[s] = [amt * (1 - COST) / px[s], px[s]]; cash -= amt; trades += 1
        elif not f_on and reb and flt == "50EMA user-rule":
            sc = S.loc[t].where(elig.loc[t]).dropna().sort_values(ascending=False)
            ok = set(sc.index[:(2 * N if buffer else N)])
            for s in [s for s in pos if s not in ok]:
                cash += pos[s][0] * px[s] * (1 - COST); del pos[s]; trades += 1
        was_on = f_on
        eq.append(cash + sum(sh * px[s] for s, (sh, bp) in pos.items()))
    return pd.Series(eq, index=days), trades

def stats(e):
    yrs = (e.index[-1] - e.index[0]).days / 365.25; dr = e.pct_change().dropna()
    def cg(k): x = e[e.index >= e.index[-1] - pd.DateOffset(years=k)]; return (x.iloc[-1] / x.iloc[0]) ** (1 / k) - 1
    yr = e.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] / e.iloc[0] - 1
    return dict(CAGR=(e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1, maxDD=(e / e.cummax() - 1).min(),
                sharpe=dr.mean() / dr.std() * np.sqrt(252), cagr_3y=cg(3), cagr_5y=cg(5), cagr_10y=cg(10),
                losing_yrs=f"{(yret < 0).sum()}/{len(yret)}", worst_yr=yret.min())

if __name__ == "__main__":
    rows, curves = [], {}
    for score in SC:
        for N in (10, 20):
            for buf in (False, True):
                for flt in FLT:
                    e, tr = sim(score, N, buf, flt)
                    name = f"{score} top{N}{' buffer' if buf else ''} | {flt}"
                    curves[name] = e
                    rows.append(dict(strategy=name, **stats(e), trades_per_yr=tr / ((e.index[-1] - e.index[0]).days / 365.25)))
                    print(name, f"{rows[-1]['CAGR']*100:.1f}% {rows[-1]['maxDD']*100:.0f}%", flush=True)
    ref = pd.read_csv(TPM, index_col=0, parse_dates=True)
    for col in ("3 PM breakout", "Nifty 500"):
        e = ref[col].reindex(days).ffill().dropna(); curves[col] = e
        rows.append(dict(strategy=f"REF {col}", **stats(e)))
    R = pd.DataFrame(rows)
    best = R[~R.strategy.str.startswith("REF")].assign(score=lambda x: x.CAGR / -x.maxDD).sort_values("score", ascending=False)
    b = best.strategy.iloc[0]
    tp = curves["3 PM breakout"]; m = curves[b].reindex(tp.index).ffill()
    blend = (0.5 * tp.pct_change() + 0.5 * m.pct_change()).fillna(0).add(1).cumprod()
    rows.append(dict(strategy=f"BLEND 50/50 3 PM + [{b}]", **stats(blend)))
    corr = tp.pct_change().corr(m.pct_change())
    R = pd.DataFrame(rows)
    out = R.copy()
    for k in ("CAGR", "maxDD", "cagr_3y", "cagr_5y", "cagr_10y", "worst_yr"): out[k] = (out[k] * 100).round(1)
    out["sharpe"] = out.sharpe.round(2); out["trades_per_yr"] = out.trades_per_yr.round(0)
    out.to_csv("momentum_rotation_summary.csv", index=False)
    pd.DataFrame(curves).to_csv("momentum_rotation_equity.csv.gz")
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
    print(out.sort_values("CAGR", ascending=False).to_string(index=False))
    print(f"\nbest CAGR/DD: {b}; daily-return correlation with 3 PM = {corr:.2f}")
