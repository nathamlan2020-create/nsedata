"""Improving the weekend direction trade (base = futures + 1% OTM protective option, Friday direction must agree with Nifty vs 50 EMA,
Fri close -> Mon open). Real NSE bhavcopy option prices; futures proxied by the index. Lot 65. Each variant shown for 2016-20 and 2021-26."""
import numpy as np, pandas as pd
G = pd.read_csv("weekend_gaps.csv", index_col=0, parse_dates=True); G["mon"] = pd.to_datetime(G.mon)
m = pd.read_csv("/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz", parse_dates=["date"]).set_index("date")
dc = m.close.resample("D").last().dropna(); dh = m.high.resample("D").max().dropna(); dl = m.low.resample("D").min().dropna()
e50 = dc.ewm(span=50, adjust=False).mean(); s200 = dc.rolling(200).mean()
vix = pd.read_csv("/home/claude/nsedata/daily/extra/INDIAVIX.csv", parse_dates=["Date"]).set_index("Date").close
D = pd.read_pickle("/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/idxopt.pkl"); D = D[D.sym == "NIFTY"]
byd = {k: g for k, g in D.groupby("date")}; LOT = 65
def cb(pi, po): return po * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 1.0
rows = []
for fri, r in G.iterrows():
    if fri not in byd or r.mon not in byd or fri not in dc.index or r.mon not in dc.index: continue
    d = 1 if r.fri_close >= r.fri_open else -1
    gf, gm = byd[fri], byd[r.mon]; ex = sorted(x for x in gf.exp.unique() if x >= r.mon)
    if not ex: continue
    e = ex[0]; f = gf[gf.exp == e]; mo = gm[gm.exp == e]; s = r.fri_close
    ks = np.array(sorted(f.k.unique())); near = lambda x: ks[np.abs(ks - x).argmin()]
    def opt(typ, k, col="o"):
        a = f[(f.typ == typ) & (f.k == k)]; b = mo[(mo.typ == typ) & (mo.k == k)]
        if a.empty or b.empty or a.c.iloc[0] <= 0 or b[col].iloc[0] <= 0: return None
        return float(a.c.iloc[0]), float(b[col].iloc[0])
    mon_close = float(dc.loc[r.mon]); typ_h = "PE" if d == 1 else "CE"; kh = near(s * (1 - d * 0.01))
    h_open, h_close = opt(typ_h, kh, "o"), opt(typ_h, kh, "c")
    typ_d = "CE" if d == 1 else "PE"; kitm = near(s * (1 - d * 0.01)); itm_o = opt(typ_d, kitm, "o")
    if h_open is None or h_close is None or itm_o is None: continue
    rows.append(dict(fri=fri, dir=d, long_weekend=(r.mon - fri).days > 3,
        base=d * (r.mon_916 - s) - 2 + (h_open[1] - h_open[0]) - cb(*h_open),
        hold_mon=d * (mon_close - s) - 2 + (h_close[1] - h_close[0]) - cb(*h_close),
        itm_call=(itm_o[1] - itm_o[0]) - cb(*itm_o),
        trend50=bool((d == 1 and dc[fri] > e50[fri]) or (d == -1 and dc[fri] < e50[fri])),
        trend200=bool((d == 1 and dc[fri] > s200[fri]) or (d == -1 and dc[fri] < s200[fri])) if not np.isnan(s200[fri]) else False,
        day_move=abs(r.day_ret), close_pos=(r.fri_close - r.fri_lo) / max(r.fri_hi - r.fri_lo, 1e-9),
        vix=float(vix.reindex([fri], method="ffill").iloc[0])))
T = pd.DataFrame(rows).set_index("fri")
T["strong_close"] = np.where(T.dir == 1, T.close_pos > 0.7, T.close_pos < 0.3)
yrs = (T.index[-1] - T.index[0]).days / 365.25
def rep(name, mask, col="base"):
    s = T.loc[mask, col] * LOT; eq = s.cumsum(); M = s.groupby(s.index.to_period("M")).sum(); yr = s.groupby(s.index.year).sum()
    return dict(variant=name, trades=len(s), win=round((s > 0).mean() * 100, 1), rs_yr=round(s.sum() / yrs), worst=round(s.min()),
                max_dd=round((eq - eq.cummax()).min()), worst_month=round(M.min()), losing_yrs=int((yr < 0).sum()),
                avg_16_20=round(s[s.index < "2021"].mean()), avg_21_26=round(s[s.index >= "2021"].mean()), ret_dd=round(s.sum() / yrs / max(-(eq - eq.cummax()).min(), 1), 2))
B = T.trend50
V = [rep("BASE: 50-EMA trend filter", B),
     rep("+ also above/below 200 SMA", B & T.trend200),
     rep("+ Friday move > 0.3%", B & (T.day_move > 0.3)),
     rep("+ Friday move > 0.5%", B & (T.day_move > 0.5)),
     rep("+ strong close (top/bottom 30% of day range)", B & T.strong_close),
     rep("+ VIX < 20", B & (T.vix < 20)), rep("+ VIX < 16", B & (T.vix < 16)), rep("+ VIX > 13", B & (T.vix > 13)),
     rep("Long side only", B & (T.dir == 1)), rep("Short side only", B & (T.dir == -1)),
     rep("Skip long weekends (3+ day holidays)", B & ~T.long_weekend),
     rep("Exit Monday close instead of open", B, "hold_mon"),
     rep("Buy 1% ITM call/put instead of futures+hedge", B, "itm_call"),
     rep("200 SMA + strong close", B & T.trend200 & T.strong_close),
     rep("200 SMA + move > 0.3%", B & T.trend200 & (T.day_move > 0.3))]
R = pd.DataFrame(V); pd.set_option("display.width", 260); print(R.to_string(index=False)); R.to_csv("weekend_improve_summary.csv", index=False)
T.to_csv("weekend_improve_trades.csv")
