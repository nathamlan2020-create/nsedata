"""
5 EMA reversal (Kiran Bala style) on Nifty 50, 2015-2026, signals on 30/60-min candles,
trade path replayed on 1-minute data (no same-candle ambiguity).
Short: alert candle fully above 5 EMA (low > EMA); later candle (same day) breaks alert low -> short at alert low
       (or the minute's open if it gaps through); stop = alert high.  Long: mirror.
Exits: 1:2 or 1:3 target, or trail = candle closes back across 5 EMA; always squared off at day's last minute.
No entries in the day's last candle. After an exit, alerts reset.
Usage: python ema5_long.py <nifty50_1min.csv.gz>
"""
import sys
import numpy as np
import pandas as pd

m = pd.read_csv(sys.argv[1], index_col=0, parse_dates=True)
m = m[(m.index.time >= pd.Timestamp("09:15").time()) & (m.index.time <= pd.Timestamp("15:29").time())]
m["day"] = m.index.normalize()
mins_of_day = (m.index.hour * 60 + m.index.minute - 555).values

def run(tf, exit_mode, cost):
    m["bucket"] = mins_of_day // tf
    g = m.groupby(["day", "bucket"])
    C = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
              i0=("open", lambda s: 0)).reset_index()
    # minute index ranges for each candle
    idx = np.arange(len(m)); m["_i"] = idx
    rng = m.groupby(["day", "bucket"])["_i"].agg(["min", "max"]).reset_index()
    C["a"], C["b"] = rng["min"].values, rng["max"].values
    C["ema"] = C.close.ewm(span=5, adjust=False).mean()
    C["last"] = C.day != C.day.shift(-1)
    mo, mh, ml, mc = (m[k].values for k in ("open", "high", "low", "close"))
    co, ch, cl, cc, ce = (C[k].values for k in ("open", "high", "low", "close", "ema"))
    cday, clast, ca, cb = C.day.values, C["last"].values, C.a.values, C.b.values
    R_mult = 3 if exit_mode == "t3" else 2
    trades = []
    alert_s = alert_l = None
    i = 1
    n = len(C)
    while i < n:
        if alert_s is not None and cday[alert_s] != cday[i]: alert_s = None
        if alert_l is not None and cday[alert_l] != cday[i]: alert_l = None
        entered = False
        if not clast[i] and (alert_s is not None or alert_l is not None):
            for k in range(ca[i], cb[i] + 1):
                d = 0
                if alert_s is not None and ml[k] < cl[alert_s]:
                    d, entry, stop = -1, min(mo[k], cl[alert_s]), ch[alert_s]
                elif alert_l is not None and mh[k] > ch[alert_l]:
                    d, entry, stop = 1, max(mo[k], ch[alert_l]), cl[alert_l]
                if d == 0 or (stop - entry) * d >= 0:
                    continue
                risk = abs(entry - stop); tgt = entry + d * R_mult * risk
                # replay minute by minute from the entry minute
                j, ci = k, i
                exit_px = why = None
                while exit_px is None:
                    hi, lo, op = mh[j], ml[j], mo[j]
                    if (d == -1 and hi >= stop) or (d == 1 and lo <= stop):
                        exit_px, why = (stop if j == k else (max(op, stop) if d == -1 else min(op, stop))), "stop"
                    elif exit_mode != "trail" and ((d == -1 and lo <= tgt) or (d == 1 and hi >= tgt)):
                        exit_px, why = (tgt if j == k else (min(op, tgt) if d == -1 else max(op, tgt))), "target"
                    elif j == cb[ci]:                     # end of a candle
                        if exit_mode == "trail" and ci > i and ((d == -1 and cc[ci] > ce[ci]) or (d == 1 and cc[ci] < ce[ci])):
                            exit_px, why = cc[ci], "trail"
                        elif clast[ci]:
                            exit_px, why = mc[j], "eod"
                        else:
                            ci += 1
                    j += 1
                R = d * (exit_px - entry) / risk - 2 * cost * entry / risk
                trades.append((cday[i], d, entry, exit_px, risk / entry, R, why))
                alert_s = alert_l = None
                i = ci + 1 if why != "stop" or ci > i else i + 1
                # the exit candle itself may become a new alert
                last_c = i - 1
                if cday[last_c] == cday[min(i, n - 1)]:
                    if cl[last_c] > ce[last_c]: alert_s = last_c
                    if ch[last_c] < ce[last_c]: alert_l = last_c
                entered = True
                break
        if entered:
            continue
        if cl[i] > ce[i]: alert_s = i
        if ch[i] < ce[i]: alert_l = i
        i += 1
    return pd.DataFrame(trades, columns=["day", "dir", "entry", "exit", "risk_pct", "R", "why"])

def summ(t, risk=0.01):
    t = t.sort_values("day")
    eq = (1 + risk * t.R.clip(lower=-3)).cumprod()
    yrs = (t.day.max() - t.day.min()).days / 365.25
    by_year = t.groupby(t.day.dt.year).R.sum().round(0).astype(int).to_dict()
    return dict(trades=len(t), per_day=len(t) / t.day.nunique() if len(t) else 0, win=(t.R > 0).mean(), avgR=t.R.mean(),
                cagr=eq.iloc[-1] ** (1 / yrs) - 1, max_dd=(eq / eq.cummax() - 1).min(), stop_pct=t.risk_pct.median() * 100,
                long_R=t.R[t.dir == 1].mean(), short_R=t.R[t.dir == -1].mean(), by_year=by_year)

if __name__ == "__main__":
    for tf in (60, 30):
        for mode, lab in (("t3", "1:3 target"), ("t2", "1:2 target"), ("trail", "trail 5 EMA")):
            for cost in (0.00015, 0.0):
                t = run(tf, mode, cost); s = summ(t)
                print(f"{tf}m {lab:12s} cost {cost*100:.3f}%/side | trades {s['trades']:5d} win {s['win']*100:3.0f}% avgR {s['avgR']:+.3f} "
                      f"CAGR {s['cagr']*100:6.1f}% DD {s['max_dd']*100:6.1f}% stop {s['stop_pct']:.2f}% long {s['long_R']:+.2f} short {s['short_R']:+.2f}", flush=True)
                if cost > 0 and mode == "t3":
                    print("    R by year:", s["by_year"], flush=True)
                    t.to_csv(f"ema5_long_trades_{tf}m_t3.csv", index=False)
