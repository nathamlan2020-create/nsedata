"""
Heikin Ashi swing-trading backtest on Nifty 500 (2006-2026).
Rules are a mechanical reading of the Dhan / Animesh K masterclass framework:
weekly Heikin Ashi for trend, daily Heikin Ashi for timing, strict risk per trade.

Usage: python ha_backtest.py <data_dir> <out_dir>
"""
import sys, os, glob, json
import numpy as np
import pandas as pd

DATA, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
START = "2006-01-01"

# ---------------------------------------------------------------- load
def load(path):
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = df[~df.index.duplicated()].sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)

idx = load(os.path.join(DATA, "IDX_CRSLDX.csv"))
dates = idx.index[idx.index >= pd.Timestamp(START) - pd.Timedelta(days=400)]
files = [f for f in glob.glob(os.path.join(DATA, "*.NS.csv"))]
O, H, L, C, V = {}, {}, {}, {}, {}
for f in files:
    s = os.path.basename(f).replace(".NS.csv", "")
    d = load(f).reindex(dates)
    d = d[(d["close"] > 0)]
    d = d.reindex(dates)
    O[s], H[s], L[s], C[s], V[s] = d.open, d.high, d.low, d.close, d.volume
O, H, L, C, V = [pd.DataFrame(x) for x in (O, H, L, C, V)]
# kill obviously bad prints: >60% one-day jumps that fully reverse next day
r = C.pct_change(fill_method=None)
bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
for X in (O, H, L, C):
    X[bad] = np.nan
syms = list(C.columns)

# ---------------------------------------------------------------- indicators
def heikin_ashi(o, h, l, c):
    """Works column-wise on DataFrames; returns ha_open, ha_close."""
    hc = (o + h + l + c) / 4
    ov, cv, rc = o.to_numpy(float), hc.to_numpy(float), c.to_numpy(float)
    hov = np.full(ov.shape, np.nan)
    for j in range(ov.shape[1]):
        prev = np.nan
        for i in range(ov.shape[0]):
            if np.isnan(cv[i, j]):
                continue
            if np.isnan(prev):
                hov[i, j] = (ov[i, j] + rc[i, j]) / 2
            else:
                hov[i, j] = (prev + prev_c) / 2
            prev, prev_c = hov[i, j], cv[i, j]
    return pd.DataFrame(hov, index=o.index, columns=o.columns), hc

# daily HA
d_ho, d_hc = heikin_ashi(O, H, L, C)
d_green = d_hc > d_ho
d_red = d_hc < d_ho
# "strong" green: HA low equals HA open (no lower shadow) -> classic HA trend candle
d_halow = pd.concat([L, d_ho, d_hc]).groupby(level=0).min() if False else np.minimum(np.minimum(L, d_ho), d_hc)
d_strong = d_green & ((d_ho - d_halow) <= 0.001 * C)

# weekly HA (bars labelled on Friday; value known at Friday close, forward-filled -> no lookahead)
wk = lambda X, how: X.resample("W-FRI").agg(how)
WO, WH, WL, WC = wk(O, "first"), wk(H, "max"), wk(L, "min"), wk(C, "last")
w_ho, w_hc = heikin_ashi(WO, WH, WL, WC)
w_green = (w_hc > w_ho).astype(float).where(w_hc.notna())
w_green = w_green.reindex(dates, method="ffill").fillna(0).astype(bool)

# index regime: weekly HA green on Nifty 500 index + index above 50 EMA
I = idx.reindex(dates)
iO, iH, iL, iC = [I[[k]].rename(columns={k: "IDX"}) for k in ("open", "high", "low", "close")]
iw_ho, iw_hc = heikin_ashi(*(wk(x, h) for x, h in ((iO, "first"), (iH, "max"), (iL, "min"), (iC, "last"))))
idx_wgreen = (iw_hc > iw_ho)["IDX"].reindex(dates, method="ffill").fillna(False)
idx_ema50 = iC["IDX"].ewm(span=50, adjust=False).mean()
mkt_ok = idx_wgreen & (iC["IDX"] > idx_ema50)

