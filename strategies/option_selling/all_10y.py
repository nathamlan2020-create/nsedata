"""Whole plan over the last 10 years (26 Oct 2016 - Oct 2026):
 Nifty expiry 7 hedged lots (2/2/3 at 9:22/9:35/10:05) + Sensex expiry 7 hedged lots (2/2/3 at 9:45/10:05/10:35, from May 2023)
 with loss limits (day stop -20k, re-entry only if day green, account DD > 30k -> 3 lots), + weekend trade 5 lots
 (futures + 1% OTM protective option; Friday direction must agree with 50 EMA and 200 SMA; skip long weekends; Fri close -> Mon open)."""
exec(open("loss_limits.py").read().split("V = [")[0])
import pandas as pd, numpy as np
START = pd.Timestamp("2016-10-26")
DAYS = sorted([("N", p) for p in NS["PRE"] if p["dt"] >= START] + [("S", p) for p in SS["PRE"]], key=lambda x: x[1]["dt"])
exp = run(day_stop=20000, green=True, dd_resize=30000)
nd = {p["dt"] for k, p in DAYS if k == "N"}
w = pd.read_csv("/home/claude/nsedata/strategies/weekend_gap/weekend_v2_trades.csv", index_col=0, parse_dates=True).iloc[:, 0] * 5
w = w[w.index >= START]
D = pd.DataFrame({"nifty": exp[exp.index.isin(nd)], "sensex": exp[~exp.index.isin(nd)]}).join(w.rename("weekend"), how="outer").fillna(0)
D["total"] = D.sum(axis=1)
pd.to_pickle(D, f"{SP}/all10y.pkl"); D.to_csv("all_strategies_10y_daily.csv")
yrs = (D.index[-1] - D.index[0]).days / 365.25; eq = D.total.cumsum(); M = D.groupby(D.index.to_period("M")).sum(); Y = D.groupby(D.index.year).sum()
Y["pct_7_5L"] = (Y.total / CAP * 100).round(0)
ydd = {y: round((lambda e: (e - e.cummax()).min())(D.total[D.index.year == y].cumsum())) for y in Y.index}; Y["year_maxDD"] = pd.Series(ydd)
pd.set_option("display.width", 220); print(Y.round(0).to_string())
for c in ("nifty", "sensex", "weekend", "total"):
    s = D[c]; s = s[s != 0]; e_ = s.cumsum()
    print(f"{c:8s} total Rs {s.sum():,.0f} | Rs/yr {s.sum()/yrs:,.0f} | trades {len(s)} | win {(s>0).mean()*100:.0f}% | worst {s.min():,.0f} | maxDD {(e_-e_.cummax()).min():,.0f}")
print(f"PLAN: losing months {(M.total<0).sum()}/{len(M)}, worst month {M.total.min():,.0f}, best month {M.total.max():,.0f}, avg month {M.total.mean():,.0f}")
MM = M.total.groupby([M.index.year, M.index.month]).sum().unstack().reindex(columns=range(1, 13)).fillna(0).round(0)
MM.columns = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]; MM["Total"] = MM.sum(axis=1); print(MM.to_string())
M.to_csv("all_strategies_10y_monthly.csv"); Y.to_csv("all_strategies_10y_yearly.csv")
