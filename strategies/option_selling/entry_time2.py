"""Same rebuild as entry_time.py (Nifty expiry-day ATM straddle, 30% SL/leg, exit 15:15) for entries 9:45 / 10:05 / 10:35 (+ 11:05, 11:35 for context)
and the 3-lot combination 9:45 + 10:05 + 10:35. Also the VIX>18 -> 2 lots sizing."""
src = open("entry_time.py").read().split("TIMES = ")[0]; exec(src)
TIMES = ["09:45", "10:05", "10:35", "11:05", "11:35"]
res = {et: pd.DataFrame([dict(date=dt, **dict(zip(("pnl", "stops", "prem"), trade(b, iv, et, 0.30)))) for dt, b, iv, _ in days]).set_index("date") for et in TIMES}
def summ(t, name):
    rs = t.pnl * LOT; eq = rs.cumsum(); yrs = (t.index[-1] - t.index[0]).days / 365.25; yr = rs.groupby(t.index.year).sum()
    return dict(entry=name, trades=len(t), win=round((t.pnl > 0).mean() * 100, 1), avg_premium=round(t.prem.mean(), 1), avg_pts=round(t.pnl.mean(), 1),
                rs_per_lot_yr=round(rs.sum() / yrs), worst_day_rs=round(rs.min()), max_dd_rs=round((eq - eq.cummax()).min()), losing_yrs=int((yr < 0).sum()),
                both_legs_stopped_pct=round((t.stops == 2).mean() * 100, 1))
c = (res["09:45"].pnl + res["10:05"].pnl + res["10:35"].pnl).to_frame("pnl"); c["stops"] = 0; c["prem"] = res["09:45"].prem + res["10:05"].prem + res["10:35"].prem
old = pd.read_pickle(f"{SP}/entry_res.pkl"); o = (old[("09:22", 0.3)].pnl + old[("09:35", 0.3)].pnl + old[("10:05", 0.3)].pnl).to_frame("pnl"); o["stops"] = 0; o["prem"] = 0
S = pd.DataFrame([summ(res[et], et) for et in TIMES] + [summ(c, "3 lots: 9:45 + 10:05 + 10:35"), summ(o, "3 lots: 9:22 + 9:35 + 10:05 (earlier)")])
pd.set_option("display.width", 250); print(S.to_string(index=False)); S.to_csv("entry_time2_summary.csv", index=False)
Y = pd.DataFrame({et: res[et].pnl.groupby(res[et].index.year).sum() * LOT for et in ("09:45", "10:05", "10:35")})
Y["3 lots 9:45+10:05+10:35"] = c.pnl.groupby(c.index.year).sum() * LOT; Y["3 lots 9:22+9:35+10:05"] = o.pnl.groupby(o.index.year).sum() * LOT
print(Y.round(-2).to_string()); Y.round(0).to_csv("entry_time2_yearly.csv")
print(pd.DataFrame({et: res[et].pnl for et in ("09:45", "10:05", "10:35")}).corr().round(2))
v = pd.read_csv("/home/claude/nsedata/daily/extra/INDIAVIX.csv", parse_dates=["Date"]).set_index("Date").close.shift(1).reindex(c.index, method="ffill")
w = np.where(v > 18, 2, 1); b = c.pnl * w * LOT
print("VIX>18 -> 2x:", round(b.sum() / 10.8), "/yr, maxDD", round((b.cumsum() - b.cumsum().cummax()).min()), " worst day", round(b.min()), " losing yrs", int((b.groupby(b.index.year).sum() < 0).sum()))
