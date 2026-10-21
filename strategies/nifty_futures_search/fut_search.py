"""
Nifty futures strategy candidates, 2015-2026, from 1-minute index data.
Each strategy produces a daily return on 1x notional (after costs). Then leverage is applied.
Design/in-sample: 2015-2021. Out-of-sample: 2022-2026 (never used to choose parameters).
Costs: 0.035% of notional per round trip (brokerage + STT + exchange + slippage on Nifty futures).
Carry: long futures held overnight lose ~5.5%/yr vs index (premium decay); shorts gain it.
"""
import sys, numpy as np, pandas as pd
m = pd.read_csv(sys.argv[1], index_col=0, parse_dates=True)
m["day"] = m.index.normalize()
RT, CARRY = 0.00035, 0.055 / 252
D = m.groupby("day").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
D = D[D.index >= "2015-01-12"]

res = {}
# A. overnight long: buy at close, sell next open
on = D.open.shift(-1) / D.close - 1
res["A overnight long (close->next open)"] = (on - RT - CARRY).shift(1).fillna(0)

# B. opening range breakout, first N minutes; stop = other side; exit at close
def orb(N, tgt_mult=None, only_dir=0):
    out = {}
    for day, g in m.groupby("day"):
        g = g.iloc[:375]
        if len(g) < N + 30: out[day] = 0.0; continue
        hi, lo = g.high.iloc[:N].max(), g.low.iloc[:N].min()
        rest = g.iloc[N:]
        up = np.where(rest.high.values > hi)[0]; dn = np.where(rest.low.values < lo)[0]
        fu, fd = (up[0] if len(up) else 10**9), (dn[0] if len(dn) else 10**9)
        if fu == fd == 10**9: out[day] = 0.0; continue
        d = 1 if fu < fd else -1
        if only_dir and d != only_dir: out[day] = 0.0; continue
        k = min(fu, fd); entry = max(rest.open.values[k], hi) if d == 1 else min(rest.open.values[k], lo)
        stop = lo if d == 1 else hi; risk = abs(entry - stop)
        tgt = entry + d * tgt_mult * risk if tgt_mult else None
        ex = rest.close.values[-1]
        H, L, O = rest.high.values, rest.low.values, rest.open.values
        for j in range(k, len(rest)):
            if (d == 1 and L[j] <= stop) or (d == -1 and H[j] >= stop):
                ex = stop if j == k else (min(O[j], stop) if d == 1 else max(O[j], stop)); break
            if tgt and ((d == 1 and H[j] >= tgt) or (d == -1 and L[j] <= tgt)):
                ex = tgt if j == k else (max(O[j], tgt) if d == 1 else min(O[j], tgt)); break
        out[day] = d * (ex / entry - 1) - RT
    return pd.Series(out).reindex(D.index).fillna(0)

for N in (15, 30, 60):
    res[f"B ORB {N}m, stop other side, exit close"] = orb(N)
res["B ORB 30m, 1:2 target"] = orb(30, 2)
res["B ORB 30m, long only"] = orb(30, None, 1)

# C. daily trend: hold sign(close vs EMA) overnight, switch at close
cc = D.close
for n in (10, 20, 50, 100):
    pos = np.sign(cc - cc.ewm(span=n, adjust=False).mean())
    r = pos.shift(1) * cc.pct_change() - pos.diff().abs().fillna(0) * RT / 2 - pos.shift(1).clip(lower=0) * CARRY + (-pos.shift(1)).clip(lower=0) * CARRY
    res[f"C trend EMA{n} long/short"] = r.fillna(0)
    posl = (cc > cc.ewm(span=n, adjust=False).mean()).astype(float)
    rl = posl.shift(1) * cc.pct_change() - posl.diff().abs().fillna(0) * RT / 2 - posl.shift(1) * CARRY
    res[f"C trend EMA{n} long only"] = rl.fillna(0)
res["Nifty buy & hold (futures, incl carry)"] = (cc.pct_change() - CARRY).fillna(0)

R = pd.DataFrame(res)
R.to_csv("fut_daily_returns.csv")
def st(r):
    e = (1 + r).cumprod(); y = (r.index[-1] - r.index[0]).days / 365.25
    return (e.iloc[-1] ** (1 / y) - 1), (e / e.cummax() - 1).min(), r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0
print(f"{'strategy (1x, after costs)':42s} | {'IN 2015-21: CAGR':>16s} {'DD':>6s} {'Sh':>5s} | {'OUT 2022-26: CAGR':>17s} {'DD':>6s} {'Sh':>5s}")
for k in R:
    a = st(R[k][:"2021"]); b = st(R[k]["2022":])
    print(f"{k:42s} | {a[0]*100:15.1f}% {a[1]*100:5.0f}% {a[2]:5.2f} | {b[0]*100:16.1f}% {b[1]*100:5.0f}% {b[2]:5.2f}")
