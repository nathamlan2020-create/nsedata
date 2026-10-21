"""34 EMA pullback backtest across timeframes (long only).

Rules (same on every timeframe):
  Trend   : close > EMA34, EMA34 rising (above its value 5 bars ago), EMA34 > EMA200
  Pullback: signal bar's low touches/pierces EMA34 but closes above it; previous 3 bars' lows were above EMA34
  Entry   : next bar trades above signal-bar high (buy-stop) -> fill at max(open, signal high)
  Stop    : signal-bar low  (skip if risk > 8% of price or < 0.1%)
  Exits   : A) 2R target   B) trail: exit next bar open after a close below EMA34
            plus time limit (daily 20 bars, weekly 12, 60m 35) ; 5m/15m squared off at day's last bar
  Costs   : 0.20% round trip (delivery) for daily/weekly/60m, 0.10% for 5m/15m intraday
  Portfolio: 10 slots, 10% of equity each, signals taken in time order (highest turnover first)
"""
import sys, glob, os, numpy as np, pandas as pd
from multiprocessing import Pool

N500 = "../n500"; K1 = "../n50/stocks"
K22 = ["RELIANCE","HDFCBANK","ICICIBANK","BHARTIARTL","INFY","LT","ITC","TCS","SBIN","AXISBANK","ADANIENT","APOLLOHOSP",
       "KOTAKBANK","MM","HINDUNILVR","BAJFINANCE","SUNPHARMA","MARUTI","HCLTECH","NTPC","ULTRACEMCO","TITAN"]
CFG = {"5m": (True, 0.0010, 999), "15m": (True, 0.0010, 999), "60m": (False, 0.0020, 35),
       "D": (False, 0.0020, 20), "W": (False, 0.0020, 12)}

