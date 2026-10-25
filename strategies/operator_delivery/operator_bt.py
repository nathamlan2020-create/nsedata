"""'Operator tracking' (Vivek Bajaj / StockEdge idea) backtest on the Nifty 500, 2006-2026.

Daily, at the close:
 1 Operator footprint : volume >= X x its 5-day average AND delivery qty >= X x its 5-day average AND close up on the day.
                         (delivery % from NSE MTO files x split-adjusted volume; price > 50, 20d turnover > Rs 5 cr)
 2 Sector screen      : the stock's sector must have >= 3 such stocks that day (unusual sector-wide delivery).
 3 Chart check        : close above 20 EMA, 50 EMA and 20-day VWAP; RS(55) vs Nifty 500 > 0; Supertrend(10,3) up.
 4 Watch-list         : passing stocks wait up to 10 days (max 40 names, highest delivery multiple first).
 5 Entry (no chasing) : buy-stop above the signal-day high; fill at max(open, trigger).
 6 Exit               : stop at signal-day low (max 8% below entry); trail = close below Supertrend (or other exit).
 Portfolio: max 10 positions x 10%, new buys only while Nifty 500 > 50 EMA (as in your other systems).
 Costs 0.15%/side. Tax STCG 20% / LTCG 12.5% (> Rs 1.25L) + 4% cess at FY end, Rs 5 lakh start.
Also an event study: forward returns after footprint days vs all stock-days."""
import glob, os, numpy as np, pandas as pd
D = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/n500c"
DEL = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/deliv/delivery_n500.csv.gz"
START = pd.Timestamp("2006-04-01"); COST = 0.0015; CAP = 5e5
SECT = dict(l.strip().split("|") for l in open("/home/claude/nsedata/lists/nifty500_sectors.txt") if "|" in l)

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True); return d[~d.index.duplicated()].sort_index()
idx = load(f"{D}/IDX_CRSLDX.csv").close; dates = idx.index
X = {k: {} for k in "OHLCV"}
for f in glob.glob(f"{D}/*.NS.csv"):
    s = os.path.basename(f)[:-7]; d = load(f); d = d[d.close > 0].reindex(dates)
    for k, c in zip("OHLCV", ("open", "high", "low", "close", "volume")): X[k][s] = d[c]
O, H, L, C, V = (pd.DataFrame(X[k]) for k in "OHLCV")
r = C.pct_change(fill_method=None); bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
for Z in (O, H, L, C): Z[bad] = np.nan
dl = pd.read_csv(DEL, parse_dates=["date"])
DP = dl.pivot_table(index="date", columns="sym", values="pct").reindex(index=dates, columns=C.columns) / 100
DQ = V * DP
ic = idx.reindex(dates).ffill(); MKT = ic > ic.ewm(span=50, adjust=False).mean()
turn = (C * V).rolling(20, min_periods=10).mean(); liq = (C > 50) & (turn > 5e7)
e20 = C.ewm(span=20, adjust=False).mean(); e50 = C.ewm(span=50, adjust=False).mean()
tp = (H + L + C) / 3; vwap20 = (tp * V).rolling(20).sum() / V.rolling(20).sum()
rs55 = (C / C.shift(55)).div(ic / ic.shift(55), axis=0) - 1

def supertrend(h, l, c, n=10, m=3):
    tr = np.maximum(h - l, np.maximum(abs(h - c.shift()), abs(l - c.shift())))
    atr = tr.ewm(alpha=1 / n, adjust=False).mean(); hl = (h + l) / 2
    ub, lb = (hl + m * atr).values, (hl - m * atr).values; cv = c.values
    up = np.zeros(c.shape, bool); fu, fl = ub.copy(), lb.copy()
    for i in range(1, len(c)):
        for j in range(c.shape[1]):
            if np.isnan(cv[i, j]) or np.isnan(fu[i - 1, j]):
                continue
            fu[i, j] = ub[i, j] if (ub[i, j] < fu[i - 1, j] or cv[i - 1, j] > fu[i - 1, j]) else fu[i - 1, j]
            fl[i, j] = lb[i, j] if (lb[i, j] > fl[i - 1, j] or cv[i - 1, j] < fl[i - 1, j]) else fl[i - 1, j]
            up[i, j] = cv[i, j] > fu[i - 1, j] if not up[i - 1, j] else not (cv[i, j] < fl[i - 1, j])
    return pd.DataFrame(up, index=c.index, columns=c.columns), pd.DataFrame(np.where(up, fl, fu), index=c.index, columns=c.columns)
