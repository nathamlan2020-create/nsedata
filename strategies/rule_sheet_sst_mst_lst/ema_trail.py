"""Sheet strategies with MARKET FILTER (Nifty 500 > 50 EMA at entry) and a 20-EMA TRAILING EXIT.
Entries exactly as the sheet (see sheet_strats.py / sst.py). Exits:
  - hard stop-loss (SST 5%, MST 8%, LST 10%)
  - 'book50' : book 50% at the target (2x / 2.5x / 3x SL), move stop to cost, trail the rest with the 20 EMA
  - 'trail'  : no target, the whole position trails with the 20 EMA
  20 EMA of the strategy's own chart: SST 2-hour, MST daily, LST weekly (checked at the weekly close).
  RS / Supertrend / RSI>90 exits are dropped (the 20 EMA replaces them)."""
import glob, os, numpy as np, pandas as pd
from multiprocessing import Pool
import sheet_strats as S
COST = S.COST

def trade(o, h, l, c, ema_ok, i, sl, tpm, book, check=None, maxbars=None):
    """walk bars after entry i; ema_ok[j] False => close below 20 EMA; check[j] says whether the EMA rule is evaluated on bar j."""
    n = len(c); en = c[i]; stop = en * (1 - sl); tp = en * (1 + sl * tpm); rem = 1.0; got = 0.0; hit = False; j = i + 1; why = None
    while j < n:
        if o[j] <= stop: got += rem * o[j]; rem = 0; why = "SL" if not hit else "BE"; break
        if l[j] <= stop: got += rem * stop; rem = 0; why = "SL" if not hit else "BE"; break
        if book and not hit and h[j] >= tp: got += 0.5 * max(tp, o[j]); rem -= 0.5; hit = True; stop = max(stop, en)
        if (check is None or check[j]) and not ema_ok[j]: got += rem * c[j]; rem = 0; why = "20EMA"; break
        if maxbars and j - i >= maxbars: got += rem * c[j]; rem = 0; why = "time"; break
        j += 1
    if rem > 0: got += rem * c[-1]; j = n - 1; why = "open"
    return got / en - 1 - 2 * COST, j, why, hit

def mst(X, book):
    o, h, l, c = (X[k].values for k in "ohlc"); rs55, rsi_, st, swh = (X[k].values for k in ("rs55", "rsi", "st", "swh"))
    ema = pd.Series(c).ewm(span=20, adjust=False).mean().values
    brk = (c > swh) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, swh[:-1]])
    sig = X.mst_mother.values.astype(bool) & X.mkt.values & (rs55 > 0) & (rsi_ > 50) & (st == 1) & brk & (X.turn.values > 5e7) & (c > 50)
    out = []; i = 260; n = len(c)
    while i < n - 1:
        if not sig[i]: i += 1; continue
        r, j, why, hit = trade(o, h, l, c, c >= ema, i, 0.08, 2.5, book)
        out.append(dict(sym=X.sym.iloc[0], t_in=X.index[i], t_out=X.index[j], ret=r, why=why, tp_hit=hit, days=j - i, rank=rs55[i]))
        i = j + 1
    return out

def lst(X, book, pyramid=False):
    o, h, l, c = (X[k].values for k in "ohlc"); weekend = X.weekend.values
    wc = X.w_c; wema = wc.dropna().ewm(span=20, adjust=False).mean().reindex(X.index).values
    ema_ok = ~(weekend & (c < wema))
    sig = weekend & X.mkt.values & X.lst_mother.values.astype(bool) & (X.w_rs21.values > 0) & (X.w_rsi.values > 50) & (X.w_st.values == 1) \
        & X.w_brk.fillna(False).values.astype(bool) & (X.turn.values > 5e7) & (c > 50)
    out = []; i = 300; n = len(c)
    while i < n - 1:
        if not sig[i]: i += 1; continue
        if not pyramid:
            r, j, why, hit = trade(o, h, l, c, ema_ok, i, 0.10, 3.0, book)
        else:   # 20/40/40: add 40% at +5% and +10% above first entry (closes), stop 10% below average cost
            e0 = c[i]; tr = (0.2, 0.4, 0.4); sh = 0.2 / e0; cin = 0.2; used = 0.2; k = 1; proc = 0.0; hit = False; j = i + 1; why = None
            stop = e0 * 0.9
            while j < n:
                if o[j] <= stop: proc += sh * o[j]; sh = 0; why = "SL"; break
                if l[j] <= stop: proc += sh * stop; sh = 0; why = "SL"; break
                avg = cin / sh
                if book and not hit and h[j] >= avg * 1.3: proc += 0.5 * sh * max(avg * 1.3, o[j]); cin *= 0.5; sh *= 0.5; hit = True; stop = max(stop, avg)
                if not ema_ok[j]: proc += sh * c[j]; sh = 0; why = "20EMA"; break
                if not hit and k < 3 and c[j] >= e0 * (1 + 0.05 * k):
                    sh += tr[k] / c[j]; cin += tr[k]; used += tr[k]; k += 1; stop = max(stop, cin / sh * 0.9)
                j += 1
            if sh > 0: proc += sh * c[-1]; j = n - 1; why = "open"
            r = proc - used - COST * (used + proc)
        out.append(dict(sym=X.sym.iloc[0], t_in=X.index[i], t_out=X.index[j], ret=r, why=why, tp_hit=hit, days=j - i, rank=X.m_rs12_last.values[i]))
        i = j + 1
    return out

