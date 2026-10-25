"""Sensex weekly-expiry short straddle backtest, May 2023 - Oct 2026 (rebuilt prices; BSE option bhavcopies are not reachable from here).

Expiry days: Friday (15 May 2023 - Dec 2024), Tuesday (Jan - Aug 2025), Thursday (Sep 2025 onwards); holiday -> previous trading day.
Minute path: real Sensex 1-minute data if SENSEX_1MIN file exists (Kite), else Nifty's 1-minute path scaled to the Sensex level
(intraday correlation ~0.98).  Option prices: Black-Scholes with the day's 0-DTE implied vol = (Nifty-calibrated ratio of
0-DTE open IV to India VIX) x yesterday's VIX.  Strikes every 100 pts, lot 20, costs: STT 0.1% sell + 0.04%/side + Rs 40 + 1.5 pt slippage/side.
Rules tested:
 A  StockMock rule: sell ATM straddle 9:16, exit both if Sensex moves 500 pts from entry, else exit 15:15
 B  Same + 'paper check': only trade if the 9:16 straddle is in profit at 9:36 (enter at 9:36)
 C  Our Nifty rule, 1 lot: 10:05 straddle, 30% SL/leg
 D  Our improved Nifty rule, 3 lots: 9:22/9:35/10:05, 40% SL/leg, other leg SL to cost, 1 re-entry before 13:00"""
import os, numpy as np, pandas as pd, yfinance as yf
from scipy.special import ndtr
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"
SENSEX_1MIN = f"{SP}/sensex_1min.csv"
LOT, R, YM, STEP = 20, 0.065, 375 * 252, 100
nm = pd.read_csv("/home/claude/nsedata/intraday/index_1min/nifty50_1min_kite_2015-2026.csv.gz", parse_dates=["date"]).set_index("date").sort_index()
vix = pd.read_csv("/home/claude/nsedata/daily/extra/INDIAVIX.csv", parse_dates=["Date"]).set_index("Date").close
dl = yf.download(["^BSESN", "^NSEI"], start="2023-04-01", progress=False, auto_adjust=True)["Close"].dropna()
ratio = (dl["^BSESN"] / dl["^NSEI"]).shift(1)
REAL = os.path.exists(SENSEX_1MIN)
sm = pd.read_csv(SENSEX_1MIN, parse_dates=["date"]).set_index("date").sort_index() if REAL else None
# ---- IV calibration on Nifty expiry days (from entry_time.py rebuild): open 0DTE IV vs yesterday's VIX
src = open("/home/claude/nsedata/strategies/option_selling/entry_time.py").read().split("def trade(")[0]; exec(src)
cal = pd.DataFrame([(dt, iv) for dt, b, iv, _ in days], columns=["date", "iv"]).set_index("date")
cal["vix"] = vix.shift(1).reindex(cal.index, method="ffill") / 100; cal = cal[cal.index >= "2021-01-01"]
LOT, R, YM, STEP = 20, 0.065, 375 * 252, 100
K_IV = float((cal.iv / cal.vix).median()); print("0-DTE IV / VIX ratio (Nifty 2021-26):", round(K_IV, 3), " corr", round(cal.iv.corr(cal.vix), 2))
# ---- expiry calendar
td = dl.index
def exp_days():
    out = []
    for wk, g in pd.Series(td, index=td).groupby(td.to_period("W-SUN")):
        d0 = g.index[0]
        if d0 < pd.Timestamp("2023-05-15"): continue
        wd = 4 if d0 < pd.Timestamp("2025-01-01") else (1 if d0 < pd.Timestamp("2025-09-01") else 3)
        cand = [d for d in g.index if d.weekday() <= wd]
        if cand: out.append(max(cand))
    return out
EXP = exp_days()
def bsv(S, K, T, v, cp):
    T = np.maximum(T, 1e-7); sq = v * np.sqrt(T); d1 = (np.log(S / K) + (R + v * v / 2) * T) / sq; d2 = d1 - sq
    return S * ndtr(d1) - K * np.exp(-R * T) * ndtr(d2) if cp == "C" else K * np.exp(-R * T) * ndtr(-d2) - S * ndtr(-d1)
def cost(pi, po): return pi * 0.0010 + (pi + po) * 0.0004 + 47.2 / LOT + 3.0
PRE = []; ND = set(nm.index.normalize())
for d in EXP:
    if REAL and str(d.date()) in sm.index.strftime("%Y-%m-%d"): b = sm.loc[str(d.date())]
    else:
        if d not in ND: continue
        b = nm.loc[str(d.date())] * float(ratio.get(d, np.nan))
    b = b.between_time("09:15", "15:29")
    v = vix.shift(1).reindex([d], method="ffill").iloc[0] / 100
    if len(b) < 300 or np.isnan(v) or b.isna().any().any(): continue
    t = np.array([x.hour * 60 + x.minute for x in b.index]); T = np.array([(930 - m_) for m_ in t]) / YM
    PRE.append(dict(dt=d, t=t, o=b.open.values, h=b.high.values, l=b.low.values, c=b.close.values, T=T, iv=K_IV * v))
