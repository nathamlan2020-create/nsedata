"""Backtest of the user's MST (mid-term) and LST (long-term) rule sheet on Nifty 500 daily data (current constituents, 2007-2026).

Indicators
  RS_N  = (stock/stock[N]) / (Nifty500/Nifty500[N]) - 1        (relative strength vs Nifty 500 index)
  RSI   = 14-period Wilder RSI;  Supertrend(10, 3);  swing high = last pivot high (5 bars each side, known 5 bars later)
  Higher-timeframe "mother" values are taken from the LAST COMPLETED bar of that timeframe (no look-ahead).
MST  mother  W_RS21>0 & W_RSI>50
     entry   (daily close) D_RS55>0 & D_RSI>50 & daily Supertrend buy & close breaks above the last daily swing high (fresh)
     risk    SL 8%; target 2.5x SL = +20% -> book 50%, move stop to cost, trail rest
     exits   daily close: D_RS21<0 or Supertrend sell -> exit rest;  D_RSI>90 -> book 50% of what is left (once)
     size    10 slots of 10% (Rs 50k on Rs 5L)
LST  mother  M_RS12>0 & M_RSI>50 (fundamental filters NOT testable here)
     entry   (weekly close) W_RS21>0 & W_RSI>50 & weekly Supertrend buy & weekly close breaks the last weekly swing high
     size    5 slots of 20% (Rs 1L on Rs 5L); pyramid 20% at entry, +40% when close >= 5% above entry, +40% at >= 10%
             (variant: full 100% at entry)
     risk    SL 10% below average cost; target 3x SL = +30% over cost -> book 50%, stop to cost, trail rest
     exits   D_RS55<0 at daily close or weekly Supertrend sell at weekly close -> exit rest; W_RSI>90 -> book 50% of rest (once)
Costs 0.15% per side.  Liquidity: 20-day avg turnover > Rs 5 cr, price > 50.  Signals on the same day ranked by RS (strongest first).
"""
import glob, os, sys, numpy as np, pandas as pd
from multiprocessing import Pool
D = "../n500"; COST = 0.0015
IDX = pd.read_csv(f"{D}/IDX_CRSLDX.csv", index_col=0, parse_dates=True).close.dropna()

def rsi(c, n=14):
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)

def supertrend(h, l, c, n=10, m=3.0):
    h, l, c = (np.asarray(x, float) for x in (h, l, c))
    tr = np.maximum(h - l, np.maximum(abs(h - np.r_[np.nan, c[:-1]]), abs(l - np.r_[np.nan, c[:-1]]))); tr[0] = h[0] - l[0]
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().values
    hl2 = (h + l) / 2; ub = hl2 + m * atr; lb = hl2 - m * atr
    fu, fl = ub.copy(), lb.copy(); dr = np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        dr[i] = 1 if c[i] > fu[i - 1] else -1 if c[i] < fl[i - 1] else dr[i - 1]
    return dr

def swing_high(h, k=5):
    h = pd.Series(h)
    piv = h.where(h == h.rolling(2 * k + 1, center=True).max())
    return piv.shift(k).ffill().values               # pivot only known k bars later

def bars(d, rule):
    g = d.groupby(d.index.to_period(rule))
    b = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last()})
    b.index = g.apply(lambda x: x.index[-1]).values          # stamp with the last trading day of the period
    return b

def rs(c, ix, n): return (c / c.shift(n)) / (ix / ix.shift(n)) - 1

