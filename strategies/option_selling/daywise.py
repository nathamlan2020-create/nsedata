"""Day-wise / month-wise / year-wise P&L for the two 3-lot expiry-day straddle sets (rebuilt minute prices, 30% SL/leg, exit 15:15, Rs at 65 qty/lot)."""
src = open("entry_time.py").read().split("TIMES = ")[0]; exec(src)
T = ["09:22", "09:35", "09:45", "10:05", "10:35"]
res = {et: pd.DataFrame([dict(date=dt, **dict(zip(("pnl", "stops", "prem"), trade(b, iv, et, 0.30)))) for dt, b, iv, _ in days]).set_index("date") for et in T}
vix = pd.read_csv("/home/claude/nsedata/daily/extra/INDIAVIX.csv", parse_dates=["Date"]).set_index("Date").close.shift(1)
spot = pd.Series({dt: b.open.iloc[0] for dt, b, iv, _ in days})
out = {}
for name, legs in (("Set A 9:22+9:35+10:05", ["09:22", "09:35", "10:05"]), ("Set B 9:45+10:05+10:35", ["09:45", "10:05", "10:35"])):
    d = pd.DataFrame(index=res[legs[0]].index); d.index.name = "date"
    d["day"] = d.index.day_name(); d["nifty_open"] = spot.reindex(d.index).round(1); d["vix_prev_close"] = vix.reindex(d.index, method="ffill").round(2)
    for et in legs:
        d[f"{et} premium pts"] = res[et].prem.round(1); d[f"{et} P&L Rs"] = (res[et].pnl * LOT).round(0); d[f"{et} legs stopped"] = res[et].stops
    d["Total P&L Rs (3 lots)"] = d[[f"{et} P&L Rs" for et in legs]].sum(axis=1); d["Cumulative Rs"] = d["Total P&L Rs (3 lots)"].cumsum()
    d["Drawdown Rs"] = d["Cumulative Rs"] - d["Cumulative Rs"].cummax()
    out[name] = d
pd.to_pickle(out, f"{SP}/daywise.pkl")