print("Sensex expiry days simulated:", len(PRE), "| minute data:", "real Sensex" if REAL else "Nifty path scaled to Sensex")
def hm(s): h, m_ = map(int, s.split(":")); return h * 60 + m_

def straddle(p, entry, sl=0.30, be=False, reentry=False, spot_sl=None, exit_t="15:15", paper=None):
    t = p["t"]; iv = p["iv"]; T = p["T"]; i0 = np.searchsorted(t, hm(entry)); ie = np.searchsorted(t, hm(exit_t))
    if paper:                                                      # paper-trade from `entry`, real entry at `paper` time only if in profit
        k0 = round(p["o"][i0] / STEP) * STEP; e0 = bsv(p["o"][i0], k0, T[i0], iv, "C") + bsv(p["o"][i0], k0, T[i0], iv, "P")
        j = np.searchsorted(t, hm(paper)); v = bsv(p["c"][j - 1], k0, T[j - 1], iv, "C") + bsv(p["c"][j - 1], k0, T[j - 1], iv, "P")
        if v >= e0: return None
        i0 = j
    pnl = 0.0; reentered = False
    while True:
        s0 = p["o"][i0]; k = round(s0 / STEP) * STEP
        e = {cp: float(bsv(s0, k, T[i0], iv, cp)) for cp in "CP"}; slv = {cp: e[cp] * (1 + sl) for cp in "CP"}; op = {"C": True, "P": True}
        Ch, Pl = bsv(p["h"], k, T, iv, "C"), bsv(p["l"], k, T, iv, "P"); Cc, Pc = bsv(p["c"], k, T, iv, "C"), bsv(p["c"], k, T, iv, "P")
        i = i0; restart = None
        while i < ie:
            if spot_sl and (p["h"][i] >= s0 + spot_sl or p["l"][i] <= s0 - spot_sl):
                lvl = s0 + spot_sl if p["h"][i] >= s0 + spot_sl else s0 - spot_sl
                for cp in "CP":
                    if op[cp]: x = float(bsv(lvl, k, T[i], iv, cp)) * 1.01; pnl += e[cp] - x - cost(e[cp], x); op[cp] = False
                break
            for cp, w in (("C", Ch[i]), ("P", Pl[i])):
                if sl < 5 and op[cp] and w >= slv[cp]:
                    x = slv[cp] * 1.01; pnl += e[cp] - x - cost(e[cp], x); op[cp] = False
                    o = "P" if cp == "C" else "C"
                    if be and op[o]: slv[o] = e[o]
            if not (op["C"] or op["P"]):
                if reentry and not reentered and t[i] < hm("13:00") and i + 1 < ie: reentered = True; restart = i + 1
                break
            i += 1
        else:
            for cp, arr in (("C", Cc), ("P", Pc)):
                if op[cp]: x = arr[ie]; pnl += e[cp] - x - cost(e[cp], x)
        if restart is None: return pnl
        i0 = restart

V = {"A  StockMock: 9:16 straddle, 500-pt spot SL": [dict(entry="09:16", sl=9, spot_sl=500)],
     "B  A + paper check at 9:36": [dict(entry="09:16", sl=9, spot_sl=500, paper="09:36")],
     "C  10:05 straddle, 30% SL/leg (1 lot)": [dict(entry="10:05")],
     "D  3 lots 9:22/9:35/10:05, 40% SL + cost + re-entry": [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:22", "09:35", "10:05")]}
rows = []; daily = {}
for name, legs in V.items():
    s = {}
    for p in PRE:
        r = [straddle(p, **kw) for kw in legs]
        if all(x is None for x in r): continue
        s[p["dt"]] = sum(x for x in r if x is not None) * LOT
    s = pd.Series(s); daily[name] = s; eq = s.cumsum(); yr = s.groupby(s.index.year).sum()
    yrs = (PRE[-1]["dt"] - PRE[0]["dt"]).days / 365.25
    rows.append(dict(rule=name, days_traded=len(s), win=round((s > 0).mean() * 100, 1), avg_rs=round(s.mean()), rs_per_year=round(s.sum() / yrs),
                     total=round(s.sum()), worst_day=round(s.min()), max_dd=round((eq - eq.cummax()).min()), losing_years=int((yr < 0).sum()),
                     **{f"y{y}": round(v_) for y, v_ in yr.items()}))
R_ = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R_.to_string(index=False))
R_.to_csv("sensex_expiry_summary.csv", index=False); pd.DataFrame(daily).to_csv("sensex_expiry_daily.csv")
for name, s in daily.items():
    print(name, {k: round(v_) for k, v_ in s.groupby(s.index.dayofweek.map({1: "Tue", 3: "Thu", 4: "Fri", 0: "Mon", 2: "Wed"})).sum().items()})