def bars(sym, tf):
    if tf in ("5m", "15m", "60m"):
        d = pd.read_csv(f"{K1}/{sym}.csv.gz", index_col=0, parse_dates=True)
        rule = {"5m": "5min", "15m": "15min", "60m": "60min"}[tf]
        d = d.resample(rule, origin="start_day", offset="9h15min", label="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        return d
    f = f"{N500}/{'M_M' if sym == 'MM' else sym}.NS.csv"
    d = pd.read_csv(f, index_col=0, parse_dates=True).dropna()
    d = d[d.volume > 0]
    if tf == "W":
        d = d.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return d

def trades(d, tf, sym):
    intraday, cost, tmax = CFG[tf]
    o, h, l, c = (d[k].values for k in ("open", "high", "low", "close"))
    e = d.close.ewm(span=34, adjust=False).mean().values
    e200 = d.close.ewm(span=200, adjust=False).mean().values
    turn = (d.close * d.volume).rolling(20).mean().values
    t = d.index.values; day = d.index.normalize().values
    n = len(c); out = []
    above3 = np.zeros(n, bool)
    above3[3:] = (l[2:-1] > e[2:-1]) & (l[1:-2] > e[1:-2]) & (l[:-3] > e[:-3])
    rising = np.zeros(n, bool); rising[5:] = e[5:] > e[:-5]
    sig = (c > e) & (l <= e) & above3 & rising & (e > e200)
    sig[:200] = False
    if tf in ("D", "W"):
        sig &= (turn > 5e7 * (5 if tf == "W" else 1)) & (c > 50)   # >Rs5 cr/day avg turnover
    for i in np.flatnonzero(sig):
        j = i + 1
        if j >= n or h[j] <= h[i] or (intraday and day[j] != day[i]): continue
        en = max(o[j], h[i]); st = l[i]; R = en - st
        if R <= 0 or R / en > 0.08 or R / en < 0.001: continue
        tg = en + 2 * R
        res = {}
        for mode in ("2R", "trail"):
            k = j; ex = None
            while True:
                if k > j and o[k] <= st: ex = (k, o[k]); break
                if l[k] <= st: ex = (k, st); break
                if mode == "2R":
                    if k > j and o[k] >= tg: ex = (k, o[k]); break
                    if h[k] >= tg: ex = (k, tg); break
                else:
                    if c[k] < e[k] and k + 1 < n and not (intraday and day[k + 1] != day[k]):
                        ex = (k + 1, o[k + 1]); break
                last = k + 1 >= n or (intraday and day[k + 1] != day[k]) or (k - j + 1 >= tmax)
                if last: ex = (k, c[k]); break
                k += 1
            res[mode] = (ex[1] / en - 1 - cost, t[ex[0]], ex[0] - j + 1)
        out.append(dict(sym=sym, tf=tf, t_in=t[j], turn=turn[i], R=R / en,
                        ret_2R=res["2R"][0], t_out_2R=res["2R"][1], bars_2R=res["2R"][2],
                        ret_trail=res["trail"][0], t_out_trail=res["trail"][1], bars_trail=res["trail"][2]))
    return out

def job(a):
    sym, tf = a
    try: return trades(bars(sym, tf), tf, sym)
    except Exception as ex: print("ERR", sym, tf, ex); return []

def portfolio(T, mode, slots=10):
    T = T.sort_values(["t_in", "turn"], ascending=[True, False])
    eq = 1.0; openp = []  # (t_out, stake, ret)
    curve = []
    for r in T.itertuples():
        ti = r.t_in
        still = []
        for p in openp:
            if p[0] <= ti: eq += p[1] * p[2]; curve.append((p[0], eq))
            else: still.append(p)
        openp = still
        if len(openp) >= slots: continue
        openp.append((getattr(r, f"t_out_{mode}"), eq / slots, getattr(r, f"ret_{mode}")))
    for p in sorted(openp): eq += p[1] * p[2]; curve.append((p[0], eq))
    s = pd.Series([v for _, v in curve], index=pd.to_datetime([x for x, _ in curve])).sort_index()
    s = s.groupby(level=0).last()
    yrs = (s.index[-1] - T.t_in.min()).days / 365.25
    dd = (s / s.cummax() - 1).min()
    yr = s.resample("YE").last().pct_change(); yr.iloc[0] = s.resample("YE").last().iloc[0] - 1
    return eq ** (1 / yrs) - 1, dd, (yr < 0).sum(), len(yr)

if __name__ == "__main__":
    jobs = [(s, tf) for tf in ("5m", "15m", "60m", "D", "W") for s in K22]
    n500 = [os.path.basename(f)[:-7] for f in glob.glob(f"{N500}/*.NS.csv")]
    jobs += [(s, tf) for tf in ("D", "W") for s in n500]
    with Pool(2) as p: res = p.map(job, jobs, chunksize=4)
    T = pd.DataFrame([r for rr in res for r in rr])
    for col in ("t_in", "t_out_2R", "t_out_trail"): T[col] = pd.to_datetime(T[col])
    T["univ"] = np.where(T.sym.isin(K22 + ["M_M"]), "22", "N500")
    ix = pd.read_csv(f"{N500}/IDX_CRSLDX.NS.csv" if os.path.exists(f"{N500}/IDX_CRSLDX.NS.csv") else f"{N500}/IDX_CRSLDX.csv", index_col=0, parse_dates=True).close.dropna()
    bull = (ix > ix.ewm(span=200, adjust=False).mean()).shift(1)
    T["bull"] = bull.reindex(T.t_in.dt.normalize(), method="ffill").values.astype(bool)
    T.to_csv("ema34_trades.csv.gz", index=False)
    rows = []
    def add(lbl, X, start=None):
        if start: X = X[X.t_in >= start]
        for mode in ("2R", "trail"):
            r = X[f"ret_{mode}"]
            cg, dd, ly, ny = portfolio(X, mode)
            rows.append(dict(test=lbl, exit=mode, trades=len(X), win=f"{(r > 0).mean()*100:.0f}%",
                             avg=f"{r.mean()*100:+.2f}%", pf=round(r[r > 0].sum() / -r[r < 0].sum(), 2),
                             early=f"{X[X.t_in < '2022'][f'ret_{mode}'].mean()*100:+.2f}%",
                             late=f"{X[X.t_in >= '2022'][f'ret_{mode}'].mean()*100:+.2f}%",
                             bars=round(X[f'bars_{mode}'].mean(), 1),
                             CAGR=f"{cg*100:+.1f}%", maxDD=f"{dd*100:.0f}%", losing_yrs=f"{ly}/{ny}"))
    T22 = T[T.sym.isin(K22 + ["M_M"])]
    for tf in ("5m", "15m", "60m", "D", "W"):
        add(f"22 stocks {tf} 2015-26", T22[T22.tf == tf], "2015-03-01")
        add(f"22 stocks {tf} +mkt>200EMA", T22[(T22.tf == tf) & T22.bull], "2015-03-01")
    N = T[T.univ == "N500"].copy(); N = pd.concat([N, T22[T22.tf.isin(["D", "W"])]]).drop_duplicates(["sym", "tf", "t_in"])
    for tf in ("D", "W"):
        add(f"Nifty500 {tf} 2007-26", N[N.tf == tf], "2007-01-01")
        add(f"Nifty500 {tf} 2015-26", N[N.tf == tf], "2015-03-01")
        add(f"Nifty500 {tf} 07-26 +mkt>200EMA", N[(N.tf == tf) & N.bull], "2007-01-01")
    R = pd.DataFrame(rows); pd.set_option("display.width", 250)
    print(R.to_string(index=False)); R.to_csv("ema34_summary.csv", index=False)
