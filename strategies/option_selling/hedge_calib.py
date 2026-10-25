"""Calibrate the vol 'skew' of ~Rs 1 far-OTM options on Nifty expiry days from the real NSE bhavcopy 9:15 open prices:
IV of the strike whose open premium is closest to Rs 1 (0.5-2.5), divided by that day's ATM open IV."""
import numpy as np, pandas as pd
from scipy.optimize import brentq
exec(open("entry_time.py").read().split("def trade(")[0])
ivd = {dt: iv for dt, b, iv, _ in days}; s0d = {dt: b.open.iloc[0] for dt, b, iv, _ in days}
rows = []
for dt, g in D.groupby("date"):
    if dt not in ivd: continue
    s0 = s0d[dt]; T = mins_left(pd.Timestamp(dt) + pd.Timedelta(hours=9, minutes=15)) / YM
    for cp, typ in (("C", "CE"), ("P", "PE")):
        x = g[(g.typ == typ) & (g.o.between(0.5, 2.5)) & (g.vol > 0)]
        x = x[(x.k > s0) if cp == "C" else (x.k < s0)]
        if x.empty: continue
        r = x.iloc[(x.o - 1).abs().argmin()]
        try: iv = brentq(lambda v: bs(s0, r.k, T, v, cp) - r.o, 0.01, 5)
        except ValueError: continue
        rows.append(dict(date=dt, cp=cp, prem=r.o, dist_pct=abs(r.k / s0 - 1) * 100, iv_ratio=iv / ivd[dt]))
X = pd.DataFrame(rows); X["year"] = X.date.dt.year
print(X.groupby(["cp"])[["prem", "dist_pct", "iv_ratio"]].median().round(3))
print(X[X.year >= 2023].groupby(["year", "cp"])[["dist_pct", "iv_ratio"]].median().round(2).unstack())
X.to_csv("hedge_calibration.csv", index=False)
