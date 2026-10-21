"""
Synthetic backtest: intraday ATM Nifty straddle selling with a per-leg stop (Sourav Mazumder style).
- Sell ATM CE + PE at the 9:15 open (strike = open rounded to 50).
- Option prices: Black-Scholes, IV = previous day's India VIX close, r = 6.5%,
  time to the next weekly expiry (Thursday until Aug 2025, Tuesday from Sep 2025), decaying through the day.
- Each hourly candle: CE is checked at the candle's HIGH and PE at its LOW (worst case for a seller).
  A leg whose price reaches entry x (1 + SL) is bought back at that stop price.
- Remaining legs closed at the last candle's close. Costs: 1 point slippage per leg round trip + 0.15% of premium.
- Capital per lot (pledged collateral margin): Rs 2.5 lakh; lot 75.
Limits: IV held constant intraday (real IV jumps when Nifty falls fast), no VWAP filter (needs option volume).
Usage: python atm_sell.py <nifty_60m.csv> <indiavix.csv>
"""
import sys
import numpy as np
import pandas as pd
from math import log, sqrt, exp, erf

N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
def bs(S, K, T, s, r=0.065, call=True):
    T = max(T, 1e-5); d1 = (log(S / K) + (r + s * s / 2) * T) / (s * sqrt(T)); d2 = d1 - s * sqrt(T)
    return S * N(d1) - K * exp(-r * T) * N(d2) if call else K * exp(-r * T) * N(-d2) - S * N(-d1)

bars = pd.read_csv(sys.argv[1], index_col=0, parse_dates=True)
vix = pd.read_csv(sys.argv[2], index_col=0, parse_dates=True)["close"]
LOT, CAP = 75, 250000

def expiry_after(d):
    wd = 3 if d < pd.Timestamp("2025-09-01") else 1        # Thu, then Tue
    x = d.normalize()
    while x.weekday() != wd:
        x += pd.Timedelta(days=1)
    return x + pd.Timedelta(hours=15, minutes=30)

def run(sl=0.20, slip=1.0, pct_cost=0.0015):
    out = []
    for day, g in bars.groupby(bars.index.date):
        g = g.sort_index()
        if len(g) < 5:
            continue
        prev = vix[vix.index < pd.Timestamp(day)]
        if len(prev) == 0:
            continue
        iv = prev.iloc[-1] / 100
        t0 = g.index[0]
        exp_ = expiry_after(t0)
        S0 = g.open.iloc[0]; K = round(S0 / 50) * 50
        def T(ts, exp_=exp_):
            # remaining TRADING time to expiry, in years (6.25 h sessions, 252 days/yr)
            ts = min(ts, exp_)
            close_today = ts.normalize() + pd.Timedelta(hours=15, minutes=30)
            hrs = max((close_today - ts).total_seconds() / 3600, 0)
            if ts.normalize() < exp_.normalize():
                hrs += 6.25 * np.busday_count(ts.date() + pd.Timedelta(days=1), exp_.date() + pd.Timedelta(days=1))
            return hrs / (6.25 * 252)
        ce0, pe0 = bs(S0, K, T(t0), iv, call=True), bs(S0, K, T(t0), iv, call=False)
        legs = {"ce": [ce0, None], "pe": [pe0, None]}
        for ts, b in g.iterrows():
            tend = ts + pd.Timedelta(minutes=60)
            if legs["ce"][1] is None:
                worst = bs(b.high, K, T(tend - pd.Timedelta(minutes=30)), iv, call=True)
                if worst >= ce0 * (1 + sl):
                    legs["ce"][1] = ce0 * (1 + sl)
            if legs["pe"][1] is None:
                worst = bs(b.low, K, T(tend - pd.Timedelta(minutes=30)), iv, call=False)
                if worst >= pe0 * (1 + sl):
                    legs["pe"][1] = pe0 * (1 + sl)
        last = g.iloc[-1]; tl = g.index[-1] + pd.Timedelta(minutes=15)
        if legs["ce"][1] is None: legs["ce"][1] = bs(last.close, K, T(tl), iv, call=True)
        if legs["pe"][1] is None: legs["pe"][1] = bs(last.close, K, T(tl), iv, call=False)
        pts = sum(a - b for a, b in legs.values()) - 2 * slip - pct_cost * (ce0 + pe0)
        out.append(dict(day=pd.Timestamp(day), premium=ce0 + pe0, pts=pts, rs=pts * LOT,
                        stops=sum(b == a * (1 + sl) for a, b in legs.values()), dte=(exp_ - t0).days))
    return pd.DataFrame(out).set_index("day")

def stats(t, lab):
    eq = CAP + t.rs.cumsum()                                  # fixed 1 lot on Rs 2.5L (no compounding)
    yrs = (t.index[-1] - t.index[0]).days / 365.25
    dd = (eq - eq.cummax()).min()
    yearly = t.rs.groupby(t.index.year).sum() / CAP * 100
    print(f"{lab:34s} return/yr {t.rs.sum() / CAP / yrs * 100:6.1f}%  worst drawdown Rs {dd/1e5:5.2f}L ({dd/CAP*100:5.1f}% of capital)  "
          f"win days {(t.pts > 0).mean() * 100:3.0f}%  avg win {t.rs[t.rs > 0].mean():6.0f}  avg loss {t.rs[t.rs <= 0].mean():6.0f}  "
          f"worst day {t.rs.min():7.0f}  both legs stopped {(t.stops == 2).mean() * 100:3.0f}%  | by year % {yearly.round(1).to_dict()}")

if __name__ == "__main__":
    print("days:", bars.index.normalize().nunique(), bars.index[0].date(), "to", bars.index[-1].date())
    for sl, lab in ((0.20, "ATM straddle, 20% SL per leg"), (0.30, "ATM straddle, 30% SL per leg"),
                    (0.50, "ATM straddle, 50% SL per leg"), (9.99, "ATM straddle, no stop")):
        stats(run(sl), lab)
    t = run(0.20)
    print("avg premium collected (pts):", round(t.premium.mean(), 1), "| expiry-day share of profit:",
          round(t.rs[t.dte == 0].sum() / t.rs.sum() * 100) if t.rs.sum() else "n/a")
