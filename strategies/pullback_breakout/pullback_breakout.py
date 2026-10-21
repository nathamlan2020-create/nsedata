"""Pullback-breakout backtest, Nifty 500 daily (2007-2026, current constituents, adjusted prices).

Setup   : stock has fallen >= 11% from its 52-week high, and the deepest low since that high is no more than 22% below it
Trigger : close breaks above the highest high of the previous N days (N = 20 base case), still below the 52-week high
Entry   : at the signal day's close (= user's 3 PM price)
Exit    : stop-loss 3% below entry, target 5% above (intraday high/low; if both hit the same day, SL is assumed first);
          60-day time stop. Cost 0.20% round trip (delivery).
Filters : liquidity (20-day avg turnover > Rs 5 cr, price > 50); optional market filter Nifty 500 > its 50 EMA.
Portfolio: 10 slots x 10% of equity, signals taken in date order (highest turnover first).
"""
import glob, os, numpy as np, pandas as pd
from multiprocessing import Pool
D500 = "../n500"; COST = 0.002; TMAX = 60

def depth_series(h, l):
    """52w-high (252 bars) and deepest low since that high, computed with lows up to and including bar t."""
    n = len(h); pk = np.full(n, np.nan); mn = np.full(n, np.nan)
    pi = 0; m = l[0]
    for t in range(n):
        if t - pi >= 252:                       # old peak left the window -> recompute
            w0 = t - 251; pi = w0 + int(np.argmax(h[w0:t + 1])); m = l[pi + 1:t + 1].min() if pi < t else np.inf
        if h[t] >= h[pi]: pi = t; m = np.inf    # new high: reset the fall
        else: m = min(m, l[t])
        pk[t] = h[pi]; mn[t] = m
    return pk, mn

def run(args):
    f, N, fall_min, fall_max, sl, tp = args
    sym = os.path.basename(f).replace(".NS.csv", "")
    d = pd.read_csv(f, index_col=0, parse_dates=True).dropna(); d = d[d.volume > 0]
    if len(d) < 300: return []
    o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
    pk, mn = depth_series(h, l)
    depth_prev = np.r_[np.nan, (mn / pk - 1)[:-1]]          # deepest fall known before today
    hiN = pd.Series(h).rolling(N).max().shift(1).values
    turn = (d.close * d.volume).rolling(20).mean().values
    sig = (depth_prev <= -fall_min) & (depth_prev >= -fall_max) & (c > hiN) & (c < pk) & (turn > 5e7) & (c > 50)
    sig[:260] = False
    out = []; t = 0; idx = d.index
    while t < len(c) - 1:
        if not sig[t]: t += 1; continue
        en = c[t]; s, g = en * (1 - sl), en * (1 + tp); k = t + 1; ex = None
        while k < len(c):
            if o[k] <= s: ex = (k, o[k], "SL"); break           # gap below stop
            if o[k] >= g: ex = (k, o[k], "TP"); break           # gap above target
            if l[k] <= s: ex = (k, s, "SL"); break
            if h[k] >= g: ex = (k, g, "TP"); break
            if k - t >= TMAX: ex = (k, c[k], "time"); break
            k += 1
        if ex is None: break
        out.append(dict(sym=sym, t_in=idx[t], t_out=idx[ex[0]], ret=ex[1] / en - 1 - COST, why=ex[2],
                        bars=ex[0] - t, turn=turn[t], depth=depth_prev[t]))
        t = ex[0] + 1
    return out

