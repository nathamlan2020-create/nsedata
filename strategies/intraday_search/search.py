import numpy as np, pandas as pd, itertools
F = pd.read_pickle("days.pkl").reset_index(drop=True).sort_values(["sym", "day"]).reset_index(drop=True)
F["gap"] = F.open / F.pc - 1
F = F[F.gap.abs() < 0.15]                      # drop split/bonus artefacts (Kite prices unadjusted)
F["vol20"] = F.groupby("sym").v15.transform(lambda s: s.rolling(20).mean().shift(1))
F["orv"] = F.v15 / F.vol20
F["atr"] = ((F.high - F.low) / F.close).groupby(F.sym).transform(lambda s: s.rolling(14).mean().shift(1))
NEW = {"KOTAKBANK","MM","HINDUNILVR","BAJFINANCE","SUNPHARMA","MARUTI","HCLTECH","NTPC","ULTRACEMCO","TITAN"}
S = F[F.sym != "NIFTY"].copy(); N = F[F.sym == "NIFTY"].copy()
COST = {"stk": 0.0010, "idx": 0.0003}

def rule_rows(D, name, dirn, ent, ex, cost):
    m = (dirn != 0) & ent.notna() & ex.notna()
    r = dirn[m] * (ex[m] / ent[m] - 1) - cost
    return pd.DataFrame({"rule": name, "day": D.day[m], "sym": D.sym[m], "ret": r})

def families(D, cost):
    out = []
    sg = np.sign
    for g in (0.005, 0.01, 0.02):
        big = D.gap.abs() > g
        out.append(rule_rows(D, f"gap fade >{g:.1%} 9:20-15:15", np.where(big, -sg(D.gap), 0), D.p920, D.p1515, cost))
        out.append(rule_rows(D, f"gap go >{g:.1%} 9:20-15:15", np.where(big, sg(D.gap), 0), D.p920, D.p1515, cost))
    r30 = D.p945 / D.open - 1
    for x in (0.0, 0.005, 0.01):
        big = r30.abs() > x
        out.append(rule_rows(D, f"1st30m mom >{x:.1%} 9:45-15:15", np.where(big, sg(r30), 0), D.p945, D.p1515, cost))
        out.append(rule_rows(D, f"1st30m rev >{x:.1%} 9:45-15:15", np.where(big, -sg(r30), 0), D.p945, D.p1515, cost))
    rd = D.p1445 / D.pc - 1
    for x in (0.0, 0.005, 0.01):
        big = rd.abs() > x
        out.append(rule_rows(D, f"day mom >{x:.1%} 14:45-close", np.where(big, sg(rd), 0), D.p1445, D.close, cost))
        out.append(rule_rows(D, f"day rev >{x:.1%} 14:45-close", np.where(big, -sg(rd), 0), D.p1445, D.close, cost))
    r1 = D.p945 / D.pc - 1
    out.append(rule_rows(D, "1st30m(vs pc) mom 14:45-close", sg(r1), D.p1445, D.close, cost))
    if D.vol.sum() > 0:
        up = (D.p1015 > D.vwap1015) & (D.p1015 > D.open); dn = (D.p1015 < D.vwap1015) & (D.p1015 < D.open)
        out.append(rule_rows(D, "VWAP trend 10:15-15:15", np.where(up, 1, np.where(dn, -1, 0)), D.p1015, D.p1515, cost))
        out.append(rule_rows(D, "VWAP fade 10:15-15:15", np.where(up, -1, np.where(dn, 1, 0)), D.p1015, D.p1515, cost))
        hv = D.orv > 2
        out.append(rule_rows(D, "VWAP trend +orv>2 10:15-15:15", np.where(up & hv, 1, np.where(dn & hv, -1, 0)), D.p1015, D.p1515, cost))
        out.append(rule_rows(D, "gap go >1% +orv>2", np.where((D.gap.abs() > .01) & hv, sg(D.gap), 0), D.p920, D.p1515, cost))
        out.append(rule_rows(D, "1st30m mom +orv>2", np.where(hv, sg(r30), 0), D.p945, D.p1515, cost))
    ab = D.open > D.ph; bl = D.open < D.pl
    out.append(rule_rows(D, "open beyond prev H/L go", np.where(ab, 1, np.where(bl, -1, 0)), D.p920, D.p1515, cost))
    out.append(rule_rows(D, "open beyond prev H/L fade", np.where(ab, -1, np.where(bl, 1, 0)), D.p920, D.p1515, cost))
    rm = D.p1200 / D.open - 1
    for x in (0.005, 0.01, 0.02):
        big = rm.abs() > x
        out.append(rule_rows(D, f"morning rev >{x:.1%} 12:00-15:15", np.where(big, -sg(rm), 0), D.p1200, D.p1515, cost))
        out.append(rule_rows(D, f"morning mom >{x:.1%} 12:00-15:15", np.where(big, sg(rm), 0), D.p1200, D.p1515, cost))
    # big ATR-scaled first-30-min move
    z = r30 / D.atr
    for zz in (0.3, 0.5):
        out.append(rule_rows(D, f"1st30m/ATR>{zz} mom", np.where(z.abs() > zz, sg(z), 0), D.p945, D.p1515, cost))
        out.append(rule_rows(D, f"1st30m/ATR>{zz} rev", np.where(z.abs() > zz, -sg(z), 0), D.p945, D.p1515, cost))
    return out

