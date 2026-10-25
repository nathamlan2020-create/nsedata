"""Does India VIX improve the Nifty expiry-day straddle (30% SL/leg, exit 15:15)?  Only information known before entry is used:
 vix_prev  = yesterday's VIX close;  vix_pct = its percentile in the last 252 days;  vix_5d = change over the last 5 days;
 vix_gap   = today's VIX open vs yesterday's close (known by 9:15, usable for 9:22+ entries).
Checked on the rebuilt minute-level trades (9:22 / 9:35 / 10:05 / all 3) and on the real-price bhavcopy version (9:15 open -> close)."""
import numpy as np, pandas as pd
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"; LOT = 65
res = pd.read_pickle(f"{SP}/entry_res.pkl"); K = pd.read_pickle(f"{SP}/optsell_trades.pkl")
v = pd.read_csv("/home/claude/nsedata/daily/extra/INDIAVIX.csv", parse_dates=["Date"]).set_index("Date").sort_index()
F = pd.DataFrame({"vix_prev": v.close.shift(1), "vix_open": v.open})
F["vix_pct"] = v.close.rolling(252).rank(pct=True).shift(1); F["vix_5d"] = v.close.shift(1) / v.close.shift(6) - 1
F["vix_gap"] = np.where((v.open - v.close.shift(1)).abs() > 1e-6, v.open / v.close.shift(1) - 1, np.nan)
T = {"9:22": res[("09:22", 0.3)].pnl, "9:35": res[("09:35", 0.3)].pnl, "10:05": res[("10:05", 0.3)].pnl}
T["All 3 lots"] = T["9:22"] + T["9:35"] + T["10:05"]
real = K["Expiry day only: straddle SL 30%"]; real = real[real.sym == "NIFTY"].set_index("date").pnl_pts; T["Real prices 9:15 (bhavcopy)"] = real
X = pd.DataFrame(T).join(F, how="left"); X["vix_prev"] = X.vix_prev.ffill()
print("days with VIX:", X.vix_prev.notna().sum(), " VIX-open usable on", X.vix_gap.notna().sum(), "days")
pd.set_option("display.width", 250)
# 1) buckets
X["VIX level"] = pd.cut(X.vix_prev, [0, 11, 13, 15, 18, 22, 99], labels=["<11", "11-13", "13-15", "15-18", "18-22", ">22"])
B = X.groupby("VIX level", observed=True).agg(days=("9:22", "size"), **{f"{k} avg pts": (k, "mean") for k in T})
print("\nAVG PROFIT (pts per day) BY YESTERDAY'S VIX\n", B.round(1).to_string())
X["VIX 5d change"] = pd.cut(X.vix_5d, [-1, -0.10, -0.03, 0.03, 0.10, 9], labels=["fell >10%", "fell 3-10%", "flat", "rose 3-10%", "rose >10%"])
print("\nBY VIX 5-DAY CHANGE\n", X.groupby("VIX 5d change", observed=True).agg(days=("9:22", "size"), **{f"{k}": (k, "mean") for k in T}).round(1).to_string())
X["VIX gap at open"] = pd.cut(X.vix_gap, [-1, -0.03, 0.03, 0.08, 9], labels=["down >3%", "flat", "up 3-8%", "up >8%"])
print("\nBY VIX GAP AT 9:15 (days with a real VIX open)\n", X.groupby("VIX gap at open", observed=True).agg(days=("9:22", "size"), **{f"{k}": (k, "mean") for k in T}).round(1).to_string())
# 2) candidate filters, checked in two halves
RULES = {"No filter": pd.Series(True, index=X.index),
         "Skip if VIX > 22": ~(X.vix_prev > 22), "Skip if VIX > 18": ~(X.vix_prev > 18), "Skip if VIX < 11": ~(X.vix_prev < 11),
         "Trade only VIX 11-22": X.vix_prev.between(11, 22), "Skip if VIX rose >10% in 5d": ~(X.vix_5d > 0.10),
         "Skip if VIX gaps up >8% at open": ~(X.vix_gap > 0.08), "Skip if VIX in top 20% of its year": ~(X.vix_pct > 0.8),
         "VIX 11-22 and not rising >10%": X.vix_prev.between(11, 22) & ~(X.vix_5d > 0.10)}
out = []
for name, keep in RULES.items():
    for k in T:
        s = X[k][keep.fillna(True)]; rs = s * LOT; eq = rs.cumsum(); yr = rs.groupby(s.index.year).sum()
        h1 = s[s.index < "2021-01-01"].mean(); h2 = s[s.index >= "2021-01-01"].mean()
        out.append(dict(rule=name, trades_on=k, days=len(s), avg_pts=round(s.mean(), 1), avg_2016_20=round(h1, 1), avg_2021_26=round(h2, 1),
                        rs_yr=round(rs.sum() / 10.8), worst_day=round(rs.min()), max_dd=round((eq - eq.cummax()).min()), losing_yrs=int((yr < 0).sum())))
O = pd.DataFrame(out)
for k in T: print(f"\n=== {k} ===\n", O[O.trades_on == k].drop(columns="trades_on").to_string(index=False))
O.to_csv("vix_filter_summary.csv", index=False); B.round(2).to_csv("vix_buckets.csv")
# 3) size by VIX: 2x lots when VIX 13-18 else 1x (all-3 version)
w = np.where(X.vix_prev.between(13, 18), 2, 1)
for k in ("All 3 lots", "10:05"):
    a = X[k] * LOT; b = X[k] * w * LOT
    print(k, "sizing 2x at VIX 13-18: Rs/yr", round(b.sum() / 10.8), "vs", round(a.sum() / 10.8), "| maxDD", round((b.cumsum() - b.cumsum().cummax()).min()), "vs", round((a.cumsum() - a.cumsum().cummax()).min()))
