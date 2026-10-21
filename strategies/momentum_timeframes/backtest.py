"""Momentum-continuation backtest across timeframes, Nifty 50 index + 33 Nifty 50 stocks, 1-min Kite data 2015-26.
Rule family: measure the move so far in a window; if |move| > x, trade in its direction; exit at the end of the hold.
  A  fixed check time T (9:30..14:00): move = price(T)/day open - 1, enter at T, exit 15:15
  B  bar timeframe 5m/15m/60m: enter on close of the FIRST bar whose close is > x away from day open (till 15:00), exit 15:15
  C  daily: yesterday's close-to-close move > x -> trade prev close->today close (enter at signal close)
  D  daily trend: 20-day return sign -> trade prev close->today close (enter at signal close) (always in)
  E  weekly: last week's return > x -> trade next week enter at last Fri close -> exit this Fri close
Costs per round trip: Nifty futures 0.03%, stocks 0.10%. In-sample 2015-20, out-of-sample 2021-26.
C/D/E hold close->close and pay costs only when the position changes (so "trades" = position-days/weeks).
Portfolio: all capital split equally across that day's/week's trades (Nifty = 1 position).
"""
import numpy as np, pandas as pd
F = pd.read_pickle("days.pkl").sort_values(["sym", "day"]).reset_index(drop=True)
F["gap"] = F.open / F.pc - 1
COST = {"idx": 0.0003, "stk": 0.0010}
TH = {"idx": [0.0025, 0.005, 0.0075, 0.01], "stk": [0.005, 0.01, 0.015, 0.02]}
CHK = [930, 945, 1015, 1100, 1200, 1300, 1400]
rows = []

def add(D, fam, tf, x, dirn, ent, ex, kind, day=None, long_only=False):
    dirn = pd.Series(dirn, index=D.index)
    if long_only: dirn = dirn.clip(lower=0)
    m = (dirn != 0) & ent.notna() & ex.notna()
    r = dirn[m] * (ex[m] / ent[m] - 1) - COST[kind]
    r = r[r.abs() < 0.15]                                   # split / bad-tick guard (prices unadjusted)
    rows.append(pd.DataFrame({"fam": fam, "tf": tf, "x": x, "univ": "NIFTY" if kind == "idx" else "33 stocks",
                              "side": "long only" if long_only else "long+short",
                              "day": (D.day if day is None else day)[r.index], "ret": r}))

def addh(D, fam, tf, x, pos, kind, long_only=False):
    """position held close->close; cost charged only on position changes (half round-trip per unit change)"""
    pos = pd.Series(pos, index=D.index).fillna(0)
    if long_only: pos = pos.clip(lower=0)
    rc = (D.close / D.pcx - 1)
    prev = pos.groupby(D.sym).shift(1).fillna(0)
    r = pos * rc - COST[kind] / 2 * (pos - prev).abs()
    m = ((pos != 0) | (prev != 0)) & rc.notna() & (rc.abs() < 0.15)
    rows.append(pd.DataFrame({"fam": fam, "tf": tf, "x": x, "univ": "NIFTY" if kind == "idx" else "33 stocks",
                              "side": "long only" if long_only else "long+short", "day": D.day[m], "ret": r[m]}))

for kind, D in F.groupby("kind"):
    D = D[(D.gap.abs() < 0.15) | D.gap.isna()]
    for T in CHK:
        rT = D[f"p{T}"] / D.open - 1
        for x in TH[kind]:
            add(D, "A fixed time", f"{T//100}:{T%100:02d}", x, np.where(rT.abs() > x, np.sign(rT), 0), D[f"p{T}"], D.p1515, kind)
    for tf in (5, 15, 60):
        for x in TH[kind]:
            add(D, "B first bar beyond x", f"{tf}m bars", x, D[f"b{tf}_{x}_dir"].fillna(0), D[f"b{tf}_{x}_px"], D.p1515, kind)
    g = D.groupby("sym")
    r1 = g.close.pct_change().groupby(D.sym).shift(1)          # yesterday's close/close
    for x in ([0.005, 0.01] if kind == "idx" else [0.01, 0.02]):
        for lo in (False, True):
            addh(D.assign(pcx=D.pc), "C daily (yday move)", "1D", x, np.where(r1.abs() > x, np.sign(r1), 0), kind, long_only=lo)
    addh(D.assign(pcx=D.pc), "D0 buy & hold", "1D", 0, np.ones(len(D)), kind)
    r20 = (D.close / g.close.shift(20) - 1).groupby(D.sym).shift(1)
    for lo in (False, True):
        addh(D.assign(pcx=D.pc), "D daily trend (20D)", "1D", 0, np.sign(r20).fillna(0), kind, long_only=lo)
    # weekly bars
    W = D.assign(wk=D.day.dt.to_period("W-FRI")).groupby(["sym", "wk"]).agg(
        day=("day", "first"), open=("open", "first"), close=("close", "last")).reset_index()
    W["pcw"] = W.groupby("sym").close.shift(1)
    rw = W.groupby("sym").close.pct_change()
    rw = rw.where(rw.abs() < 0.3).groupby(W.sym).shift(1)
    for x in (0.0, 0.01, 0.02):
        for lo in (False, True):
            addh(W.assign(pcx=W.pcw), "E weekly (last week)", "1W", x, np.where(rw.abs() > x, np.sign(rw), 0).astype(float), kind, long_only=lo)

R = pd.concat(rows); R["day"] = pd.to_datetime(R.day)
R.to_pickle("trades.pkl")

def cagr(per):
    if len(per) < 2: return np.nan
    e = (1 + per).cumprod(); yrs = (per.index[-1] - per.index[0]).days / 365.25
    return (e.iloc[-1] ** (1 / yrs) - 1) * 100 if e.iloc[-1] > 0 else -100

def summ(g):
    per = g.groupby("day").ret.mean()
    IS, OOS = per[per.index < "2021"], per[per.index >= "2021"]
    e = (1 + per).cumprod()
    yrs_oos = g[g.day >= "2021"].day.dt.year.nunique()
    yoos = OOS.groupby(OOS.index.year).apply(lambda s: (1 + s).prod() - 1)
    return pd.Series({"trades/days": len(g), "win%": (g.ret > 0).mean() * 100,
                      "IS_avg%": g[g.day < "2021"].ret.mean() * 100, "OOS_avg%": g[g.day >= "2021"].ret.mean() * 100,
                      "CAGR_IS%": cagr(IS), "CAGR_OOS%": cagr(OOS), "maxDD%": (e / e.cummax() - 1).min() * 100,
                      "OOS_losing_yrs": f"{(yoos < 0).sum()}/{len(yoos)}"})

T = R.groupby(["univ", "fam", "tf", "x", "side"]).apply(summ).reset_index()
T["x"] = (T.x * 100).round(2).astype(str) + "%"
T.to_csv("momentum_tf_summary.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
r = lambda d: d.round({"win%": 0, "IS_avg%": 3, "OOS_avg%": 3, "CAGR_IS%": 1, "CAGR_OOS%": 1, "maxDD%": 0})
for u in ("NIFTY", "33 stocks"):
    print(f"\n=========== {u} ===========")
    print(r(T[T.univ == u].drop(columns="univ")).to_string(index=False))