cache = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/deliv/st.pkl"
if os.path.exists(cache): STUP, STL = pd.read_pickle(cache)
else: STUP, STL = supertrend(H.ffill(), L.ffill(), C.ffill()); pd.to_pickle((STUP, STL), cache)

def footprint(x=2.0):
    vm = V / V.shift(1).rolling(5).mean(); dm = DQ / DQ.shift(1).rolling(5).mean()
    return (vm >= x) & (dm >= x) & (C > C.shift(1)) & liq, dm
def sector_ok(fp, k=3):
    sec = pd.Series({s: SECT.get(s, "NA") for s in C.columns})
    cnt = fp.T.groupby(sec).sum().T                                   # signals per sector per day
    return pd.DataFrame({s: cnt[sec[s]] for s in C.columns}, index=dates) >= k
CHART = (C > e20) & (C > e50) & (C > vwap20) & (rs55 > 0) & STUP

def fy(t): return t.year + 1 if t.month >= 4 else t.year
def run(x=2.0, sector=3, chart=True, exit="supertrend", mkt=True, wait=10, maxpos=10, tax=True, maxsl=0.08):
    fp, dm = footprint(x); sig = fp.copy()
    if sector: sig &= sector_ok(fp, sector)
    if chart: sig &= CHART
    syms = list(C.columns); col = {s: j for j, s in enumerate(syms)}
    Ov, Hv, Lv, Cv, SG, DM, SL_, E20 = O.values, H.values, L.values, C.values, sig.values, dm.values, STL.values, e20.values
    days = dates[dates >= START]; di = {d: i for i, d in enumerate(dates)}; MK = MKT.values
    cash = CAP; pos = {}; watch = {}; vals = []; trades = []; st = lt = cfs = cfl = 0.0; cur = fy(days[0])
    def sell(s, px, t, why):
        nonlocal cash, st, lt
        p = pos.pop(s); pr = p["sh"] * px * (1 - COST); cash += pr; g = pr - p["cost"]
        if (t - p["d"]).days >= 365: lt += g
        else: st += g
        trades.append(dict(sym=s, entry=p["d"], exit=t, ret=pr / p["cost"] - 1, why=why, days=(t - p["d"]).days))
    for t in days:
        i = di[t]
        if tax and fy(t) != cur:
            S_, L_ = st + cfs, lt + cfl
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cfs, cfl = min(S_, 0), min(L_, 0)
            cash -= (max(S_, 0) * 0.20 + max(max(L_, 0) - 125000, 0) * 0.125) * 1.04; st = lt = 0.0; cur = fy(t)
        for s in list(pos):                                           # stops (intraday) and trail (at close)
            j = col[s]; p = pos[s]
            if np.isnan(Cv[i, j]): continue
            if Lv[i, j] <= p["sl"]: sell(s, min(Ov[i, j], p["sl"]) if not np.isnan(Ov[i, j]) else p["sl"], t, "stop"); continue
            if i <= p["i"]: continue
            if exit == "supertrend" and Cv[i, j] < SL_[i, j] and not STUP.values[i, j]: sell(s, Cv[i, j], t, "supertrend")
            elif exit == "ema20" and Cv[i, j] < E20[i, j]: sell(s, Cv[i, j], t, "ema20")
            elif exit == "hold20" and i - p["i"] >= 20: sell(s, Cv[i, j], t, "20 days")
        eq = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
        for s in list(watch):                                         # buy-stop above signal-day high
            w = watch[s]; j = col[s]
            if i - w["i"] > wait or s in pos: watch.pop(s); continue
            if i == w["i"] or np.isnan(Hv[i, j]): continue
            if Lv[i, j] < w["low"]: watch.pop(s); continue                    # setup broken before trigger
            if Hv[i, j] > w["trig"] and len(pos) < maxpos and (MK[i - 1] or not mkt):
                px = max(Ov[i, j], w["trig"]); amt = min(eq / maxpos, cash)
                if amt < 0.02 * eq: continue
                cash -= amt; pos[s] = dict(sh=amt * (1 - COST) / px, cost=amt, px=px, d=t, i=i, sl=max(w["low"], px * (1 - maxsl)))
                watch.pop(s)
        new = [syms[j] for j in np.flatnonzero(SG[i]) if syms[j] not in pos]
        for s in new: watch[s] = dict(i=i, trig=Hv[i, col[s]], low=Lv[i, col[s]], dm=DM[i, col[s]])
        if len(watch) > 40:
            for s in sorted(watch, key=lambda s: watch[s]["dm"])[:len(watch) - 40]: watch.pop(s)
        vals.append(cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items()))
    e = pd.Series(vals, index=days); tr = pd.DataFrame(trades); yrs = (e.index[-1] - e.index[0]).days / 365.25
    yr = e.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] / CAP - 1
    s3 = e[e.index >= e.index[-1] - pd.DateOffset(years=3)]
    return dict(CAGR=((e.iloc[-1] / CAP) ** (1 / yrs) - 1) * 100, maxDD=(e / e.cummax() - 1).min() * 100, last3y=((s3.iloc[-1] / s3.iloc[0]) ** (1 / 3) - 1) * 100,
                worst_yr=yret.min() * 100, losing_yrs=int((yret < 0).sum()), trades_yr=len(tr) / yrs, win=(tr.ret > 0).mean() * 100,
                avg_trade=tr.ret.mean() * 100, avg_days=tr.days.mean(), final_L=e.iloc[-1] / 1e5), e, tr

