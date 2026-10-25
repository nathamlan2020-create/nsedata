"""Nifty expiry-day ATM straddle, 30% SL per leg, exit 15:15 - effect of the ENTRY TIME (9:15 ... 10:05). 2016-2026.

Historic minute-by-minute option prices are not published, so each expiry day is rebuilt:
 * real Nifty 1-minute path (Kite)
 * option prices = Black-Scholes (r=6.5%) with that day's implied vol, solved so the model 9:15 straddle equals the
   ACTUAL 9:15 open straddle in the NSE bhavcopy (flat smile, IV held for the day)
 * ATM strike re-chosen at each entry time (nearest 50), stops checked every minute against the minute's spot high/low
   (conservative: CE checked at the high, PE at the low), stop fill +1% slippage, exit 15:15 at the model price.
 Costs as before: STT 0.1% sell, ~0.04% other per side, Rs 40 brokerage, 0.5 pt slippage/side; Rs per lot at 65 qty."""
import numpy as np, pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"
D = pd.read_pickle(f"{SP}/idxopt.pkl"); D = D[(D.sym == "NIFTY") & (D.date == D.exp)]
m = pd.read_csv("/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz", parse_dates=["date"]).set_index("date").sort_index()
LOT, R, YM = 65, 0.065, 375 * 252
def bs(S, K, T, v, cp):
    T = max(T, 1e-7); d1 = (np.log(S / K) + (R + v * v / 2) * T) / (v * np.sqrt(T)); d2 = d1 - v * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-R * T) * norm.cdf(d2) if cp == "C" else K * np.exp(-R * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
def cost(pi, po): return pi * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 1.0
def mins_left(t): return (pd.Timestamp(t.date()) + pd.Timedelta(hours=15, minutes=30) - t).total_seconds() / 60

days = []; MD = set(m.index.normalize().unique())
for dt, g in D.groupby("date"):
    b = m.loc[str(dt.date())] if dt in MD else None
    if b is None or len(b) < 300: continue
    ce = g[g.typ == "CE"].set_index("k"); pe = g[g.typ == "PE"].set_index("k"); ks = ce.index.intersection(pe.index)
    ks = ks[(ce.loc[ks, "o"] > 0).values & (pe.loc[ks, "o"] > 0).values]
    if len(ks) < 3: continue
    s0 = b.open.iloc[0]; k0 = ks[np.abs(ks - s0).argmin()]
    strad = float(ce.at[k0, "o"] + pe.at[k0, "o"]); T0 = mins_left(b.index[0]) / YM
    f = lambda v: bs(s0, k0, T0, v, "C") + bs(s0, k0, T0, v, "P") - strad
    try: iv = brentq(f, 0.01, 3.0)
    except ValueError: continue
    days.append((dt, b, iv, strad))
print("expiry days rebuilt:", len(days), " median open IV", round(np.median([d[2] for d in days]) * 100, 1), "%")

def trade(b, iv, et, sl=0.30, step=50):
    b = b[b.index.time >= pd.Timestamp(et).time()]
    t0 = b.index[0]; s0 = b.open.iloc[0]; k = round(s0 / step) * step; T = mins_left(t0) / YM
    e = {"C": bs(s0, k, T, iv, "C"), "P": bs(s0, k, T, iv, "P")}; pnl = 0.0; stops = 0; open_ = {"C": True, "P": True}
    for t, row in b.iterrows():
        T = mins_left(t) / YM
        if t.time() >= pd.Timestamp("15:15").time():
            for cp in ("C", "P"):
                if open_[cp]: x = bs(row.open, k, T, iv, cp); pnl += e[cp] - x - cost(e[cp], x); open_[cp] = False
            break
        if sl is None: continue
        for cp, sx in (("C", row.high), ("P", row.low)):
            if open_[cp] and bs(sx, k, T, iv, cp) >= e[cp] * (1 + sl):
                x = e[cp] * (1 + sl) * 1.01; pnl += e[cp] - x - cost(e[cp], x); open_[cp] = False; stops += 1
    return pnl, stops, e["C"] + e["P"]

TIMES = ["09:15", "09:16", "09:20", "09:22", "09:35", "10:05"]
res = {}
for et in TIMES:
    for sl in (0.30, None):
        rows = [dict(date=dt, **dict(zip(("pnl", "stops", "prem"), trade(b, iv, et, sl)))) for dt, b, iv, _ in days]
        res[(et, sl)] = pd.DataFrame(rows).set_index("date"); print(et, sl, round(res[(et, sl)].pnl.mean(), 2), flush=True)
def summ(t, name):
    rs = t.pnl * LOT; eq = rs.cumsum(); yrs = (t.index[-1] - t.index[0]).days / 365.25; yr = rs.groupby(t.index.year).sum()
    l2 = rs[rs.index >= rs.index[-1] - pd.DateOffset(years=2)]
    return dict(entry=name, trades=len(t), win=round((t.pnl > 0).mean() * 100, 1), avg_premium=round(t.prem.mean(), 1), avg_pts=round(t.pnl.mean(), 1),
                rs_per_lot_yr=round(rs.sum() / yrs), worst_day_rs=round(rs.min()), max_dd_rs=round((eq - eq.cummax()).min()),
                losing_yrs=int((yr < 0).sum()), both_legs_stopped_pct=round((t.stops == 2).mean() * 100, 1), last2y_rs=round(l2.sum()))
S = pd.DataFrame([summ(res[(et, 0.30)], et + " SL30%") for et in TIMES] + [summ(res[(et, None)], et + " no SL") for et in TIMES])
combo = (res[("09:22", 0.30)].pnl + res[("09:35", 0.30)].pnl + res[("10:05", 0.30)].pnl).to_frame("pnl")
combo["stops"] = 0; combo["prem"] = res[("09:22", 0.30)].prem + res[("09:35", 0.30)].prem + res[("10:05", 0.30)].prem
cs = summ(combo, "3 lots: 9:22 + 9:35 + 10:05 (SL30% each)"); S = pd.concat([S, pd.DataFrame([cs])], ignore_index=True)
pd.set_option("display.width", 250); print(S.to_string(index=False)); S.to_csv("entry_time_summary.csv", index=False)
Y = pd.DataFrame({et: res[(et, 0.30)].pnl.groupby(res[(et, 0.30)].index.year).sum() * LOT for et in TIMES}); Y["3 lots combined"] = combo.pnl.groupby(combo.index.year).sum() * LOT
print(Y.round(-2).to_string()); Y.round(0).to_csv("entry_time_yearly.csv")
print("corr of daily P&L:\n", pd.DataFrame({et: res[(et, 0.30)].pnl for et in ("09:22", "09:35", "10:05")}).corr().round(2))
pd.to_pickle(res, f"{SP}/entry_res.pkl")
