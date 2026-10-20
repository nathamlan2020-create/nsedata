"""
3 PM breakout strategy backtest on any universe of daily CSVs.
Rules (user's live system):
  Market filter: index close > its 50 EMA (no new buys otherwise)
  Buy at the close: close > prior 52-week highest close, volume >= 1.5x prior 50-day average,
       close > 200-day SMA, 20-day average traded value >= LIQ, close >= MIN_PX;
       rank by 3-month return; max 10 positions of 10% equity each
  Sell: GTT stop -10% (intraday), close < prior 20-day lowest close, or
        market filter OFF and close below buy price. Costs 0.15% per side.
Usage: python bt3pm.py <stock_dir> <index_csv> <liq> <min_px> <label> <out_dir> [start] [cash_yield]
"""
import sys, os, glob, json
import numpy as np
import pandas as pd

SD, IDXF, LIQ, MINPX, LABEL, OUT = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6]
START = sys.argv[7] if len(sys.argv) > 7 else "2006-01-01"
CASH_Y = float(sys.argv[8]) if len(sys.argv) > 8 else 0.0
COST = 0.0015
os.makedirs(OUT, exist_ok=True)

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    d.columns = [c.lower() for c in d.columns]
    return d[~d.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]]

idx = load(IDXF)
dates = idx.index[idx.index >= pd.Timestamp(START) - pd.Timedelta(days=550)]
cols = {k: {} for k in ("open", "low", "close", "volume")}
n_files = 0
for f in sorted(glob.glob(os.path.join(SD, "*.csv"))):
    if os.path.basename(f).startswith(("_", "IDX_")):
        continue
    s = os.path.basename(f)[:-4]
    d = load(f)
    d = d[(d.close > 0) & (d.index >= dates[0])]
    if len(d) < 260:
        continue
    d = d.reindex(dates)
    for k in cols:
        cols[k][s] = d[k].astype("float32")
    n_files += 1
O, L, C, V = (pd.DataFrame(cols[k]) for k in ("open", "low", "close", "volume"))
del cols
r = C.pct_change(fill_method=None)
bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)       # one-day bad prints that reverse
for X in (O, L, C):
    X[bad] = np.nan
syms = list(C.columns)
print(f"{LABEL}: {n_files} stocks with >=1y history in window", flush=True)

hi52 = C.shift(1).rolling(252, min_periods=240).max()
vavg50 = V.shift(1).rolling(50, min_periods=40).mean()
sma200 = C.rolling(200, min_periods=200).mean()
turn20 = (C * V).rolling(20, min_periods=15).mean()
mom63 = C / C.shift(63) - 1
low20 = C.shift(1).rolling(20, min_periods=20).min()
ic = idx.close.reindex(dates).ffill()
mkt_on = ic > ic.ewm(span=50, adjust=False).mean()
entry_sig = (C > hi52) & (V >= 1.5 * vavg50) & (C > sma200) & (turn20 >= LIQ) & (C >= MINPX)
del hi52, vavg50, sma200