def job(f):
    X = S.prep(f)
    if X is None: return {}
    return {"MST book50": mst(X, True), "MST trail": mst(X, False), "LST book50": lst(X, True), "LST trail": lst(X, False),
            "LST pyramid trail": lst(X, False, True), "LST pyramid book50": lst(X, True, True)}

# ---- SST on 2-hour bars (33 stocks) ----
import sst as SS
def sst_job(f, book):
    sym = os.path.basename(f).split(".")[0]
    d = SS.load1m(f); b = SS.to2h(d); dd = SS.todaily(d)
    ix2 = SS.NI2.reindex(b.index).ffill(); ixd = SS.NID.reindex(dd.index).ffill()
    rs55 = S.rs(b.close, ix2, 55).values; st = S.supertrend(b.high, b.low, b.close); swh = S.swing_high(b.high.values)
    day = b.index.normalize(); prev = lambda s: s.shift(1).reindex(day).values
    mother = (prev(S.rs(dd.close, ixd, 55)) > 0) & (prev(S.rsi(dd.close)) > 50)
    mkt = SS.MKT.shift(1).reindex(day, method="ffill").values.astype(bool)
    o, h, l, c = (b[k].values for k in ("open", "high", "low", "close")); ema = pd.Series(c).ewm(span=20, adjust=False).mean().values
    brk = (c > swh) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, swh[:-1]])
    sig = mother & mkt & (rs55 > 0) & (st == 1) & brk
    out = []; i = 600; n = len(c)
    while i < n - 1:
        if not sig[i]: i += 1; continue
        r, j, why, hit = trade(o, h, l, c, c >= ema, i, 0.05, 2.0, book, maxbars=80)   # 20 days x 4 bars
        out.append(dict(sym=sym, t_in=b.index[i], t_out=b.index[j], ret=r, why=why, tp_hit=hit, days=(j - i) / 4, rank=rs55[i]))
        i = j + 1
    return out
def sst_both(f): return {"SST book50": sst_job(f, True), "SST trail": sst_job(f, False)}

if __name__ == "__main__":
    with Pool(2) as p:
        res = p.map(job, sorted(glob.glob(f"{S.D}/*.NS.csv")), chunksize=8)
        res2 = p.map(sst_both, sorted(glob.glob(f"{SS.K1}/*.csv.gz")))
    rows = []; curves = {}
    for name, slots, start, R in (("MST book50", 10, "2007-01-01", res), ("MST trail", 10, "2007-01-01", res), ("LST book50", 5, "2007-01-01", res),
                                  ("LST trail", 5, "2007-01-01", res), ("LST pyramid book50", 5, "2007-01-01", res), ("LST pyramid trail", 5, "2007-01-01", res),
                                  ("SST book50", 10, "2015-06-01", res2), ("SST trail", 10, "2015-06-01", res2)):
        T = pd.DataFrame([t for r in R for t in r.get(name, [])]); T.to_csv(f"ema_{name.replace(' ', '_')}.csv.gz", index=False)
        X = T[T.t_in >= start]; yrs = (pd.Timestamp("2026-10-16") - pd.Timestamp(start)).days / 365.25
        for tax in (False, True):
            s, cv = S.portfolio(T, slots, tax, start=start); curves[name + (" AT" if tax else "")] = cv
            rows.append(dict(strategy=name + (" | after tax" if tax else ""), trades_yr=round(len(X) / yrs), win=f"{(X.ret>0).mean()*100:.0f}%",
                             avg=f"{X.ret.mean()*100:+.2f}%", avg_win=f"{X[X.ret>0].ret.mean()*100:+.1f}%", avg_loss=f"{X[X.ret<=0].ret.mean()*100:+.1f}%",
                             med_days=round(float(X.days.median()), 1), CAGR=f"{s['CAGR']*100:+.1f}%", maxDD=f"{s['maxDD']*100:.0f}%",
                             last3y=f"{s['cagr_3y']*100:+.1f}%", losing_yrs=s["losing_yrs"], x5L=f"₹{s['final']*5:.1f} L"))
    R = pd.DataFrame(rows); pd.set_option("display.width", 260); print(R.to_string(index=False)); R.to_csv("ema_trail_summary.csv", index=False)
    Y = pd.DataFrame({k: v.resample("YE").last() for k, v in curves.items() if not k.endswith("AT")}).ffill()
    YR = Y.pct_change(); YR.iloc[0] = Y.iloc[0] - 1; YR.index = YR.index.year; print((YR * 100).round(1).to_string())