ema20 = C.ewm(span=20, adjust=False).mean()
ema50 = C.ewm(span=50, adjust=False).mean()
sma200 = C.rolling(200, min_periods=200).mean()
mom126 = C / C.shift(126) - 1
turnover = (C * V).rolling(20, min_periods=15).mean()
swing_low = L.rolling(10, min_periods=10).min()
hh20 = H.rolling(20, min_periods=20).max()
# red streak before today (pullback)
red_prev = d_red.shift(1).fillna(False)
red_prev2 = d_red.shift(2).fillna(False)
pullback = red_prev & red_prev2

# ---------------------------------------------------------------- engine
def run(name, use_mkt=True, exit_mode="ema20", risk=0.01, max_pos=10, max_w=0.10,
        stop_cap=0.08, cost=0.0015, start=START):
    """
    Entry (signal at day t close, fill at t+1 open):
      stock weekly HA green, close > 50 EMA > 200 SMA, daily HA flips red->green after
      >=2 red HA candles (pullback ends) with a strong green candle, liquid
      (20d avg turnover in top 300 of universe that day), optional market regime.
      Ranked by 6-month momentum when slots are limited.
    Stop: 10-day swing low, capped at stop_cap below entry; hit intraday (gap -> open).
    Exit (signal at close, fill next open):
      ema20: close < 20 EMA or weekly HA turns red
      ha:    first daily HA red candle (fast) or weekly red
      weekly: weekly HA turns red only
    Sizing: risk% of equity / stop distance, capped at max_w of equity, max_pos names.
    """
    dts = dates[dates >= pd.Timestamp(start)]
    cash, pos, eq_curve, trades = 1.0, {}, [], []
    tov_rank = turnover.rank(axis=1, ascending=False)
    Ov, Hv, Lv, Cv = O.values, H.values, L.values, C.values
    col = {s: j for j, s in enumerate(syms)}
    di = {d: i for i, d in enumerate(dates)}
    pending_entries, pending_exits = [], set()

    for d in dts:
        i = di[d]
        # --- fills at open
        for s in list(pending_exits):
            if s in pos:
                j = col[s]
                px = Ov[i, j] if not np.isnan(Ov[i, j]) else Cv[i - 1, j]
                p = pos.pop(s)
                cash += p["sh"] * px * (1 - cost)
                trades.append(dict(sym=s, entry_date=p["d"], exit_date=d, entry=p["px"], exit=px,
                                   ret=px * (1 - cost) / (p["px"] * (1 + cost)) - 1, why="signal"))
        pending_exits = set()
        equity_open = cash + sum(p["sh"] * (Ov[i, col[s]] if not np.isnan(Ov[i, col[s]]) else Cv[i - 1, col[s]])
                                 for s, p in pos.items())
        for s, stop_lvl in pending_entries:
            if len(pos) >= max_pos or s in pos:
                continue
            j = col[s]
            px = Ov[i, j]
            if np.isnan(px) or px <= 0:
                continue
            stop = max(stop_lvl, px * (1 - stop_cap))
            if stop >= px * 0.995:          # gapped through/near stop: skip
                continue
            dist = (px - stop) / px
            w = min(risk / dist, max_w)
            val = min(w * equity_open, cash / (1 + cost))
            if val < 0.002 * equity_open:
                continue
            sh = val / px
            cash -= val * (1 + cost)
            pos[s] = dict(sh=sh, px=px, stop=stop, d=d)
        pending_entries = []
        # --- intraday stops
        for s in list(pos):
            j = col[s]
            p = pos[s]
            lo, op = Lv[i, j], Ov[i, j]
            if not np.isnan(lo) and lo <= p["stop"]:
                px = min(op, p["stop"]) if not np.isnan(op) else p["stop"]
                pos.pop(s)
                cash += p["sh"] * px * (1 - cost)
                trades.append(dict(sym=s, entry_date=p["d"], exit_date=d, entry=p["px"], exit=px,
                                   ret=px * (1 - cost) / (p["px"] * (1 + cost)) - 1, why="stop"))
        # --- mark to market
        eq = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"])
                        for s, p in pos.items())
        eq_curve.append((d, eq, len(pos)))
        # --- exit signals at close
        for s in pos:
            j = col[s]
            if np.isnan(Cv[i, j]):
                continue
            wred = not w_green.iat[i, j]
            if exit_mode == "ema20":
                ex = Cv[i, j] < ema20.iat[i, j] or wred
            elif exit_mode == "ha":
                ex = d_red.iat[i, j] or wred
            else:
                ex = wred
            if ex:
                pending_exits.add(s)
        # --- entry signals at close
        if use_mkt and not mkt_ok.iat[i]:
            continue
        free = max_pos - (len(pos) - len(pending_exits))
        if free <= 0:
            continue
        sig = (w_green.iloc[i] & d_strong.iloc[i] & pullback.iloc[i]
               & (C.iloc[i] > ema50.iloc[i]) & (ema50.iloc[i] > sma200.iloc[i])
               & (tov_rank.iloc[i] <= 300))
        cands = [s for s in sig.index[sig.fillna(False).values] if s not in pos]
        cands.sort(key=lambda s: -(mom126.iat[i, col[s]] if not np.isnan(mom126.iat[i, col[s]]) else -9))
        pending_entries = [(s, swing_low.iat[i, col[s]]) for s in cands[:free]]

    ec = pd.DataFrame(eq_curve, columns=["date", "equity", "npos"]).set_index("date")
    tr = pd.DataFrame(trades)
    return ec, tr