def prep(f):
    sym = os.path.basename(f)[:-7]
    d = pd.read_csv(f, index_col=0, parse_dates=True)[["open", "high", "low", "close", "volume"]].dropna()
    d = d[(d.volume > 0) & (d.close > 0)]; d = d[~d.index.duplicated()]
    if len(d) < 400: return None
    r = d.close.pct_change(); bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
    d = d[~bad]
    ix = IDX.reindex(d.index).ffill()
    X = pd.DataFrame(index=d.index)
    X["o"], X["h"], X["l"], X["c"] = d.open, d.high, d.low, d.close
    X["turn"] = (d.close * d.volume).rolling(20).mean()
    X["rs21"], X["rs55"] = rs(d.close, ix, 21), rs(d.close, ix, 55)
    X["rsi"] = rsi(d.close); X["st"] = supertrend(d.high, d.low, d.close); X["swh"] = swing_high(d.high.values)
    w = bars(d, "W-FRI"); wix = ix.reindex(w.index)
    W = pd.DataFrame({"w_rs21": rs(w.close, wix, 21), "w_rsi": rsi(w.close), "w_st": supertrend(w.high, w.low, w.close),
                      "w_swh": swing_high(w.high.values), "w_c": w.close}, index=w.index)
    W["w_brk"] = (W.w_c > W.w_swh) & (W.w_c.shift(1) <= pd.Series(W.w_swh).shift(1))
    m = bars(d, "M"); mix = ix.reindex(m.index)
    M = pd.DataFrame({"m_rs12": rs(m.close, mix, 12), "m_rsi": rsi(m.close)}, index=m.index)
    X = X.join(W)                                        # weekly values only on the week's last day
    X["weekend"] = X.w_c.notna()
    for col in ("w_rs21", "w_rsi", "w_st"): X[col + "_last"] = X[col].ffill()   # value of last completed week (incl. today if week ends today)
    X["w_rs21_prev"] = X.w_rs21.ffill().shift(1).where(~X.weekend, X.w_rs21.ffill().shift(1))
    X = X.join(M); X["m_rs12_last"] = X.m_rs12.ffill().shift(1); X["m_rsi_last"] = X.m_rsi.ffill().shift(1)  # last COMPLETED month
    # mother for MST: last completed week strictly before today unless today is week end
    wk_rs = X.w_rs21.ffill(); wk_rsi = X.w_rsi.ffill()
    X["mst_mother"] = np.where(X.weekend, (wk_rs.shift(1) > 0) & (wk_rsi.shift(1) > 50), (wk_rs > 0) & (wk_rsi > 50))
    X["lst_mother"] = (X.m_rs12_last > 0) & (X.m_rsi_last > 50)
    X["mkt"] = (IDX > IDX.ewm(span=50, adjust=False).mean()).reindex(X.index).ffill().fillna(False).values.astype(bool)
    X["sym"] = sym
    return X

def sim_mst(X, sl=0.08, tpm=2.5, rs_exit=True, mkt=False):
    o, h, l, c = (X[k].values for k in "ohlc"); rs21, rs55, rsi_, st, swh = (X[k].values for k in ("rs21", "rs55", "rsi", "st", "swh"))
    brk = (c > swh) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, swh[:-1]])
    sig = X.mst_mother.values.astype(bool) & (X.mkt.values if mkt else True) & (rs55 > 0) & (rsi_ > 50) & (st == 1) & brk & (X.turn.values > 5e7) & (c > 50)
    out = []; i = 0; n = len(c); idx = X.index
    while i < n - 1:
        if not sig[i] or i < 260: i += 1; continue
        en = c[i]; stop = en * (1 - sl); tp = en * (1 + sl * tpm); rem = 1.0; got = 0.0; tp_hit = rsi_done = False; j = i + 1; why = None
        while j < n:
            if o[j] <= stop: got += rem * o[j]; rem = 0; why = "SL" if not tp_hit else "BE/trail"; break
            if l[j] <= stop: got += rem * stop; rem = 0; why = "SL" if not tp_hit else "BE/trail"; break
            if not tp_hit and h[j] >= tp:
                px = max(tp, o[j]); got += 0.5 * px; rem -= 0.5; tp_hit = True; stop = max(stop, en)
            if not rsi_done and rsi_[j] > 90: got += rem * 0.5 * c[j]; rem *= 0.5; rsi_done = True
            if (rs_exit and rs21[j] < 0) or st[j] == -1: got += rem * c[j]; rem = 0; why = "RS21<0" if rs21[j] < 0 else "Supertrend"; break
            j += 1
        if rem > 0: got += rem * c[-1]; j = n - 1; why = "open"
        out.append(dict(sym=X.sym.iloc[0], t_in=idx[i], t_out=idx[j], ret=got / en - 1 - 2 * COST, why=why, tp_hit=tp_hit,
                        days=j - i, rank=rs55[i], turn=X.turn.values[i]))
        i = j + 1
    return out

