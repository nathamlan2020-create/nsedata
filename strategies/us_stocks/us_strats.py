"""
Candidate US strategies on the nsedata US archive (2001-2026), costs 0.15%/side, signals at the close,
trades at the next day's open.
 1. Momentum rotation: monthly, top N liquid stocks by 12-1 month return, equal weight;
    optional regime filter (S&P 500 above 200-day SMA, else cash).
 2. Pullback (mean reversion) in uptrends: liquid stock above 200-day SMA, 2-day RSI < 10 ->
    buy next open; sell next open after close > 5-day SMA or after 10 days; max 10 x 10%;
    only while S&P 500 > 200-day SMA.
Usage: python us_strats.py <stock_dir> <sp500_csv> <out_dir>
"""
import sys, os, glob, json
import numpy as np
import pandas as pd

SD, IDXF, OUT = sys.argv[1:4]
os.makedirs(OUT, exist_ok=True)
START, COST = "2001-01-01", 0.0015

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    return d[~d.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]

idx = load(IDXF)
dates = idx.index[idx.index >= pd.Timestamp("2000-01-01")]
cols = {k: {} for k in ("open", "close", "volume")}
for f in sorted(glob.glob(os.path.join(SD, "*.csv"))):
    if os.path.basename(f).startswith("_"):
        continue
    d = load(f); d = d[d.close > 0]
    if len(d) < 260:
        continue
    d = d.reindex(dates)
    for k in cols:
        cols[k][os.path.basename(f)[:-4]] = d[k].astype("float32")
O, C, V = (pd.DataFrame(cols[k]) for k in ("open", "close", "volume"))
del cols
r = C.pct_change(fill_method=None)
bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
O[bad] = np.nan; C[bad] = np.nan
syms = list(C.columns); col = {s: j for j, s in enumerate(syms)}
ic = idx.close.reindex(dates).ffill()
spx_up = ic > ic.rolling(200).mean()
turn = (C * V).rolling(20, min_periods=15).mean()
sma200 = C.rolling(200, min_periods=200).mean()
Cv, Ov = C.values, O.values
di = {d: i for i, d in enumerate(dates)}
dts = dates[dates >= pd.Timestamp(START)]

def px(i, s, field="o"):
    j = col[s]; v = (Ov if field == "o" else Cv)[i, j]
    if np.isnan(v):
        v = Cv[i, j]
    return v

# ---------------------------------------------------------------- 1. momentum rotation
mom = C.shift(21) / C.shift(252) - 1            # 12-1 month momentum
def momentum(top=10, liq=5e7, minpx=10, use_filter=True):
    cash, hold, curve, n_trades = 1.0, {}, [], 0
    month_ends = set(pd.Series(dts, index=dts).groupby([dts.year, dts.month]).max())
    pending = None
    for d in dts:
        i = di[d]
        if pending is not None:                       # execute at today's open
            target = pending; pending = None
            eq = cash + sum(sh * px(i, s) for s, sh in hold.items() if not np.isnan(px(i, s)))
            for s in list(hold):
                if s not in target:
                    p = px(i, s); p = p if not np.isnan(p) else 0
                    cash += hold.pop(s) * p * (1 - COST); n_trades += 1
            if target:
                w = eq / len(target)
                for s in target:                      # rebalance to equal weight
                    p = px(i, s)
                    if np.isnan(p):
                        continue
                    cur = hold.get(s, 0) * p
                    delta = w - cur
                    if delta > 0:
                        delta = min(delta, cash / (1 + COST)); cash -= delta * (1 + COST)
                    else:
                        cash += -delta * (1 - COST)
                    hold[s] = hold.get(s, 0) + delta / p
                    if s not in hold or cur == 0:
                        n_trades += 1
        val = cash + sum(sh * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else 0) for s, sh in hold.items())
        curve.append((d, val, len(hold)))
        if d in month_ends:
            if use_filter and not spx_up.iat[i]:
                pending = []
            else:
                ok = (turn.iloc[i] >= liq) & (C.iloc[i] >= minpx) & (C.iloc[i] > sma200.iloc[i]) & mom.iloc[i].notna()
                pending = list(mom.iloc[i][ok].nlargest(top).index)
    e = pd.DataFrame(curve, columns=["date", "equity", "npos"]).set_index("date")
    return e, n_trades

