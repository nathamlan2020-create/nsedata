"""'Follow Friday's full-day direction' weekend trade with drawdown control. Direction = sign(Fri close - Fri open).
Entry at Friday close, exit at Monday open (real NSE bhavcopy option prices: Fri CLOSE, Mon OPEN; futures proxied by the index
Fri close -> Mon 9:16). Nearest expiry still alive on Monday. Lot 65. Costs: futures 2 pts round trip; options per leg STT 0.1% on sell,
0.04%/side charges, Rs 40 brokerage, 0.5 pt slippage/side."""
import numpy as np, pandas as pd
G = pd.read_csv("weekend_gaps.csv", index_col=0, parse_dates=True, dtype={"mon": str}); G["mon"] = pd.to_datetime(G.mon)
D = pd.read_pickle("/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/idxopt.pkl"); D = D[D.sym == "NIFTY"]
byd = {k: g for k, g in D.groupby("date")}; LOT = 65
def cbuy(pi, po): return po * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 1.0     # bought at pi, sold at po
def csell(pi, po): return pi * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 1.0
rows = []
for fri, r in G.iterrows():
    if fri not in byd or r.mon not in byd: continue
    d = 1 if r.fri_close >= r.fri_open else -1
    gf, gm = byd[fri], byd[r.mon]; ex = sorted(e for e in gf.exp.unique() if e >= r.mon)
    if not ex: continue
    e = ex[0]; f = gf[gf.exp == e]; mo = gm[gm.exp == e]; s = r.fri_close
    def opt(typ, k):
        a = f[(f.typ == typ) & (f.k == k)]; b = mo[(mo.typ == typ) & (mo.k == k)]
        if a.empty or b.empty or a.c.iloc[0] <= 0 or b.o.iloc[0] <= 0: return None
        return float(a.c.iloc[0]), float(b.o.iloc[0])
    ks = np.array(sorted(f.k.unique())); near = lambda x: ks[np.abs(ks - x).argmin()]
    fut = d * (r.mon_916 - s) - 2.0
    res = dict(fri=fri, dir=d, gap_pct=r.gap_pct, fut=fut)
    for tag, off in (("hedge1", 0.01), ("hedge2", 0.02)):            # protective option against the futures position
        typ = "PE" if d == 1 else "CE"; k = near(s * (1 - d * off)); o = opt(typ, k)
        res[tag] = None if o is None else fut + (o[1] - o[0]) - cbuy(*o)
    typ = "CE" if d == 1 else "PE"; ka = near(s); o = opt(typ, ka)          # outright ATM option in the direction
    res["atm_opt"] = None if o is None else (o[1] - o[0]) - cbuy(*o)
    kb = near(s * (1 + d * 0.01)); o2 = opt(typ, kb)                          # debit spread ATM / 1% OTM
    res["spread"] = None if (o is None or o2 is None) else (o[1] - o[0]) - cbuy(*o) - (o2[1] - o2[0]) - csell(*o2)
    rows.append(res)
T = pd.DataFrame(rows).set_index("fri").dropna()
yrs = (T.index[-1] - T.index[0]).days / 365.25
NAMES = {"fut": "Futures, no hedge", "hedge1": "Futures + 1% OTM protective option", "hedge2": "Futures + 2% OTM protective option",
         "atm_opt": "Buy ATM call/put in Friday's direction", "spread": "Debit spread (ATM / 1% OTM) in Friday's direction"}
out = []
for c, nm in NAMES.items():
    rs = T[c] * LOT; eq = rs.cumsum(); M = rs.groupby(rs.index.to_period("M")).sum(); yr = rs.groupby(rs.index.year).sum()
    out.append(dict(version=nm, trades=len(rs), win=round((rs > 0).mean() * 100, 1), rs_per_yr=round(rs.sum() / yrs), worst_weekend=round(rs.min()),
                    best_weekend=round(rs.max()), max_dd=round((eq - eq.cummax()).min()), worst_month=round(M.min()), losing_months=f"{(M<0).sum()}/{len(M)}",
                    losing_yrs=int((yr < 0).sum()), avg_2016_20=round(rs[rs.index < "2021"].mean()), avg_2021_26=round(rs[rs.index >= "2021"].mean())))
O = pd.DataFrame(out); pd.set_option("display.width", 250); print(O.to_string(index=False)); O.to_csv("weekend_hedged_summary.csv", index=False)
T.to_csv("weekend_hedged_trades.csv")
for c in ("hedge1", "hedge2", "fut"):
    rs = T[c] * LOT; M = rs.groupby([rs.index.year, rs.index.month]).sum().unstack().fillna(0).round(0)
    M.columns = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][:len(M.columns)]; M["Total"] = M.sum(axis=1)
    print(f"\nMonthly Rs per lot - {NAMES[c]}\n", M.to_string()); M.to_csv(f"weekend_monthly_{c}.csv")