def sim_lst(X, sl=0.10, tpm=3.0, pyramid=True, rs_exit=True, mkt=False):
    o, h, l, c = (X[k].values for k in "ohlc"); rs55 = X.rs55.values; weekend = X.weekend.values
    wst = X.w_st.ffill().values; wrsi = X.w_rsi.ffill().values; wrs21 = X.w_rs21.values; wrsi_raw = X.w_rsi.values
    sig = weekend & (X.mkt.values if mkt else True) & X.lst_mother.values.astype(bool) & (wrs21 > 0) & (wrsi_raw > 50) & (X.w_st.values == 1) & X.w_brk.fillna(False).values.astype(bool) \
        & (X.turn.values > 5e7) & (c > 50)
    out = []; i = 0; n = len(c); idx = X.index
    tranches = (0.2, 0.4, 0.4) if pyramid else (1.0,)
    while i < n - 1:
        if not sig[i] or i < 300: i += 1; continue
        e0 = c[i]; sh = tranches[0] / e0; cost_in = tranches[0]; used = tranches[0]; k_add = 1; proceeds = 0.0
        tp_hit = rsi_done = False; j = i + 1; why = None
        def avg(): return cost_in / sh if sh > 0 else e0
        stop = avg() * (1 - sl)
        while j < n:
            if o[j] <= stop: proceeds += sh * o[j]; sh = 0; why = "SL" if not tp_hit else "BE/trail"; break
            if l[j] <= stop: proceeds += sh * stop; sh = 0; why = "SL" if not tp_hit else "BE/trail"; break
            tp = avg() * (1 + sl * tpm)
            if not tp_hit and h[j] >= tp:
                px = max(tp, o[j]); proceeds += 0.5 * sh * px; cb = cost_in * 0.5; cost_in -= cb; sh *= 0.5; tp_hit = True; stop = max(stop, avg())
            if weekend[j] and not rsi_done and wrsi_raw[j] > 90: proceeds += 0.5 * sh * c[j]; cost_in *= 0.5; sh *= 0.5; rsi_done = True
            if (rs_exit and rs55[j] < 0) or (weekend[j] and wst[j] == -1): proceeds += sh * c[j]; sh = 0; why = "RS55<0" if rs55[j] < 0 else "W Supertrend"; break
            if pyramid and not tp_hit and k_add < len(tranches) and c[j] >= e0 * (1 + 0.05 * k_add):
                a = tranches[k_add]; sh += a / c[j]; cost_in += a; used += a; k_add += 1; stop = max(stop, avg() * (1 - sl))
            j += 1
        if sh > 0: proceeds += sh * c[-1]; j = n - 1; why = "open"
        gross_in = used                                   # fraction of the slot actually deployed
        pnl = proceeds - gross_in - COST * (gross_in + proceeds)
        out.append(dict(sym=X.sym.iloc[0], t_in=idx[i], t_out=idx[j], ret=pnl, deployed=gross_in, why=why, tp_hit=tp_hit,
                        days=j - i, rank=X.m_rs12_last.values[i], turn=X.turn.values[i]))
        i = j + 1
    return out

def job(f):
    X = prep(f)
    if X is None: return [], [], []
    return sim_mst(X), sim_lst(X, pyramid=True), sim_lst(X, pyramid=False)

def fy(t): return t.year + 1 if t.month >= 4 else t.year