if __name__ == "__main__":
    # ---- event study ----
    fwd = {k: C.shift(-k) / C - 1 for k in (5, 10, 20, 60)}
    base = (liq & C.notna()).values & (C.index >= START)[:, None]; mk = MKT.values[:, None]
    fp2, _ = footprint(2.0); fp3, _ = footprint(3.0); full = fp2 & sector_ok(fp2, 3) & CHART
    ES = []
    for name, m in [("All liquid stock-days", base), ("Footprint 2x vol+delivery, up day", fp2.values & base), ("Footprint 3x", fp3.values & base),
                    ("Footprint 2x + sector >=3 + chart filters", full.values & base), ("... and market on", full.values & base & mk)]:
        ES.append(dict(screen=name, signals_yr=round(m.sum() / 20.5), **{f"fwd{k}d_avg%": round(np.nanmean(f.values[m]) * 100, 2) for k, f in fwd.items()},
                       **{"fwd20d_win%": round(np.nanmean(fwd[20].values[m][~np.isnan(fwd[20].values[m])] > 0) * 100, 1)}))
    ES = pd.DataFrame(ES); pd.set_option("display.width", 250); print(ES.to_string(index=False)); ES.to_csv("event_study.csv", index=False)
    V_ = [("Full rules (2x, sector>=3, chart, Supertrend exit)", dict()),
          ("No sector screen", dict(sector=0)), ("Sector >= 2", dict(sector=2)), ("Footprint 1.5x", dict(x=1.5)), ("Footprint 3x", dict(x=3.0)),
          ("No chart filters", dict(chart=False)), ("Exit: close < 20 EMA", dict(exit="ema20")), ("Exit: hold 20 days", dict(exit="hold20")),
          ("No market filter", dict(mkt=False)), ("Max 20 positions x 5%", dict(maxpos=20))]
    rows = []; curves = {}
    for name, kw in V_:
        a, _, _ = run(**kw, tax=False); b, e, tr = run(**kw); curves[name] = e
        rows.append(dict(variant=name, CAGR=round(a["CAGR"], 1), maxDD=round(a["maxDD"], 1), CAGR_after_tax=round(b["CAGR"], 1), maxDD_at=round(b["maxDD"], 1),
                         last3y_at=round(b["last3y"], 1), worst_yr_at=round(b["worst_yr"], 1), losing_yrs=b["losing_yrs"], trades_yr=round(b["trades_yr"]),
                         win=round(b["win"], 1), avg_trade=round(b["avg_trade"], 2), avg_days=round(b["avg_days"]), final_at_L=round(b["final_L"], 1)))
        print(rows[-1], flush=True)
        if name.startswith("Full"): tr.to_csv("trades_full_rules.csv", index=False)
    R = pd.DataFrame(rows); print(R.to_string(index=False)); R.to_csv("operator_summary.csv", index=False)
    Y = pd.DataFrame({k: v.resample("YE").last() for k, v in curves.items()}); YR = Y.pct_change() * 100; YR.iloc[0] = (Y.iloc[0] / CAP - 1) * 100
    YR.index = YR.index.year; YR.round(1).to_csv("operator_yearly_after_tax.csv"); print(YR.iloc[:, :3].round(1).to_string())