def run(max_pos=10, w=0.10, stop=0.10):
    dts = dates[dates >= pd.Timestamp(START)]
    di = {d: i for i, d in enumerate(dates)}
    col = {s: j for j, s in enumerate(syms)}
    Cv, Lv, Ov, L20, M63 = C.values, L.values, O.values, low20.values, mom63.values
    SIG = entry_sig.values
    cash, pos, curve, trades = 1.0, {}, [], []
    def sell(s, px, d, why):
        nonlocal cash
        p = pos.pop(s); cash += p["sh"] * px * (1 - COST)
        trades.append(dict(sym=s, entry_date=p["d"].date(), exit_date=d.date(), entry=round(float(p["px"]), 4),
                           exit=round(float(px), 4), ret=float(px * (1 - COST) / (p["px"] * (1 + COST)) - 1), why=why))
    def value(i):
        return cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["last"]) for s, p in pos.items())
    for d in dts:
        i = di[d]
        cash *= (1 + CASH_Y) ** (1 / 252)
        for s in list(pos):
            j = col[s]; sl = pos[s]["px"] * (1 - stop)
            if not np.isnan(Lv[i, j]) and Lv[i, j] <= sl:
                sell(s, min(Ov[i, j], sl) if not np.isnan(Ov[i, j]) else sl, d, "stop")
        for s in list(pos):
            j = col[s]; c = Cv[i, j]
            if np.isnan(c):
                continue
            pos[s]["last"] = c
            if c < L20[i, j]:
                sell(s, c, d, "trail")
            elif not mkt_on.iat[i] and c < pos[s]["px"]:
                sell(s, c, d, "filter_off")
        eq = value(i)
        if mkt_on.iat[i] and len(pos) < max_pos:
            js = np.where(SIG[i])[0]
            cands = [syms[j] for j in js if syms[j] not in pos]
            cands.sort(key=lambda s: -(M63[i, col[s]] if not np.isnan(M63[i, col[s]]) else -9))
            for s in cands[: max_pos - len(pos)]:
                px = Cv[i, col[s]]
                val = min(w * eq, cash / (1 + COST))
                if val < 0.01 * eq:
                    break
                cash -= val * (1 + COST)
                pos[s] = dict(sh=val / px, px=px, d=d, last=px)
        curve.append((d, value(i), len(pos)))
    return pd.DataFrame(curve, columns=["date", "equity", "npos"]).set_index("date"), pd.DataFrame(trades)

def stats(e, tr, bench):
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = e / e.cummax() - 1; dr = e.pct_change().dropna()
    b = bench.reindex(e.index).ffill(); b = b / b.iloc[0]
    o = dict(universe=LABEL, start=str(e.index[0].date()), end=str(e.index[-1].date()),
             cagr=e.iloc[-1] ** (1 / yrs) - 1, max_dd=dd.min(), sharpe=dr.mean() / dr.std() * np.sqrt(252),
             final_x=e.iloc[-1], bench_cagr=b.iloc[-1] ** (1 / yrs) - 1, bench_max_dd=(b / b.cummax() - 1).min())
    for n in (3, 5, 10):
        s = e[e.index >= e.index[-1] - pd.DateOffset(years=n)]; o[f"cagr_{n}y"] = (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
    w, l = tr[tr.ret > 0], tr[tr.ret <= 0]
    hold = (pd.to_datetime(tr.exit_date) - pd.to_datetime(tr.entry_date)).dt.days
    o.update(trades=len(tr), per_year=len(tr) / yrs, win_rate=len(w) / len(tr), avg_win=w.ret.mean(), avg_loss=l.ret.mean(),
             payoff=w.ret.mean() / abs(l.ret.mean()), med_hold_days=float(hold.median()))
    return o

if __name__ == "__main__":
    ec, tr = run()
    st = stats(ec.equity, tr, ic)
    ye = ec.equity.resample("YE").last(); yr = ye.pct_change(); yr.iloc[0] = ye.iloc[0] - 1
    by = ic.reindex(ec.index).resample("YE").last(); byr = by.pct_change(); byr.iloc[0] = by.iloc[0] / ic.reindex(ec.index).iloc[0] - 1
    st["yearly"] = {int(k.year): [round(float(a), 4), round(float(b), 4)] for k, a, b in zip(yr.index, yr.values, byr.values)}
    ec.to_csv(os.path.join(OUT, "equity.csv")); tr.to_csv(os.path.join(OUT, "trades.csv"), index=False)
    json.dump(st, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=float)
    for k, v in st.items():
        if k != "yearly":
            print(f"  {k:14s} {v:.4f}" if isinstance(v, float) else f"  {k:14s} {v}")
    print("  yearly (strategy, index):", {k: (round(a * 100, 1), round(b * 100, 1)) for k, (a, b) in st["yearly"].items()})