def xsec(D, cost, k=3):
    """cross-sectional: rank 22 stocks by 9:15->9:45 move vs prev close; long/short k each, exit 15:15"""
    out = []
    D = D.assign(r1=D.p945 / D.pc - 1, rx=D.p1515 / D.p945 - 1).dropna(subset=["r1", "rx"])
    rk = D.groupby("day").r1.rank(); n = D.groupby("day").r1.transform("count")
    for nm, lo, hi in (("XS reversal", 1, -1), ("XS momentum", -1, 1)):
        d = np.where(rk <= k, lo, np.where(rk > n - k, hi, 0))
        m = d != 0
        out.append(pd.DataFrame({"rule": f"{nm} top/bot {k} 9:45-15:15", "day": D.day[m], "sym": D.sym[m],
                                 "ret": d[m] * D.rx[m] - cost}))
    return out

R = pd.concat(families(S, COST["stk"]) + xsec(S, COST["stk"]) + xsec(S, COST["stk"], 1))
R["univ"] = "22stk"
RN = pd.concat(families(N, COST["idx"])); RN["univ"] = "NIFTY fut"
R = pd.concat([R, RN]); R["day"] = pd.to_datetime(R.day)
R.to_pickle("rule_trades.pkl")

def summ(g):
    r = g.ret; IS = g[g.day < "2021"].ret; OOS = g[g.day >= "2021"].ret
    dly = g.groupby("day").ret.mean()
    idx = pd.bdate_range(g.day.min(), g.day.max()); dly = dly.reindex(idx).fillna(0)
    def cg(x):
        if len(x) == 0: return np.nan
        e = (1 + x).cumprod(); return e.iloc[-1] ** (252 / len(x)) - 1
    dIS, dOOS = dly[dly.index < "2021"], dly[dly.index >= "2021"]
    e = (1 + dly).cumprod()
    return pd.Series({"n": len(r), "win": (r > 0).mean(), "avg": r.mean() * 100,
                      "IS_avg": IS.mean() * 100, "OOS_avg": OOS.mean() * 100,
                      "old12": g[~g.sym.isin(NEW | {"NIFTY"})].ret.mean() * 100, "new10": g[g.sym.isin(NEW)].ret.mean() * 100,
                      "CAGR_IS": cg(dIS) * 100, "CAGR_OOS": cg(dOOS) * 100, "maxDD": (e / e.cummax() - 1).min() * 100})

T = R.groupby(["univ", "rule"]).apply(summ).reset_index()
T = T[T.n >= 150]
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
fmt = lambda d: d.round({"win": 2, "avg": 3, "IS_avg": 3, "OOS_avg": 3, "old12": 3, "new10": 3, "CAGR_IS": 1, "CAGR_OOS": 1, "maxDD": 0})
for u in ("22stk", "NIFTY fut"):
    t = T[T.univ == u].sort_values("IS_avg", ascending=False)
    print(f"\n===== {u}: ranked by 2015-20 (in-sample) avg/trade; OOS = 2021-26 =====")
    print(fmt(t.drop(columns="univ")).head(14).to_string(index=False))
T.to_csv("search_summary.csv", index=False)
