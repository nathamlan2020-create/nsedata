"""Friday-afternoon -> Monday-open strategies on Nifty, 2016-2026.
A) Gap statistics + directional signals from Friday intraday (Kite 1-min index):  signal measured 12:30 -> 15:20 on Friday;
   trade Nifty futures proxy: enter 15:20 Friday, exit Monday 9:16 (index points, cost 2 pts round trip incl. slippage).
B) Options with REAL NSE prices (bhavcopy): ATM straddle of the nearest expiry that is still alive on Monday,
   bought (or sold) at Friday CLOSE price, exited at Monday OPEN price. Costs per leg as in sell_bt (STT on sell side, charges, Rs40, slippage)."""
import numpy as np, pandas as pd
m = pd.read_csv("/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz", parse_dates=["date"]).set_index("date").sort_index()
m = m[m.index >= "2016-01-01"]
days = sorted(set(m.index.normalize()))
rows = []
for i in range(len(days) - 1):
    d, n = days[i], days[i + 1]
    if d.weekday() != 4 or (n - d).days < 3: continue           # Friday followed by a weekend
    f = m.loc[str(d.date())]; mo = m.loc[str(n.date())]
    def px(df, hhmm, col="close"):
        x = df.between_time(hhmm, "15:30")
        return float(x[col].iloc[0]) if len(x) else np.nan
    o = f.open.iloc[0]; p1230 = px(f, "12:30"); p1520 = px(f, "15:20"); c = f.close.iloc[-1]
    mon_open = float(mo.open.iloc[0]); mon_916 = px(mo, "09:16"); mon_hi = mo.high.iloc[:15].max(); mon_lo = mo.low.iloc[:15].min()
    rows.append(dict(fri=d, mon=n, fri_open=o, fri_1230=p1230, fri_1520=p1520, fri_close=c, fri_hi=f.high.max(), fri_lo=f.low.min(),
                     mon_open=mon_open, mon_916=mon_916))
G = pd.DataFrame(rows).set_index("fri")
G["gap_pct"] = (G.mon_open / G.fri_close - 1) * 100
G["aft_ret"] = (G.fri_1520 / G.fri_1230 - 1) * 100; G["day_ret"] = (G.fri_close / G.fri_open - 1) * 100
G["close_pos"] = (G.fri_close - G.fri_lo) / (G.fri_hi - G.fri_lo)
print("Weekends:", len(G), "| Monday gap: mean %.3f%%, median %.3f%%, abs mean %.2f%%, up %.0f%%, >0.5%% %d, >1%% %d" % (
    G.gap_pct.mean(), G.gap_pct.median(), G.gap_pct.abs().mean(), (G.gap_pct > 0).mean() * 100, (G.gap_pct.abs() > 0.5).sum(), (G.gap_pct.abs() > 1).sum()))
print("corr(gap, Fri 12:30-15:20 move) = %.3f | corr(gap, Fri day move) = %.3f | corr(gap, close position in range) = %.3f" % (
    G.gap_pct.corr(G.aft_ret), G.gap_pct.corr(G.day_ret), G.gap_pct.corr(G.close_pos)))
def fut(sig, name):
    pts = sig * (G.mon_916 - G.fri_1520) - 2.0 * sig.abs()
    t = pts[sig != 0]; yr = t.groupby(t.index.year).sum()
    return dict(rule=name, trades=len(t), win=round((t > 0).mean() * 100, 1), avg_pts=round(t.mean(), 1), total_pts=round(t.sum()),
                rs_per_lot_yr_65=round(t.sum() * 65 / ((G.index[-1] - G.index[0]).days / 365.25)), worst_pts=round(t.min()), losing_yrs=int((yr < 0).sum()))
A = pd.DataFrame([fut(pd.Series(1, index=G.index), "Always long Fri 15:20 -> Mon 9:16"),
                  fut(np.sign(G.aft_ret), "Follow Fri 12:30-15:20 move"), fut(-np.sign(G.aft_ret), "Fade Fri 12:30-15:20 move"),
                  fut(np.sign(G.aft_ret).where(G.aft_ret.abs() > 0.3, 0), "Follow afternoon move only if > 0.3%"),
                  fut(np.sign(G.day_ret), "Follow Friday's full-day move"),
                  fut(pd.Series(np.where(G.close_pos > 0.8, 1, np.where(G.close_pos < 0.2, -1, 0)), index=G.index), "Close near day high -> long, near low -> short")])
pd.set_option("display.width", 220); print(A.to_string(index=False))
# ---------- B: straddles with real bhavcopy prices ----------
D = pd.read_pickle("/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/idxopt.pkl"); D = D[D.sym == "NIFTY"]
byd = {k: g for k, g in D.groupby("date")}
LOT = 65
def lc(pi, po, sell_first): return (pi if sell_first else po) * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 1.0
out = []
for fri, r in G.iterrows():
    if fri not in byd or r.mon not in byd: continue
    gf, gm = byd[fri], byd[r.mon]
    ex = sorted(e for e in gf.exp.unique() if e >= r.mon)
    if not ex: continue
    e = ex[0]; f = gf[gf.exp == e]; mo = gm[gm.exp == e]
    ce = f[f.typ == "CE"].set_index("k"); pe = f[f.typ == "PE"].set_index("k"); ks = ce.index.intersection(pe.index)
    ks = ks[(ce.loc[ks, "c"] > 0).values & (pe.loc[ks, "c"] > 0).values]
    if len(ks) < 3: continue
    k = (ce.loc[ks, "c"] - pe.loc[ks, "c"]).abs().idxmin()
    mc = mo[(mo.typ == "CE") & (mo.k == k)]; mp = mo[(mo.typ == "PE") & (mo.k == k)]
    if mc.empty or mp.empty or mc.o.iloc[0] <= 0 or mp.o.iloc[0] <= 0: continue
    ec, ep = float(ce.at[k, "c"]), float(pe.at[k, "c"]); xc, xp = float(mc.o.iloc[0]), float(mp.o.iloc[0])
    long_ = (xc + xp - ec - ep) - lc(ec, xc, False) - lc(ep, xp, False)
    short_ = (ec + ep - xc - xp) - lc(ec, xc, True) - lc(ep, xp, True)
    out.append(dict(fri=fri, dte_mon=(e - r.mon).days, prem=ec + ep, gap_pct=r.gap_pct, long_pts=long_, short_pts=short_))
B = pd.DataFrame(out).set_index("fri")
yrs = (B.index[-1] - B.index[0]).days / 365.25
for col, nm in (("long_pts", "BUY ATM straddle Fri close -> SELL Mon open"), ("short_pts", "SELL ATM straddle Fri close -> BUY Mon open")):
    t = B[col]; yr = t.groupby(t.index.year).sum()
    print(f"{nm}: n={len(t)} win={(t>0).mean()*100:.0f}% avg={t.mean():.1f} pts  Rs/lot/yr={t.sum()*LOT/yrs:,.0f}  worst={t.min():.0f} pts  best={t.max():.0f} pts  losing yrs={(yr<0).sum()}")
    print("   by year (Rs/lot):", {y: round(v * LOT) for y, v in yr.items()})
B["absgap"] = B.gap_pct.abs()
print("Long straddle P&L by gap size (pts):\n", B.groupby(pd.cut(B.absgap, [0, 0.25, 0.5, 1, 2, 9])).long_pts.agg(["size", "mean"]).round(1))
print("avg premium paid %.0f pts; break-even gap ~ premium/spot" % B.prem.mean())
G.to_csv("weekend_gaps.csv"); A.to_csv("directional_summary.csv", index=False); B.to_csv("straddle_weekend_trades.csv")
