"""Nifty expiry day (2016-2026, 439 days, rebuilt minute prices calibrated to the real 9:15 bhavcopy straddle) - same 4 rules as the Sensex test.
Spot SL for the course rule scaled to Nifty: 150 pts (~ Sensex 500 pts). Lot 65, strikes 50."""
src = open("sensex_expiry.py").read()
fn = src[src.index("def straddle("):src.index("V = {")]
exec(open("improve.py").read().split("def sim(")[0])        # loads Nifty PRE (with true iv per day), bsv, cost, LOT=65, hm
STEP = 50
exec(fn)
import pandas as pd
V = {"A  Course: 9:16 straddle, 150-pt spot SL": [dict(entry="09:16", sl=9, spot_sl=150)],
     "B  A + paper check at 9:36": [dict(entry="09:16", sl=9, spot_sl=150, paper="09:36")],
     "C  10:05 straddle, 30% SL/leg (1 lot)": [dict(entry="10:05")],
     "D  3 lots 9:22/9:35/10:05, 40% SL + cost + re-entry": [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:22", "09:35", "10:05")]}
rows = []
for name, legs in V.items():
    s = {}
    for p in PRE:
        r = [straddle(p, **kw) for kw in legs]
        if all(x is None for x in r): continue
        s[p["dt"]] = sum(x for x in r if x is not None) * LOT
    s = pd.Series(s); eq = s.cumsum(); yr = s.groupby(s.index.year).sum(); w = s[s.index >= "2019-01-01"]
    rows.append(dict(rule=name, days=len(s), win=round((s > 0).mean() * 100, 1), rs_yr_2019_26=round(w.sum() / 7.8), worst_day=round(s.min()),
                     max_dd=round((eq - eq.cummax()).min()), losing_yrs=int((yr < 0).sum()), y2023=round(yr.get(2023, 0)), y2024=round(yr.get(2024, 0)),
                     y2025=round(yr.get(2025, 0)), y2026=round(yr.get(2026, 0))))
R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("nifty_rules_compare.csv", index=False)
