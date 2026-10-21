"""3-month consolidation -> fall below the range -> breakout above the range. SL 3%, trailing exit. Several timeframes.

Pattern (same calendar length on every timeframe; L = bars in ~3 months):
  base   : last L bars' range (max high / min low - 1) <= W (20%); base top/bottom = that window's high/low (latest qualifying window)
  fall   : a close below the base bottom (deepest low must stay within 30% of the bottom)
  signal : within the next L bars, a close above the base top -> enter at that close
           (a breakout above the top without the fall first is ignored and the base is discarded)
Exit   : hard stop 3% below entry; trailing stop = highest high since entry x (1 - trail) for trail 5/10/15%,
         or 'EMA20' = exit next bar open after a close below the 20-bar EMA.  Gaps through stops fill at the open.
Costs  : 0.20% round trip.  Portfolio: 10 slots x 10% equity, optional Nifty 500 > 50-day EMA filter at entry.
Universes: 33 Nifty 50 stocks (Kite 1-min 2015-26 -> 15m, 60m, daily) and Nifty 500 (daily, weekly 2007-26).
"""
import glob, os, sys, numpy as np, pandas as pd
from multiprocessing import Pool
COST, SL, W, MAXFALL = 0.002, 0.03, 0.20, 0.30
EXITS = ("trail5", "trail10", "trail15", "EMA20")
K1 = "../n50/stocks"; N500 = "../n500"

def load(sym, tf):
    if tf in ("15m", "60m", "D_kite"):
        d = pd.read_csv(f"{K1}/{sym}.csv.gz", index_col=0, parse_dates=True)
        t = d.index.hour * 100 + d.index.minute; d = d[(t >= 915) & (t <= 1529)]
        rule = {"15m": "15min", "60m": "60min", "D_kite": "1D"}[tf]
        kw = dict(origin="start_day", offset="9h15min") if tf != "D_kite" else {}
        return d.resample(rule, label="left", **kw).agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                                          "volume": "sum"}).dropna()
    d = pd.read_csv(f"{N500}/{sym}.NS.csv", index_col=0, parse_dates=True).dropna(); d = d[d.volume > 0]
    if tf == "W":
        d = d.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return d

L_BARS = {"15m": 63 * 25, "60m": 63 * 7, "D_kite": 63, "D": 63, "W": 13}

def run(a):
    sym, tf, w = a
    try: d = load(sym, tf)
    except Exception: return []
    L = L_BARS[tf]
    if len(d) < 3 * L: return []
    o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
    hh = pd.Series(h).rolling(L).max().values; ll = pd.Series(l).rolling(L).min().values
    qual = (hh / ll - 1) <= w
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().values
    day = d.index.normalize()
    dv = pd.Series(c * d.volume.values, index=d.index).groupby(day).transform("sum")       # daily turnover
    dturn = dv.groupby(day).first().rolling(20).mean().reindex(day).values
    if tf == "W": dturn = (pd.Series(c * d.volume.values).rolling(4).mean() / 5).values
    out = []; state = 0; top = bot = 0.0; fall_t = 0; t = L; n = len(c)
    while t < n - 1:
        sig = False
        if state == 0 and qual[t]: state, top, bot = 1, hh[t], ll[t]
        elif state == 1:
            if qual[t]: top, bot = hh[t], ll[t]                 # base still forming -> keep latest window
            elif c[t] > top: state = 0                          # breakout without a fall -> ignore
            elif c[t] < bot: state, fall_t = 2, t
        elif state == 2:
            if l[t] < bot * (1 - MAXFALL) or t - fall_t > L: state = 0
            elif c[t] > top: sig = True; state = 0
        if not sig or not (dturn[t] > 5e7 and c[t] > 50): t += 1; continue
        en = c[t]; res = {}
        for ex in EXITS:
            stop = en * (1 - SL); pkh = en; k = t + 1; r = None
            tr = {"trail5": .05, "trail10": .10, "trail15": .15}.get(ex)
            while k < n:
                if tr: stop = max(stop, pkh * (1 - tr))
                if o[k] <= stop: r = (k, o[k]); break
                if l[k] <= stop: r = (k, stop); break
                if ex == "EMA20" and c[k] < ema[k] and k + 1 < n: r = (k + 1, o[k + 1]); break
                pkh = max(pkh, h[k]); k += 1
            if r is None: r = (n - 1, c[-1])
            res[ex] = (r[1] / en - 1 - COST, d.index[r[0]], r[0] - t)
        out.append(dict(sym=sym, tf=tf, W=w, t_in=d.index[t], turn=dturn[t],
                        **{f"ret_{e}": res[e][0] for e in EXITS}, **{f"out_{e}": res[e][1] for e in EXITS},
                        **{f"bars_{e}": res[e][2] for e in EXITS}))
        t += 1
    return out

