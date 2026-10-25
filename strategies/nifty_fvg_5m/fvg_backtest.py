"""Nifty 5-minute Fair Value Gap (FVG) backtest, Jan 2015 - Oct 2026, Kite 1-minute index data.

FVG (3-candle gap on 5-min bars, same day):
  bullish  low[i]  > high[i-2]  -> gap = [high[i-2], low[i]]  -> BUY  when price comes back to the gap top  (low[i])
  bearish  high[i] < low[i-2]   -> gap = [high[i], low[i-2]]  -> SELL when price comes back to the gap bottom (high[i])
Direction of the trade = direction of the FVG ("target according to FVG").
Entry: limit at the gap edge, only after the FVG candle closes; order valid for `valid` 5-min bars; newest FVG replaces older.
SL 30 pts, TP 30 pts (Rs 3,000 at Rs 100/point). Fills and exits checked on 1-minute bars; if SL and TP fall in the same
minute, SL is assumed (conservative). One trade at a time. New entries 09:30-15:00, any open trade closed 15:20.
Costs (Nifty futures): STT 0.02% on sell + exchange/GST/stamp/brokerage ~0.008% => ~0.028% of price per round trip,
plus 0.5 pt slippage.  At Nifty 25,000 that is ~7.5 pts per trade."""
import numpy as np, pandas as pd, sys
SRC = "/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz"
m = pd.read_csv(SRC, parse_dates=["date"]).set_index("date").sort_index()
m = m[~m.index.duplicated()].between_time("09:15", "15:29")
f5 = m.resample("5min", label="left", closed="left").agg(dict(open="first", high="max", low="min", close="last")).dropna()
QTY = 100

def run(sl=30, tp=30, valid=12, mingap=0, cost=True, side="both"):
    trades = []
    for day, b5 in f5.groupby(f5.index.date):
        b1 = m.loc[str(day)]
        if len(b5) < 10: continue
        H, L = b5.high.values, b5.low.values; T5 = b5.index
        fv = []                                                    # (ready_time, expire_time, dir, entry)
        for i in range(2, len(b5)):
            ready = T5[i] + pd.Timedelta(minutes=5)
            if L[i] > H[i - 2] and L[i] - H[i - 2] >= mingap and side in ("both", "long"):
                fv.append((ready, ready + pd.Timedelta(minutes=5 * valid), 1, L[i]))
            elif H[i] < L[i - 2] and L[i - 2] - H[i] >= mingap and side in ("both", "short"):
                fv.append((ready, ready + pd.Timedelta(minutes=5 * valid), -1, H[i]))
        if not fv: continue
        t1 = b1.index; O1, H1, L1, C1 = b1.open.values, b1.high.values, b1.low.values, b1.close.values
        k = 0; pend = None; pos = None
        for j, t in enumerate(t1):
            tm = t.time()
            while k < len(fv) and fv[k][0] <= t:                   # newest FVG becomes the pending order
                if pos is None: pend = fv[k]
                k += 1
            if pos is None and pend is not None:
                if t >= pend[1] or tm > pd.Timestamp("15:00").time() or tm < pd.Timestamp("09:30").time():
                    if t >= pend[1] or tm > pd.Timestamp("15:00").time(): pend = None
                else:
                    d, e = pend[2], pend[3]
                    if (d == 1 and L1[j] <= e) or (d == -1 and H1[j] >= e):
                        px = min(O1[j], e) if d == 1 else max(O1[j], e)
                        pos = dict(d=d, e=px, t=t); pend = None
            if pos is not None:
                d, e = pos["d"], pos["e"]; slp, tpp = e - d * sl, e + d * tp; out = None
                hit_sl = L1[j] <= slp if d == 1 else H1[j] >= slp
                hit_tp = H1[j] >= tpp if d == 1 else L1[j] <= tpp
                if hit_sl: out = (slp if not ((d == 1 and O1[j] < slp) or (d == -1 and O1[j] > slp)) else O1[j], "SL")
                elif hit_tp and t > pos["t"]: out = (tpp, "TP")
                elif hit_tp and t == pos["t"] and ((d == 1 and C1[j] >= e) or (d == -1 and C1[j] <= e)): out = (tpp, "TP")
                elif tm >= pd.Timestamp("15:20").time(): out = (C1[j], "EOD")
                if out:
                    g = d * (out[0] - e); c = (e * 0.00028 + 0.5) if cost else 0
                    trades.append(dict(entry_time=pos["t"], exit_time=t, side="LONG" if d == 1 else "SHORT", entry=round(e, 2),
                                       exit=round(out[0], 2), why=out[1], pts_gross=round(g, 2), pts_net=round(g - c, 2)))
                    pos = None
    return pd.DataFrame(trades)

def summ(tr, name):
    tr = tr.copy(); tr["yr"] = tr.entry_time.dt.year; yrs = (tr.entry_time.iloc[-1] - tr.entry_time.iloc[0]).days / 365.25
    eq = (tr.pts_net * QTY).cumsum(); dd = (eq - eq.cummax()).min()
    return dict(variant=name, trades=len(tr), trades_yr=round(len(tr) / yrs), win=round((tr.pts_gross > 0).mean() * 100, 1),
                TP=int((tr.why == "TP").sum()), SL=int((tr.why == "SL").sum()), EOD=int((tr.why == "EOD").sum()),
                gross_pts=round(tr.pts_gross.sum()), net_pts=round(tr.pts_net.sum()), net_rs=round(tr.pts_net.sum() * QTY),
                net_rs_yr=round(tr.pts_net.sum() * QTY / yrs), avg_net_pts=round(tr.pts_net.mean(), 2), max_dd_rs=round(dd),
                profit_factor=round(tr.pts_net[tr.pts_net > 0].sum() / -tr.pts_net[tr.pts_net < 0].sum(), 2),
                last2y_net_rs=round(tr[tr.entry_time >= tr.entry_time.iloc[-1] - pd.DateOffset(years=2)].pts_net.sum() * QTY))

if __name__ == "__main__":
    V = [("Base: any FVG, valid 1 hr", dict()),
         ("FVG >= 5 pts", dict(mingap=5)), ("FVG >= 10 pts", dict(mingap=10)), ("FVG >= 20 pts", dict(mingap=20)),
         ("valid 30 min", dict(valid=6)), ("valid rest of day", dict(valid=80)),
         ("longs only", dict(side="long")), ("shorts only", dict(side="short")),
         ("SL 30 / TP 60", dict(tp=60)), ("SL 20 / TP 40", dict(sl=20, tp=40))]
    rows = []; base = None
    for name, kw in V:
        tr = run(**kw); rows.append(summ(tr, name)); print(rows[-1], flush=True)
        if base is None: base = tr
    R = pd.DataFrame(rows); pd.set_option("display.width", 260); print(R.to_string(index=False))
    R.to_csv("fvg_summary.csv", index=False); base.to_csv("fvg_trades_base.csv", index=False)
    base["yr"] = base.entry_time.dt.year
    Y = base.groupby("yr").agg(trades=("pts_net", "size"), win=("pts_gross", lambda x: round((x > 0).mean() * 100, 1)),
                               gross_pts=("pts_gross", "sum"), net_pts=("pts_net", "sum"))
    Y["net_rs"] = (Y.net_pts * QTY).round(); Y["avg_nifty"] = base.groupby("yr").entry.mean().round()
    print(Y.round(0).to_string()); Y.round(1).to_csv("fvg_yearly_base.csv")
