"""
Compare the user's 3 PM breakout strategy with the Heikin Ashi swing variants,
on the same data (nsedata daily archive), same period and same 0.15%/side costs.
Usage: python compare.py <data_dir> <ha_out_dir> <out_dir>
"""
import sys, os, glob, json
import numpy as np
import pandas as pd

DATA, HAOUT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
START, COST = "2006-01-01", 0.0015

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    return d[~d.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]].astype(float)

idx = load(os.path.join(DATA, "IDX_CRSLDX.csv"))
dates = idx.index[idx.index >= pd.Timestamp(START) - pd.Timedelta(days=500)]
O, L, C, V = {}, {}, {}, {}
for f in glob.glob(os.path.join(DATA, "*.NS.csv")):
    s = os.path.basename(f)[:-7]
    d = load(f)
    d = d[d.close > 0].reindex(dates)
    O[s], L[s], C[s], V[s] = d.open, d.low, d.close, d.volume
O, L, C, V = (pd.DataFrame(x) for x in (O, L, C, V))
r = C.pct_change(fill_method=None)
bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
for X in (O, L, C):
    X[bad] = np.nan
syms = list(C.columns)

# ---- 3 PM breakout signals (all computed at the close, 3 PM price ~ close)
hi52 = C.shift(1).rolling(252, min_periods=240).max()          # prior 52-week highest close
vavg50 = V.shift(1).rolling(50, min_periods=40).mean()
sma200 = C.rolling(200, min_periods=200).mean()
turn20 = (C * V).rolling(20, min_periods=15).mean()
mom63 = C / C.shift(63) - 1
low20 = C.shift(1).rolling(20, min_periods=20).min()            # prior 20-day lowest close
ic = idx.close.reindex(dates)
mkt_on = ic > ic.ewm(span=50, adjust=False).mean()

entry_sig = (C > hi52) & (V >= 1.5 * vavg50) & (C > sma200) & (turn20 >= 5e7)

def run_breakout(dd_rule=True, max_pos=10, w=0.10, stop=0.10):
    dts = dates[dates >= pd.Timestamp(START)]
    di = {d: i for i, d in enumerate(dates)}
    col = {s: j for j, s in enumerate(syms)}
    Cv, Lv, Ov = C.values, L.values, O.values
    cash, pos, curve, trades = 1.0, {}, [], []
    def sell(s, px, d, why):
        nonlocal cash
        p = pos.pop(s)
        cash += p["sh"] * px * (1 - COST)
        trades.append(dict(sym=s, entry_date=p["d"], exit_date=d, entry=p["px"], exit=px,
                           ret=px * (1 - COST) / (p["px"] * (1 + COST)) - 1, why=why))
    for d in dts:
        i = di[d]
        # GTT stop at -10%, intraday
        for s in list(pos):
            j = col[s]; p = pos[s]; sl = p["px"] * (1 - stop)
            if not np.isnan(Lv[i, j]) and Lv[i, j] <= sl:
                op = Ov[i, j]
                sell(s, min(op, sl) if not np.isnan(op) else sl, d, "stop")
        # 3 PM exits (at close)
        for s in list(pos):
            j = col[s]; c = Cv[i, j]
            if np.isnan(c):
                continue
            if c < low20.iat[i, j]:
                sell(s, c, d, "trail")
            elif dd_rule and not mkt_on.iat[i] and c < pos[s]["px"]:
                sell(s, c, d, "filter_off")
        # 3 PM entries (at close)
        eq = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
        if mkt_on.iat[i] and len(pos) < max_pos:
            row = entry_sig.iloc[i]
            cands = [s for s in row.index[row.fillna(False).values] if s not in pos]
            cands.sort(key=lambda s: -(mom63.iat[i, col[s]] if not np.isnan(mom63.iat[i, col[s]]) else -9))
            for s in cands[: max_pos - len(pos)]:
                px = Cv[i, col[s]]
                val = min(w * eq, cash / (1 + COST))
                if val < 0.01 * eq:
                    break
                cash -= val * (1 + COST)
                pos[s] = dict(sh=val / px, px=px, d=d)
        eq = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
        curve.append((d, eq, len(pos)))
    return pd.DataFrame(curve, columns=["date", "equity", "npos"]).set_index("date"), pd.DataFrame(trades)