def stats(ec, tr, bench):
    e = ec["equity"]
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    cagr = e.iloc[-1] ** (1 / yrs) - 1
    dd = e / e.cummax() - 1
    dr = e.pct_change().dropna()
    sharpe = dr.mean() / dr.std() * np.sqrt(252)
    b = bench.reindex(e.index).ffill()
    b = b / b.iloc[0]
    bcagr = b.iloc[-1] ** (1 / yrs) - 1
    bdd = (b / b.cummax() - 1).min()
    wins = tr[tr.ret > 0]
    losses = tr[tr.ret <= 0]
    hold = (pd.to_datetime(tr.exit_date) - pd.to_datetime(tr.entry_date)).dt.days
    return dict(
        cagr=cagr, max_dd=dd.min(), sharpe=sharpe, final_x=e.iloc[-1],
        calmar=cagr / abs(dd.min()), exposure=(ec["npos"] > 0).mean(), avg_pos=ec["npos"].mean(),
        trades=len(tr), per_year=len(tr) / yrs, win_rate=len(wins) / len(tr),
        avg_win=wins.ret.mean(), avg_loss=losses.ret.mean(),
        payoff=wins.ret.mean() / abs(losses.ret.mean()),
        expectancy=tr.ret.mean(), med_hold_days=hold.median(),
        stop_exits=(tr.why == "stop").mean(),
        bench_cagr=bcagr, bench_max_dd=bdd, bench_final_x=b.iloc[-1],
    )

if __name__ == "__main__":
    variants = {
        "Base (weekly HA + 20 EMA exit, market filter)": dict(),
        "No market filter": dict(use_mkt=False),
        "Fast exit (first daily HA red)": dict(exit_mode="ha"),
        "Slow exit (weekly HA red only)": dict(exit_mode="weekly"),
        "Slow exit + no market filter": dict(exit_mode="weekly", use_mkt=False),
    }
    bench = I["close"]
    out = {}
    for k, kw in variants.items():
        ec, tr = run(k, **kw)
        st = stats(ec, tr, bench)
        out[k] = st
        slug = "".join(ch for ch in k.split(" (")[0].lower().replace(" ", "_") if ch.isalnum() or ch == "_")
        ec.to_csv(os.path.join(OUT, f"equity_{slug}.csv"))
        tr.to_csv(os.path.join(OUT, f"trades_{slug}.csv"), index=False)
        print(f"\n== {k}")
        for a, b in st.items():
            print(f"  {a:14s} {b:.4f}" if isinstance(b, float) else f"  {a:14s} {b}")
    json.dump(out, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=float)