def portfolio(T, ex, slots=10):
    T = T.sort_values(["t_in", "turn"], ascending=[True, False])
    eq = 1.0; openp = []; curve = []
    for r in T.itertuples():
        still = []
        for p in openp:
            if p[0] <= r.t_in: eq += p[1] * p[2]; curve.append((p[0], eq))
            else: still.append(p)
        openp = still
        if len(openp) >= slots or any(p[3] == r.sym for p in openp): continue
        openp.append((getattr(r, f"out_{ex}"), eq / slots, getattr(r, f"ret_{ex}"), r.sym))
    for p in sorted(openp, key=lambda x: x[0]): eq += p[1] * p[2]; curve.append((p[0], eq))
    s = pd.Series([v for _, v in curve], index=pd.to_datetime([x for x, _ in curve])).sort_index().groupby(level=0).last()
    yrs = (s.index[-1] - T.t_in.min()).days / 365.25
    yr = s.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] - 1
    return eq ** (1 / yrs) - 1, (s / s.cummax() - 1).min(), (yret < 0).sum(), len(yret)

if __name__ == "__main__":
    k33 = [os.path.basename(f).split(".")[0] for f in glob.glob(f"{K1}/*.csv.gz")]
    n500 = [os.path.basename(f)[:-7] for f in glob.glob(f"{N500}/*.NS.csv")]
    jobs = [(s, tf, W) for tf in ("15m", "60m", "D_kite") for s in k33] + [(s, tf, w) for tf in ("D", "W") for s in n500
                                                                         for w in ((0.15, 0.20, 0.25) if tf == "D" else (W,))]
    with Pool(2) as p: res = p.map(run, jobs, chunksize=4)
    T = pd.DataFrame([r for rr in res for r in rr])
    for e in EXITS: T[f"out_{e}"] = pd.to_datetime(T[f"out_{e}"])
    ix = pd.read_csv(f"{N500}/IDX_CRSLDX.csv", index_col=0, parse_dates=True).close.dropna()
    bull = ix > ix.ewm(span=50, adjust=False).mean()
    T["bull"] = bull.reindex(T.t_in.dt.normalize(), method="ffill").values.astype(bool)
    T.to_csv("cons_fall_breakout_trades.csv.gz", index=False)
    lab = {"15m": "33 stk 15-min", "60m": "33 stk 60-min", "D_kite": "33 stk daily", "D": "N500 daily", "W": "N500 weekly"}
    rows = []
    for (tf, w), X0 in T.groupby(["tf", "W"]):
        X0 = X0[X0.t_in >= ("2015-06-01" if tf in ("15m", "60m", "D_kite") else "2007-01-01")]
        for flt, X in (("none", X0), ("N500>50EMA", X0[X0.bull])):
            if len(X) < 20: continue
            for e in EXITS:
                r = X[f"ret_{e}"]; cg, dd, ly, ny = portfolio(X, e)
                half = X.t_in.min() + (X.t_in.max() - X.t_in.min()) / 2
                rows.append(dict(timeframe=lab[tf], range=f"{w:.0%}", filter=flt, exit=e, trades=len(X),
                                 win=f"{(r > 0).mean()*100:.0f}%", avg=f"{r.mean()*100:+.2f}%",
                                 pf=round(r[r > 0].sum() / -r[r < 0].sum(), 2),
                                 first_half=f"{X[X.t_in < half][f'ret_{e}'].mean()*100:+.2f}%",
                                 second_half=f"{X[X.t_in >= half][f'ret_{e}'].mean()*100:+.2f}%",
                                 hold_bars=round(X[f"bars_{e}"].mean(), 0), CAGR=f"{cg*100:+.1f}%",
                                 maxDD=f"{dd*100:.0f}%", losing_yrs=f"{ly}/{ny}"))
    R = pd.DataFrame(rows); R.to_csv("cons_fall_breakout_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    print(R.to_string(index=False))
