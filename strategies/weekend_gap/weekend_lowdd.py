"""Lower-drawdown versions of the weekend trade (base = 5 lots, futures + 1% OTM protective option, Friday direction agrees with
50 EMA and 200 SMA, skip long weekends, Fri close -> Mon open). Real NSE bhavcopy option prices, futures proxied by index."""
import numpy as np, pandas as pd
T = pd.read_csv("weekend_improve_trades.csv", index_col=0, parse_dates=True)
T = T[T.trend50 & T.trend200 & ~T.long_weekend]
G = pd.read_csv("weekend_gaps.csv", index_col=0, parse_dates=True); G["mon"] = pd.to_datetime(G.mon)
D = pd.read_pickle("/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/idxopt.pkl"); D = D[D.sym == "NIFTY"]
byd = {k: g for k, g in D.groupby("date")}; LOT = 65; N = 5
def cb(pi, po): return po * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 1.0
def cs(pi, po): return pi * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 1.0
rows = []
for fri, t in T.iterrows():
    r = G.loc[fri]; d = int(t.dir); gf, gm = byd[fri], byd[r.mon]; e = sorted(x for x in gf.exp.unique() if x >= r.mon)[0]
    f = gf[gf.exp == e]; mo = gm[gm.exp == e]; s = r.fri_close; ks = np.array(sorted(f.k.unique())); near = lambda x: ks[np.abs(ks - x).argmin()]
    def opt(typ, k):
        a = f[(f.typ == typ) & (f.k == k)]; b = mo[(mo.typ == typ) & (mo.k == k)]
        if a.empty or b.empty or a.c.iloc[0] <= 0 or b.o.iloc[0] <= 0: return None
        return float(a.c.iloc[0]), float(b.o.iloc[0])
    fut = d * (r.mon_916 - s) - 2; hp = "PE" if d == 1 else "CE"; cp_ = "CE" if d == 1 else "PE"
    row = dict(fri=fri, dir=d, vix=t.vix, base=t.base)
    for tag, off in (("h05", 0.005), ("hatm", 0.0)):
        o = opt(hp, near(s * (1 - d * off))); row[tag] = None if o is None else fut + (o[1] - o[0]) - cb(*o)
    o1 = opt(hp, near(s * (1 - d * 0.01))); o2 = opt(cp_, near(s * (1 + d * 0.02)))
    row["collar"] = None if (o1 is None or o2 is None) else fut + (o1[1] - o1[0]) - cb(*o1) - (o2[1] - o2[0]) - cs(*o2)
    rows.append(row)
X = pd.DataFrame(rows).set_index("fri").dropna()
for c_ in ("base", "h05", "hatm", "collar"): X[c_] = X[c_] * LOT
yrs = (pd.Timestamp("2026-10-23") - pd.Timestamp("2016-01-01")).days / 365.25
def stats(name, s):
    s = s[s != 0]; eq = s.cumsum(); M = s.groupby(s.index.to_period("M")).sum(); yr = s.groupby(s.index.year).sum()
    dd = (eq - eq.cummax()).min()
    return dict(version=name, trades=len(s), win=round((s > 0).mean() * 100, 1), rs_yr=round(s.sum() / yrs), worst_weekend=round(s.min()), max_dd=round(dd),
                worst_month=round(M.min()), losing_yrs=int((yr < 0).sum()), ret_dd=round(s.sum() / yrs / -dd, 2),
                avg_16_20=round(s[s.index < "2021"].mean()), avg_21_26=round(s[s.index >= "2021"].mean()))
def dd_resize(s1, full=N, small=2, lim=30000):
    out = {}; eq = pk = 0.0
    for d_, v in s1.items():
        n = small if eq - pk <= -lim else full; x = v * n; out[d_] = x; eq += x; pk = max(pk, eq)
    return pd.Series(out)
def eq_filter(s1, n=N, win=8):
    out = {}; hist = []
    for d_, v in s1.items():
        on = len(hist) < win or sum(hist[-win:]) > 0
        out[d_] = v * n if on else 0.0; hist.append(v)                      # track the shadow (paper) result even when skipped
    return pd.Series(out)
vs = np.clip(16 / X.vix, 0.5, 1.0)                                         # VIX sizing: full size at VIX<=16, scaled down above
R = [stats("BASE 5 lots, 1% hedge", X.base * N), stats("0.5% OTM hedge", X.h05 * N), stats("ATM hedge (= synthetic option)", X.hatm * N),
     stats("Collar: 1% hedge + sell 2% OTM opposite", X.collar * N),
     stats("VIX sizing (5 lots at VIX<=16, fewer above)", (X.base * N * vs).round(0)),
     stats("Longs 5 lots / shorts 3 lots", X.base * np.where(X.dir == 1, 5, 3)),
     stats("Drawdown > 30k -> 2 lots till new high", dd_resize(X.base)),
     stats("Pause if last 8 weekends (paper) net negative", eq_filter(X.base)),
     stats("0.5% hedge + drawdown rule", dd_resize(X.h05)),
     stats("0.5% hedge + longs 5 / shorts 3", X.h05 * np.where(X.dir == 1, 5, 3)),
     stats("0.5% hedge + longs 5/shorts 3 + DD rule", dd_resize(X.h05 * np.where(X.dir == 1, 1, 0.6), full=N))]
O = pd.DataFrame(R); pd.set_option("display.width", 260); print(O.to_string(index=False)); O.to_csv("weekend_lowdd_summary.csv", index=False)
X.to_csv("weekend_lowdd_trades.csv")