def stats(e, tr=None):
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = e / e.cummax() - 1
    dr = e.pct_change().dropna()
    o = dict(cagr=e.iloc[-1] ** (1 / yrs) - 1, max_dd=dd.min(), sharpe=dr.mean() / dr.std() * np.sqrt(252),
             final_x=e.iloc[-1], vol=dr.std() * np.sqrt(252))
    o["calmar"] = o["cagr"] / abs(o["max_dd"])
    # longest time under water (days)
    uw = (dd < 0).astype(int)
    grp = (uw.diff() != 0).cumsum()
    o["longest_underwater_days"] = int(uw.groupby(grp).sum().max() * 365.25 / 252)
    for n, lab in ((3, "cagr_3y"), (5, "cagr_5y"), (10, "cagr_10y")):
        s = e[e.index >= e.index[-1] - pd.DateOffset(years=n)]
        o[lab] = (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
    if tr is not None and len(tr):
        hold = (pd.to_datetime(tr.exit_date) - pd.to_datetime(tr.entry_date)).dt.days
        w, l = tr[tr.ret > 0], tr[tr.ret <= 0]
        o.update(trades=len(tr), per_year=len(tr) / yrs, win_rate=len(w) / len(tr), avg_win=w.ret.mean(),
                 avg_loss=l.ret.mean(), payoff=w.ret.mean() / abs(l.ret.mean()), med_hold_days=float(hold.median()))
    return o

if __name__ == "__main__":
    bo_e, bo_t = run_breakout()
    bo_e.to_csv(os.path.join(OUT, "equity_3pm.csv")); bo_t.to_csv(os.path.join(OUT, "trades_3pm.csv"), index=False)
    eqs = {"3 PM breakout": bo_e.equity}
    trs = {"3 PM breakout": bo_t}
    for slug, lab in (("slow_exit__no_market_filter", "Heikin Ashi (best)"), ("base", "Heikin Ashi (as described)")):
        eqs[lab] = pd.read_csv(os.path.join(HAOUT, f"equity_{slug}.csv"), index_col=0, parse_dates=True).equity
        trs[lab] = pd.read_csv(os.path.join(HAOUT, f"trades_{slug}.csv"))
    df = pd.DataFrame(eqs).dropna()
    # 50/50 blend, rebalanced monthly
    rets = df.pct_change().fillna(0)
    blend, val, wts = [], 1.0, None
    for d, rr in rets.iterrows():
        if wts is None or d.month != prev_m:
            wts = {"3 PM breakout": 0.5 * val, "Heikin Ashi (best)": 0.5 * val}
        wts = {k: v * (1 + rr[k]) for k, v in wts.items()}
        val = sum(wts.values()); blend.append(val); prev_m = d.month
    df["50/50 blend"] = blend
    df["Nifty 500"] = (ic.reindex(df.index) / ic.reindex(df.index).iloc[0]).values
    out = {k: stats(df[k], trs.get(k)) for k in df.columns}
    dr = df.pct_change().dropna()
    out["_corr_daily_3pm_vs_ha"] = float(dr["3 PM breakout"].corr(dr["Heikin Ashi (best)"]))
    # trade overlap: same stock held by both on the same day
    def held(tr):
        s = set()
        for t in tr.itertuples():
            for d in pd.bdate_range(t.entry_date, t.exit_date):
                s.add((t.sym, d))
        return s
    h1, h2 = held(bo_t), held(trs["Heikin Ashi (best)"])
    out["_overlap_share_of_3pm_position_days"] = len(h1 & h2) / len(h1)
    out["_overlap_share_of_ha_position_days"] = len(h1 & h2) / len(h2)
    out["_time_invested_3pm"] = float((bo_e.npos > 0).mean()); out["_avg_pos_3pm"] = float(bo_e.npos.mean())
    json.dump(out, open(os.path.join(OUT, "compare.json"), "w"), indent=1, default=float)
    df.to_csv(os.path.join(OUT, "equity_all.csv"))
    ye = df.resample("YE").last(); yr = ye.pct_change(); yr.iloc[0] = ye.iloc[0] / df.iloc[0] - 1
    yr.index = yr.index.year
    print((yr * 100).round(1).to_string())
    for k, v in out.items():
        if isinstance(v, dict):
            print(f"\n== {k}"); [print(f"  {a:24s} {b:.4f}" if isinstance(b, float) else f"  {a:24s} {b}") for a, b in v.items()]
        else:
            print(k, round(v, 3))