# ---------------------------------------------------------------- 2. pullback in uptrend
dlt = C.diff()
up, dn = dlt.clip(lower=0), (-dlt).clip(lower=0)
rsi2 = 100 - 100 / (1 + up.ewm(alpha=0.5, adjust=False).mean() / dn.ewm(alpha=0.5, adjust=False).mean())
sma5 = C.rolling(5).mean()
def pullback(liq=1e8, minpx=10, rsi_th=10, max_hold=10, max_pos=10, w=0.10, use_filter=True):
    sig = (C > sma200) & (rsi2 < rsi_th) & (turn >= liq) & (C >= minpx)
    exit_sig = C > sma5
    cash, pos, curve, trades = 1.0, {}, [], []
    buys, sells = [], set()
    for d in dts:
        i = di[d]
        for s in list(sells):
            if s in pos:
                p = pos.pop(s); x = px(i, s)
                cash += p["sh"] * x * (1 - COST)
                trades.append(x * (1 - COST) / (p["px"] * (1 + COST)) - 1)
        sells = set()
        eq = cash + sum(p["sh"] * (Cv[i - 1, col[s]] if not np.isnan(Cv[i - 1, col[s]]) else p["px"]) for s, p in pos.items())
        for s in buys:
            if len(pos) >= max_pos or s in pos:
                continue
            x = px(i, s)
            if np.isnan(x):
                continue
            val = min(w * eq, cash / (1 + COST))
            if val < 0.01 * eq:
                break
            cash -= val * (1 + COST); pos[s] = dict(sh=val / x, px=x, i=i)
        buys = []
        val = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
        curve.append((d, val, len(pos)))
        for s, p in pos.items():
            if exit_sig.iat[i, col[s]] or i - p["i"] >= max_hold:
                sells.add(s)
        if use_filter and not spx_up.iat[i]:
            continue
        free = max_pos - len(pos) + len(sells)
        if free > 0:
            row = sig.iloc[i]
            c = row[row.fillna(False)].index
            c = sorted([s for s in c if s not in pos], key=lambda s: rsi2.iat[i, col[s]])   # most oversold first
            buys = c[:free]
    e = pd.DataFrame(curve, columns=["date", "equity", "npos"]).set_index("date")
    return e, pd.Series(trades)

def stats(e, ntr=None, tr=None):
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = e / e.cummax() - 1; dr = e.pct_change().dropna()
    o = dict(cagr=e.iloc[-1] ** (1 / yrs) - 1, max_dd=dd.min(), sharpe=dr.mean() / dr.std() * np.sqrt(252))
    for n in (3, 10):
        s = e[e.index >= e.index[-1] - pd.DateOffset(years=n)]; o[f"cagr_{n}y"] = (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
    s = e.loc["2008-01-01":"2009-06-30"]; o["dd_2008"] = (s / s.cummax() - 1).min()
    s = e.loc["2022-01-01":"2022-12-31"]; o["ret_2022"] = s.iloc[-1] / s.iloc[0] - 1
    if tr is not None and len(tr):
        o["trades_yr"] = len(tr) / yrs; o["win"] = (tr > 0).mean(); o["avg_trade"] = tr.mean()
    if ntr is not None:
        o["trades_yr"] = ntr / yrs
    return o

if __name__ == "__main__":
    res, eqs = {}, {}
    bh = (ic / ic.loc[START:].iloc[0]).loc[START:]
    res["S&P 500 buy & hold"] = stats(bh); eqs["S&P 500 buy & hold"] = bh
    runs = {
        "Momentum top 10, S&P 200-DMA filter": lambda: momentum(10),
        "Momentum top 20, S&P 200-DMA filter": lambda: momentum(20),
        "Momentum top 10, no filter": lambda: momentum(10, use_filter=False),
        "Momentum top 10, $200M+ turnover (mega caps)": lambda: momentum(10, liq=2e8),
        "Pullback RSI(2)<10, S&P filter": lambda: pullback(),
        "Pullback RSI(2)<5, S&P filter": lambda: pullback(rsi_th=5),
        "Pullback RSI(2)<10, no filter": lambda: pullback(use_filter=False),
    }
    for k, f in runs.items():
        e, t = f()
        res[k] = stats(e.equity, ntr=t) if k.startswith("Mom") else stats(e.equity, tr=t)
        eqs[k] = e.equity
        o = res[k]
        print(f"{k:46s} CAGR {o['cagr']*100:5.1f}%  DD {o['max_dd']*100:6.1f}%  Sh {o['sharpe']:.2f}  3y {o['cagr_3y']*100:5.1f}%  10y {o['cagr_10y']*100:5.1f}%  "
              f"2008 {o['dd_2008']*100:5.1f}%  2022 {o['ret_2022']*100:5.1f}%  tr/yr {o.get('trades_yr',0):4.0f}  win {o.get('win',float('nan'))*100:3.0f}%", flush=True)
    o = res["S&P 500 buy & hold"]
    print(f"{'S&P 500 buy & hold':46s} CAGR {o['cagr']*100:5.1f}%  DD {o['max_dd']*100:6.1f}%  Sh {o['sharpe']:.2f}  3y {o['cagr_3y']*100:5.1f}%  10y {o['cagr_10y']*100:5.1f}%  2008 {o['dd_2008']*100:5.1f}%  2022 {o['ret_2022']*100:5.1f}%")
    pd.DataFrame(eqs).to_csv(os.path.join(OUT, "equity_all.csv"))
    json.dump(res, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=float)
    y = pd.DataFrame(eqs).resample("YE").last(); yr = y.pct_change(); yr.iloc[0] = y.iloc[0] - 1; yr.index = yr.index.year
    print((yr * 100).round(1).iloc[:, :3].join((yr * 100).round(1).iloc[:, 5:6]).to_string())