def portfolio(T, slots, tax=False, start="2007-01-01"):
    """slot = equity/slots at entry; ret is return on the slot. Optional tax: STCG 20%, LTCG 12.5% over 1.25L (+4% cess), paid at FY end."""
    T = T[T.t_in >= start].sort_values(["t_in", "rank"], ascending=[True, False])
    cash = 1.0; openp = []; curve = []; st = lt = cfs = cfl = 0.0; cur = fy(pd.Timestamp(start))
    def settle(t):
        nonlocal cash, st, lt, cfs, cfl, cur
        while fy(t) != cur:
            S_, L_ = st + cfs, lt + cfl
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cfs, cfl = min(S_, 0), min(L_, 0)
            cash -= (max(S_, 0) * 0.20 + max(max(L_, 0) - 0, 0) * 0.125) * 1.04 if tax else 0
            st = lt = 0.0; cur += 1
    def close(p):
        nonlocal cash, st, lt
        settle(p[0]); g = p[1] * p[2]; cash += p[1] + g
        if (p[0] - p[4]).days >= 365: lt += g
        else: st += g
        curve.append((p[0], cash + sum(q[1] for q in openp)))
    for r in T.itertuples():
        for p in sorted([p for p in openp if p[0] < r.t_in]): openp.remove(p); close(p)
        settle(r.t_in)
        if len(openp) >= slots or any(p[3] == r.sym for p in openp): continue
        eq = cash + sum(p[1] for p in openp); amt = eq / slots
        if amt > cash: amt = cash
        if amt <= 0: continue
        cash -= amt; openp.append((r.t_out, amt, r.ret, r.sym, r.t_in))
    for p in sorted(openp): openp.remove(p); close(p)
    s = pd.Series([v for _, v in curve], index=pd.to_datetime([t for t, _ in curve])).groupby(level=0).last()
    yrs = (s.index[-1] - pd.Timestamp(start)).days / 365.25
    yr = s.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] - 1
    return dict(CAGR=s.iloc[-1] ** (1 / yrs) - 1, maxDD=(s / s.cummax() - 1).min(), final=s.iloc[-1], losing_yrs=f"{(yret < 0).sum()}/{len(yret)}",
                cagr_3y=(s.iloc[-1] / s[s.index <= s.index[-1] - pd.DateOffset(years=3)].iloc[-1]) ** (1 / 3) - 1), s

if __name__ == "__main__":
    fs = sorted(glob.glob(f"{D}/*.NS.csv"))
    with Pool(2) as p: res = p.map(job, fs, chunksize=8)
    TM = pd.DataFrame([t for r in res for t in r[0]]); TL = pd.DataFrame([t for r in res for t in r[1]]); TF = pd.DataFrame([t for r in res for t in r[2]])
    TM.to_csv("mst_trades.csv.gz", index=False); TL.to_csv("lst_trades.csv.gz", index=False); TF.to_csv("lst_full_trades.csv.gz", index=False)
    rows = []; curves = {}
    for name, T, slots in (("MST (10 x 10%)", TM, 10), ("LST pyramid 20/40/40 (5 x 20%)", TL, 5), ("LST full entry (5 x 20%)", TF, 5)):
        X = T[T.t_in >= "2007-01-01"]
        for tax in (False, True):
            s, cv = portfolio(T, slots, tax)
            curves[f"{name}{' after tax' if tax else ''}"] = cv
            rows.append(dict(strategy=name + (" | after tax" if tax else ""), trades=len(X), trades_yr=round(len(X) / 19.8),
                             win=f"{(X.ret > 0).mean()*100:.0f}%", avg_trade=f"{X.ret.mean()*100:+.2f}%",
                             avg_win=f"{X[X.ret > 0].ret.mean()*100:+.1f}%", avg_loss=f"{X[X.ret <= 0].ret.mean()*100:+.1f}%",
                             tp_hit=f"{X.tp_hit.mean()*100:.0f}%", med_days=int(X.days.median()),
                             CAGR=f"{s['CAGR']*100:+.1f}%", maxDD=f"{s['maxDD']*100:.0f}%", last3y=f"{s['cagr_3y']*100:+.1f}%",
                             losing_yrs=s["losing_yrs"], x5L=f"₹{s['final']*5:.1f} L"))
    R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("sheet_summary.csv", index=False)
    for name, T in (("MST", TM), ("LST", TL)):
        print(f"\n{name} exit reasons:", (T.why.value_counts(normalize=True) * 100).round(0).to_dict())
    Y = pd.DataFrame({k: v.resample("YE").last() for k, v in curves.items()}).ffill()
    YR = Y.pct_change(); YR.iloc[0] = Y.iloc[0] - 1; YR.index = YR.index.year
    print("\nYearly returns %:\n", (YR * 100).round(1).to_string())
    pd.DataFrame(curves).to_csv("sheet_equity.csv.gz")