def portfolio(T, slots=10):
    T = T.sort_values(["t_in", "turn"], ascending=[True, False])
    eq = 1.0; openp = []; curve = []
    for r in T.itertuples():
        still = []
        for p in openp:
            if p[0] < r.t_in: eq += p[1] * p[2]; curve.append((p[0], eq))
            else: still.append(p)
        openp = still
        if len(openp) >= slots or any(p[3] == r.sym for p in openp): continue
        openp.append((r.t_out, eq / slots, r.ret, r.sym))
    for p in sorted(openp, key=lambda x: x[0]): eq += p[1] * p[2]; curve.append((p[0], eq))
    s = pd.Series([v for _, v in curve], index=pd.to_datetime([x for x, _ in curve])).sort_index().groupby(level=0).last()
    yrs = (s.index[-1] - T.t_in.min()).days / 365.25
    yr = s.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] - 1
    return eq ** (1 / yrs) - 1, (s / s.cummax() - 1).min(), yret

if __name__ == "__main__":
    fs = [f for f in sorted(glob.glob(f"{D500}/*.NS.csv"))]
    ix = pd.read_csv(f"{D500}/IDX_CRSLDX.csv", index_col=0, parse_dates=True).close.dropna()
    bull = (ix > ix.ewm(span=50, adjust=False).mean())
    bh = ix[ix.index >= "2007-01-01"]; bh_cagr = (bh.iloc[-1] / bh.iloc[0]) ** (365.25 / (bh.index[-1] - bh.index[0]).days) - 1
    bh_dd = (bh / bh.cummax() - 1).min()
    tests = [("BASE 20D breakout, SL3 TP5", 20, .11, .22, .03, .05),
             ("10D breakout, SL3 TP5", 10, .11, .22, .03, .05),
             ("55D breakout, SL3 TP5", 55, .11, .22, .03, .05),
             ("20D, SL3 TP9 (1:3)", 20, .11, .22, .03, .09),
             ("20D, SL5 TP10", 20, .11, .22, .05, .10),
             ("20D, SL8 TP15", 20, .11, .22, .08, .15),
             ("CONTROL any 20D breakout (no fall rule), SL3 TP5", 20, 0.0, 1.0, .03, .05)]
    rows = []; yearly = {}
    with Pool(2) as p:
        for name, N, a, b, sl, tp in tests:
            T = pd.DataFrame([r for rr in p.map(run, [(f, N, a, b, sl, tp) for f in fs], chunksize=8) for r in rr])
            T = T[T.t_in >= "2007-01-01"]
            T["bull"] = bull.reindex(T.t_in, method="ffill").values.astype(bool)
            if name.startswith("BASE"): T.to_csv("pullback_breakout_trades.csv.gz", index=False)
            for flt, X in (("all", T), ("Nifty500>50EMA", T[T.bull])):
                cg, dd, yr = portfolio(X)
                if name.startswith("BASE"): yearly[flt] = yr
                rows.append(dict(test=name, market_filter=flt, trades=len(X), win=f"{(X.ret > 0).mean()*100:.0f}%",
                                 TP_hit=f"{(X.why == 'TP').mean()*100:.0f}%", avg=f"{X.ret.mean()*100:+.2f}%",
                                 pf=round(X.ret[X.ret > 0].sum() / -X.ret[X.ret < 0].sum(), 2), days=round(X.bars.mean(), 1),
                                 avg_07_15=f"{X[X.t_in < '2016'].ret.mean()*100:+.2f}%",
                                 avg_16_26=f"{X[X.t_in >= '2016'].ret.mean()*100:+.2f}%",
                                 CAGR=f"{cg*100:+.1f}%", maxDD=f"{dd*100:.0f}%", losing_yrs=f"{(yr < 0).sum()}/{len(yr)}"))
            print(name, "done", flush=True)
    R = pd.DataFrame(rows); pd.set_option("display.width", 250)
    print(R.to_string(index=False)); R.to_csv("pullback_breakout_summary.csv", index=False)
    print(f"\nNifty 500 buy & hold 2007-26: CAGR {bh_cagr*100:+.1f}%, maxDD {bh_dd*100:.0f}%")
    Y = pd.DataFrame(yearly) * 100; Y.index = Y.index.year
    print("\nBASE yearly returns %:\n", Y.round(1).T.to_string())
