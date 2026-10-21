"""3 PM breakout robustness: execution delay x liquidity, same rules/costs as strategies/3pm_vs_heikin_ashi/compare.py.

Rules (unchanged): entry when close > prior 52w high close, volume >= 1.5x 50-day avg, close > 200 SMA, 20d turnover >= T,
market on (Nifty 500 > 50 EMA); rank by 63-day momentum; max 10 positions x 10%; exits: 10% GTT stop (intraday),
close < prior 20-day low close, and (market off & close < buy price). Costs 0.15%/side.

Execution modes:
  same close  : decide and trade at the 3 PM price (the backtest as before)
  next open   : decide on today's close, trade at tomorrow's open
  next close  : decide on today's close, trade at tomorrow's close (full 1-day delay)
The GTT stop is always intraday on the day it is hit (it is a resting order).
"""
import glob, os, sys, numpy as np, pandas as pd
D = "../n500"; START, COST = "2006-01-01", 0.0015

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    return d[~d.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]].astype(float)
idx = load(f"{D}/IDX_CRSLDX.csv")
dates = idx.index[idx.index >= pd.Timestamp(START) - pd.Timedelta(days=500)]
O, L, C, V = {}, {}, {}, {}
for f in glob.glob(f"{D}/*.NS.csv"):
    s = os.path.basename(f)[:-7]; d = load(f); d = d[d.close > 0].reindex(dates)
    O[s], L[s], C[s], V[s] = d.open, d.low, d.close, d.volume
O, L, C, V = (pd.DataFrame(x) for x in (O, L, C, V))
r = C.pct_change(fill_method=None); bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
for X in (O, L, C): X[bad] = np.nan
syms = list(C.columns)
hi52 = C.shift(1).rolling(252, min_periods=240).max(); vavg50 = V.shift(1).rolling(50, min_periods=40).mean()
sma200 = C.rolling(200, min_periods=200).mean(); turn20 = (C * V).rolling(20, min_periods=15).mean()
mom63 = C / C.shift(63) - 1; low20 = C.shift(1).rolling(20, min_periods=20).min()
ic = idx.close.reindex(dates); mkt_on = ic > ic.ewm(span=50, adjust=False).mean()
base_sig = (C > hi52) & (V >= 1.5 * vavg50) & (C > sma200)

def run(mode="same close", tmin=5e7, max_pos=10, w=0.10, stop=0.10):
    sig = (base_sig & (turn20 >= tmin)).values
    dts = dates[dates >= pd.Timestamp(START)]; di = {d: i for i, d in enumerate(dates)}; col = {s: j for j, s in enumerate(syms)}
    Cv, Lv, Ov, L20, M63 = C.values, L.values, O.values, low20.values, mom63.values; MK = mkt_on.values
    lag = 0 if mode == "same close" else 1
    cash, pos, curve, trades = 1.0, {}, [], []
    def fill(i, j):                                        # execution price on bar i
        if mode == "next open":
            p = Ov[i, j]; return p if not np.isnan(p) else Cv[i, j]
        return Cv[i, j]
    def sell(s, px, d, why):
        nonlocal cash
        p = pos.pop(s); cash += p["sh"] * px * (1 - COST)
        trades.append(dict(sym=s, entry_date=p["d"], exit_date=d, ret=px * (1 - COST) / (p["px"] * (1 + COST)) - 1, why=why))
    for d in dts:
        i = di[d]; k = i - lag                              # k = bar on which the decision is made
        for s in list(pos):                                 # GTT stop, intraday, no delay
            j = col[s]; sl = pos[s]["px"] * (1 - stop)
            if not np.isnan(Lv[i, j]) and Lv[i, j] <= sl:
                op = Ov[i, j]; sell(s, min(op, sl) if not np.isnan(op) else sl, d, "stop")
        for s in list(pos):                                 # close-based exits decided on bar k
            j = col[s]; c = Cv[k, j]
            if np.isnan(c) or pos[s]["i"] > k: continue    # bought after the decision bar
            px = fill(i, j)
            if np.isnan(px): continue
            if c < L20[k, j]: sell(s, px, d, "trail")
            elif not MK[k] and c < pos[s]["px"]: sell(s, px, d, "filter_off")
        eq = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
        if MK[k] and len(pos) < max_pos:
            cands = [syms[j] for j in np.flatnonzero(sig[k]) if syms[j] not in pos]
            cands.sort(key=lambda s: -(M63[k, col[s]] if not np.isnan(M63[k, col[s]]) else -9))
            for s in cands[: max_pos - len(pos)]:
                px = fill(i, col[s])
                if np.isnan(px): continue
                val = min(w * eq, cash / (1 + COST))
                if val < 0.01 * eq: break
                cash -= val * (1 + COST); pos[s] = dict(sh=val / px, px=px, d=d, i=i)
        eq = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
        curve.append((d, eq))
    e = pd.Series([v for _, v in curve], index=[d for d, _ in curve])
    return e, pd.DataFrame(trades)

def stats(e, tr):
    yrs = (e.index[-1] - e.index[0]).days / 365.25; dr = e.pct_change().dropna()
    def cg(n): s = e[e.index >= e.index[-1] - pd.DateOffset(years=n)]; return (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
    yr = e.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] - 1
    return dict(CAGR=e.iloc[-1] ** (1 / yrs) - 1, maxDD=(e / e.cummax() - 1).min(), sharpe=dr.mean() / dr.std() * np.sqrt(252),
                cagr_3y=cg(3), cagr_10y=cg(10), trades_yr=len(tr) / yrs, win=(tr.ret > 0).mean(), avg=tr.ret.mean(),
                losing_yrs=f"{(yret < 0).sum()}/{len(yret)}")

if __name__ == "__main__":
    rows = []
    for tmin, tl in ((5e7, ">5 cr (as now)"), (5e8, ">50 cr"), (2e9, ">200 cr")):
        for mode in ("same close", "next open", "next close"):
            e, tr = run(mode, tmin); s = stats(e, tr)
            rows.append(dict(liquidity=tl, execution=mode, **s)); print(tl, mode, f"{s['CAGR']*100:.1f}% {s['maxDD']*100:.0f}%", flush=True)
    R = pd.DataFrame(rows)
    for k in ("CAGR", "maxDD", "cagr_3y", "cagr_10y", "win", "avg"): R[k] = (R[k] * 100).round(1)
    R["sharpe"] = R.sharpe.round(2); R["trades_yr"] = R.trades_yr.round(0)
    pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("pm3_robust_summary.csv", index=False)
