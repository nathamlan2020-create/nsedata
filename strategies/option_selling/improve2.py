"""Combinations of the robust improvements found in improve.py."""
exec(open("improve.py").read().split("V = [")[0])
V = [("Base: SL 30%/leg, exit 15:15", dict()),
     ("SL 30% + other to cost + re-enter", dict(be=True, reentry=True)),
     ("SL 40% + other to cost + re-enter", dict(sl=0.40, be=True, reentry=True)),
     ("SL 50% + other to cost + re-enter", dict(sl=0.50, be=True, reentry=True)),
     ("SL 40% + other to cost + re-enter + exit 15:25", dict(sl=0.40, be=True, reentry=True, exit_t="15:25")),
     ("SL 30% + other to cost + re-enter + exit 15:25", dict(be=True, reentry=True, exit_t="15:25"))]
rows = []; daily = {}
for sname, legs in SETS.items():
    for vname, kw in V:
        s = pd.Series({p["dt"]: sum(sim(p, et, **kw) for et in legs) for p in PRE}) * LOT
        daily[(sname, vname)] = s; eq = s.cumsum(); yr = s.groupby(s.index.year).sum()
        rows.append(dict(set=sname, variant=vname, rs_total=round(s.sum()), rs_yr_2019_26=round(s[s.index >= "2019-01-01"].sum() / 7.8),
                         h1_2016_22=round(s[s.index < "2023-01-01"].sum()), h2_2023_26=round(s[s.index >= "2023-01-01"].sum()),
                         win=round((s > 0).mean() * 100, 1), worst_day=round(s.min()), max_dd=round((eq - eq.cummax()).min()), losing_yrs=int((yr < 0).sum()),
                         worst_month=round(s.groupby(s.index.to_period("M")).sum().min())))
R = pd.DataFrame(rows); R.to_csv("improve2_summary.csv", index=False); pd.to_pickle(daily, f"{SP}/improve2_daily.pkl")
pd.set_option("display.width", 250); print(R.to_string(index=False))
Y = pd.DataFrame({f"{k[0]} | {k[1]}": v.groupby(v.index.year).sum() for k, v in daily.items()}).round(-2)
print(Y.T.to_string())
