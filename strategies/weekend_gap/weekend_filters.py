"""Drawdown controls for the hedged weekend trade (futures + 1% OTM protective option, 1 lot = 65):
 trend filter = only trade when Friday's direction agrees with Nifty vs its 50-day EMA (up & above -> long; down & below -> short);
 monthly stop = no more weekend trades that month once month-to-date P&L <= -Rs 15,000; combined."""
import pandas as pd, numpy as np
T = pd.read_csv("weekend_hedged_trades.csv", index_col=0, parse_dates=True); LOT = 65
m = pd.read_csv("/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz", parse_dates=["date"]).set_index("date")
dc = m.close.resample("D").last().dropna(); ema = dc.ewm(span=50, adjust=False).mean()
above = (dc > ema).reindex(T.index)
trend_ok = ((T.dir == 1) & above) | ((T.dir == -1) & ~above)
def run(col, use_trend=False, mstop=None):
    out = {}; mtd = {}
    for d, r in T.iterrows():
        mo = d.to_period("M")
        if use_trend and not trend_ok.loc[d]: continue
        if mstop is not None and mtd.get(mo, 0) <= -mstop: continue
        v = r[col] * LOT; out[d] = v; mtd[mo] = mtd.get(mo, 0) + v
    return pd.Series(out)
yrs = (T.index[-1] - T.index[0]).days / 365.25; rows = []; keep = {}
for col, cn in (("fut", "Futures no hedge"), ("hedge1", "Futures + 1% hedge")):
    for nm, kw in (("no filter", {}), ("trend filter", dict(use_trend=True)), ("monthly stop -15k", dict(mstop=15000)), ("trend + monthly stop", dict(use_trend=True, mstop=15000))):
        s = run(col, **kw); keep[(cn, nm)] = s; eq = s.cumsum(); M = s.groupby(s.index.to_period("M")).sum(); yr = s.groupby(s.index.year).sum()
        rows.append(dict(version=f"{cn} | {nm}", trades=len(s), win=round((s > 0).mean() * 100, 1), rs_per_yr=round(s.sum() / yrs), worst_weekend=round(s.min()),
                         max_dd=round((eq - eq.cummax()).min()), worst_month=round(M.min()), losing_months=int((M < 0).sum()), losing_yrs=int((yr < 0).sum()),
                         avg_16_20=round(s[s.index < "2021"].mean()), avg_21_26=round(s[s.index >= "2021"].mean()), ret_dd=round(s.sum() / yrs / -(eq - eq.cummax()).min(), 2)))
R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("weekend_filters_summary.csv", index=False)
best = ("Futures + 1% hedge", "trend + monthly stop"); s = keep[best]
M = s.groupby([s.index.year, s.index.month]).sum().unstack().reindex(columns=range(1, 13)).fillna(0).round(0)
M.columns = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]; M["Total"] = M.sum(axis=1)
dd = {y: round((lambda e: (e - e.cummax()).min())(s[s.index.year == y].cumsum())) for y in M.index}; M["MDD"] = pd.Series(dd)
print("\nMonthly Rs per lot -", best, "\n", M.to_string()); M.to_csv("weekend_best_monthly.csv")
pd.Series(s).to_csv("weekend_best_trades.csv")
