"""Nifty midday-momentum rule tested across timeframes.

Base rule (from strategies/intraday_search): at check time T, if price has moved more than X% from the day's
open, trade in that direction; exit at 15:15.

Timeframes tested
  Intraday : check at 09:30 ... 14:30, threshold 0.25-1.5%, exit 15:15   (Nifty fut cost 0.03%, stocks 0.10%)
  Swing    : day / 2-day / week / month momentum - if last period's return > X, hold the next period
             in that direction (close-to-close; Nifty cost 0.03%, stocks 0.20%)
Universe   : Nifty 50 index (proxy for futures) and the 33 stocks in intraday/stocks_1min/kite_2015-2026
Split      : in-sample 2015-2020, out-of-sample 2021-2026
"""
import glob, os, numpy as np, pandas as pd
from multiprocessing import Pool

ROOT = os.path.dirname(os.path.abspath(__file__)) + "/../.."
CHECK = [930, 945, 1000, 1030, 1100, 1130, 1200, 1230, 1300, 1330, 1400, 1430]
THR = [0.0025, 0.005, 0.0075, 0.01, 0.015]

def snap(f):
    sym = "NIFTY" if "nifty50" in f else os.path.basename(f).split(".")[0]
    d = pd.read_csv(f, index_col=0, parse_dates=True, usecols=[0, 1, 2, 3, 4])
    t = d.index.hour * 100 + d.index.minute
    d = d[(t >= 915) & (t <= 1529)]
    t = d.index.hour * 100 + d.index.minute
    day = d.index.normalize()
    g = d.groupby(day)
    out = pd.DataFrame({"open": g.open.first(), "close": g.close.last(), "n": g.size()})
    for c in CHECK + [1515]:
        m = t < c
        out[f"p{c}"] = d.close[m].groupby(day[m]).last()
    out = out[out.n > 300].drop(columns="n")
    out["sym"] = sym
    return out.rename_axis("day").reset_index()

def cagr(r, per_year):
    if len(r) == 0: return np.nan
    return ((1 + r).prod()) ** (per_year / len(r)) - 1

def stats(tr, daily, label, ppy=252):
    """tr: per-trade returns (with day); daily: per-period portfolio return series"""
    IS, OOS = tr[tr.day < "2021"].ret, tr[tr.day >= "2021"].ret
    e = (1 + daily).cumprod()
    return dict(test=label, trades=len(tr), win=round((tr.ret > 0).mean() * 100),
                avg=round(tr.ret.mean() * 100, 3), IS_avg=round(IS.mean() * 100, 3), OOS_avg=round(OOS.mean() * 100, 3),
                CAGR_IS=round(cagr(daily[daily.index < "2021"], ppy) * 100, 1),
                CAGR_OOS=round(cagr(daily[daily.index >= "2021"], ppy) * 100, 1),
                maxDD=round((e / e.cummax() - 1).min() * 100))

if __name__ == "__main__":
    fs = sorted(glob.glob(f"{ROOT}/intraday/stocks_1min/kite_2015-2026/*.csv.gz")) + \
         [f"{ROOT}/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz"]
    with Pool(2) as p: F = pd.concat(p.map(snap, fs))
    F["day"] = pd.to_datetime(F.day)
    rows = []
    # ---------- intraday ----------
    for univ, cost in (("NIFTY", 0.0003), ("33 stocks", 0.0010)):
        D = F[F.sym == "NIFTY"] if univ == "NIFTY" else F[F.sym != "NIFTY"]
        bdays = pd.DatetimeIndex(sorted(D.day.unique()))
        for c in CHECK:
            mv = D[f"p{c}"] / D.open - 1
            for x in THR:
                s = np.sign(mv) * (mv.abs() > x)
                m = (s != 0) & D.p1515.notna()
                tr = pd.DataFrame({"day": D.day[m], "ret": s[m] * (D.p1515[m] / D[f"p{c}"][m] - 1) - cost})
                if len(tr) < 50: continue
                daily = tr.groupby("day").ret.mean().reindex(bdays).fillna(0)
                r = stats(tr, daily, f"{c//100}:{c%100:02d} >{x:.2%}")
                r.update(univ=univ, tf="intraday", check=c, thr=x); rows.append(r)
    # ---------- swing: day / 2-day / week / month ----------
    for univ, cost in (("NIFTY", 0.0003), ("33 stocks", 0.0020)):
        D = F[F.sym == "NIFTY"] if univ == "NIFTY" else F[F.sym != "NIFTY"]
        px = D.pivot(index="day", columns="sym", values="close")
        for tf, rule, ppy in (("1 day", None, 252), ("2 day", 2, 126), ("week", "W-FRI", 52), ("month", "ME", 12)):
            if rule is None: P = px
            elif isinstance(rule, int): P = px.iloc[::rule]
            else: P = px.resample(rule).last()
            ret = P.pct_change(fill_method=None)
            # drop split/bonus artefacts (Kite prices are unadjusted)
            ret = ret.mask(ret.abs() > (0.15 if tf in ("1 day", "2 day") else 0.30))
            nxt = ret.shift(-1)
            for x in [0.0] + THR:
                s = np.sign(ret) * (ret.abs() > x)
                tr = (s * nxt - cost * (s != 0)).where((s != 0) & nxt.notna())
                tl = tr.stack().dropna().rename("ret").reset_index()
                tl = tl.rename(columns={tl.columns[0]: "day"})
                if len(tl) < 30: continue
                per = tr.mean(axis=1).fillna(0)
                r = stats(tl, per, f"{tf} mom >{x:.2%}", ppy)
                r.update(univ=univ, tf=tf, check=None, thr=x); rows.append(r)
    R = pd.DataFrame(rows)
    R.to_csv(os.path.dirname(os.path.abspath(__file__)) + "/momentum_tf_summary.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
    cols = ["test", "trades", "win", "avg", "IS_avg", "OOS_avg", "CAGR_IS", "CAGR_OOS", "maxDD"]
    for u in ("NIFTY", "33 stocks"):
        X = R[(R.univ == u) & (R.tf == "intraday")]
        print(f"\n=== {u} intraday: best threshold per check time (by in-sample avg) ===")
        print(X.sort_values("IS_avg", ascending=False).groupby("check").head(1).sort_values("check")[cols].to_string(index=False))
        print(f"\n=== {u} intraday: 0.50% threshold at every check time ===")
        print(X[X.thr == 0.005].sort_values("check")[cols].to_string(index=False))
        print(f"\n=== {u} swing timeframes ===")
        print(R[(R.univ == u) & (R.tf != "intraday")][cols].to_string(index=False))
