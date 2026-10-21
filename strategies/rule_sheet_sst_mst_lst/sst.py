"""SST (short-term) from the user's sheet, on 2-hour bars of 33 Nifty 50 stocks (Kite 1-min, 2015-2026), benchmark Nifty 50.
mother : D_RS55>0 & D_RSI>50 (last COMPLETED day)
entry  : 2H_RS55>0 & 2H Supertrend buy & 2H close breaks the last 2H swing high (fresh) -> buy at that 2H close
risk   : SL 5%; target 2x SL = +10% -> book 50%, stop to cost, trail rest
exits  : 2H_RS55<0 or 2H Supertrend sell (2H close), D_RS21<0 (day's close) -> exit rest; time stop 20 trading days
size   : 10 slots x 10%; costs 0.15%/side; optional market filter Nifty 500 > 50 EMA (last completed day)."""
import glob, os, numpy as np, pandas as pd
from multiprocessing import Pool
import sheet_strats as S
K1 = "../n50/stocks"; NIFTY = "/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz"
COST = 0.0015
def load1m(f):
    d = pd.read_csv(f, index_col=0, parse_dates=True)
    t = d.index.hour * 100 + d.index.minute; return d[(t >= 915) & (t <= 1529)]
def to2h(d):
    return d.resample("120min", origin="start_day", offset="9h15min", label="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
def todaily(d):
    return d.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
NI = load1m(NIFTY); NI2 = to2h(NI).close; NID = todaily(NI).close
N500 = S.IDX; MKT = (N500 > N500.ewm(span=50, adjust=False).mean())
def run(f):
    sym = os.path.basename(f).split(".")[0]
    d = load1m(f); b = to2h(d); dd = todaily(d)
    ix2 = NI2.reindex(b.index).ffill(); ixd = NID.reindex(dd.index).ffill()
    rs55 = S.rs(b.close, ix2, 55).values; st = S.supertrend(b.high, b.low, b.close); swh = S.swing_high(b.high.values)
    drs55, drsi, drs21 = S.rs(dd.close, ixd, 55), S.rsi(dd.close), S.rs(dd.close, ixd, 21)
    day = b.index.normalize()
    prevday = lambda s: s.shift(1).reindex(day).values                # last completed day
    mother = (prevday(drs55) > 0) & (prevday(drsi) > 50)
    mkt = MKT.shift(1).reindex(day, method="ffill").values.astype(bool)
    drs21_today = drs21.reindex(day).values
    last_of_day = np.r_[day[1:] != day[:-1], True]
    o, h, l, c = (b[k].values for k in ("open", "high", "low", "close"))
    brk = (c > swh) & (np.r_[np.nan, c[:-1]] <= np.r_[np.nan, swh[:-1]])
    sig = mother & (rs55 > 0) & (st == 1) & brk
    dnum = np.cumsum(np.r_[True, day[1:] != day[:-1]])
    out = []; i = 0; n = len(c)
    while i < n - 1:
        if not sig[i] or i < 600: i += 1; continue
        en = c[i]; stop = en * 0.95; tp = en * 1.10; rem = 1.0; got = 0.0; tp_hit = False; j = i + 1; why = None
        while j < n:
            if o[j] <= stop: got += rem * o[j]; rem = 0; why = "SL" if not tp_hit else "BE"; break
            if l[j] <= stop: got += rem * stop; rem = 0; why = "SL" if not tp_hit else "BE"; break
            if not tp_hit and h[j] >= tp: got += 0.5 * max(tp, o[j]); rem -= 0.5; tp_hit = True; stop = max(stop, en)
            if rs55[j] < 0 or st[j] == -1 or (last_of_day[j] and drs21_today[j] < 0):
                got += rem * c[j]; rem = 0; why = "2H RS55<0" if rs55[j] < 0 else "2H Supertrend" if st[j] == -1 else "D RS21<0"; break
            if dnum[j] - dnum[i] >= 20 and last_of_day[j]: got += rem * c[j]; rem = 0; why = "20 days"; break
            j += 1
        if rem > 0: got += rem * c[-1]; j = n - 1; why = "open"
        out.append(dict(sym=sym, t_in=b.index[i], t_out=b.index[j], ret=got / en - 1 - 2 * COST, why=why, tp_hit=tp_hit,
                        days=int(dnum[j] - dnum[i]), rank=rs55[i], mkt=bool(mkt[i])))
        i = j + 1
    return out
if __name__ == "__main__":
    with Pool(2) as p: res = p.map(run, sorted(glob.glob(f"{K1}/*.csv.gz")))
    T = pd.DataFrame([t for r in res for t in r]); T.to_csv("sst_trades.csv.gz", index=False)
    rows = []
    for name, X0 in (("SST as sheet", T), ("SST + market filter", T[T.mkt])):
        for tax in (False, True):
            s, cv = S.portfolio(X0, 10, tax, start="2015-06-01"); X = X0[X0.t_in >= "2015-06-01"]
            rows.append(dict(variant=name + (" | after tax" if tax else ""), trades=len(X), trades_yr=round(len(X) / 11.4), win=f"{(X.ret>0).mean()*100:.0f}%",
                             avg=f"{X.ret.mean()*100:+.2f}%", tp_hit=f"{X.tp_hit.mean()*100:.0f}%", med_days=int(X.days.median()),
                             CAGR=f"{s['CAGR']*100:+.1f}%", maxDD=f"{s['maxDD']*100:.0f}%", last3y=f"{s['cagr_3y']*100:+.1f}%", losing_yrs=s["losing_yrs"]))
    R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("sst_summary.csv", index=False)
    print("exit reasons:", (T.why.value_counts(normalize=True) * 100).round(0).to_dict())
    n50 = NID[NID.index >= "2015-06-01"]; print("Nifty 50 B&H CAGR %.1f%%" % (((n50.iloc[-1] / n50.iloc[0]) ** (365.25 / (n50.index[-1] - n50.index[0]).days) - 1) * 100))
