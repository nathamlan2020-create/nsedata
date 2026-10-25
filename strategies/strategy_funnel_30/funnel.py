"""Strategy-validation funnel on 30 Indian assets (indices, ETFs, gold, large stocks), Jan 2011 - Oct 2026 (~15.8 years).
Replicates the 'thousands of backtests -> filters -> robustness -> layered system' idea, long-only (no shorting in cash).

Execution: signal at today's close, trade at tomorrow's OPEN. Costs 0.10%/side (ETFs/indices), 0.15%/side (stocks).
Cash earns 6%/yr. Indices are price indices (no dividends) - tradeable via ETFs/futures.
Split: in-sample (IS) 2011-2019, out-of-sample (OOS) 2020-2026.

Funnel (applied in order):
 F1 activity  : >= 30 trades over the full period (trend/momentum: >= 10 trades and invested >= 15% of the time)
 F2 IS quality: IS Sharpe (excess of 6% cash) >= 0.40 and IS max drawdown better than -25%
 F3 walk-fwd  : OOS Sharpe >= 0.30 and >= 40% of IS Sharpe; OOS max drawdown better than -30%
 F4 robustness: (a) costs x2 -> full-period Sharpe >= 0.25  (b) 1-day-late execution -> Sharpe >= 0.20
                (c) parameter neighbourhood: >= 50% of the same rule's parameter sets on that asset have full Sharpe >= 0.20
                (d) beats cash in >= 55% of calendar years
Plus a true walk-forward per family: each year 2016-2026 pick, per asset, the family's best Sharpe parameter set on the
prior 5 years and trade it next year; stitch the yearly OOS pieces."""
import numpy as np, pandas as pd, itertools, time, sys
P = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/funnel_data.pkl"
RAW = pd.read_pickle(P); RF = 0.06; LIQ = RF / 252
START, SPLIT = pd.Timestamp("2011-01-01"), pd.Timestamp("2020-01-01")
STOCKS = {"RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "ITC", "LT", "SBIN", "HINDUNILVR", "BHARTIARTL", "AXISBANK", "KOTAKBANK", "MARUTI"}

def rsi(c, n):
    d = c.diff(); u = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); v = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + u / v)
def state(entry, exit_):                       # 1 after entry until exit (vectorised state machine)
    s = pd.Series(np.nan, index=entry.index); s[exit_.fillna(False)] = 0; s[entry.fillna(False)] = 1
    return s.ffill().fillna(0)
def hold_n(entry, n):                          # in position for n days after each entry
    return entry.fillna(False).astype(float).rolling(n, min_periods=1).max()

def strategies(d):
    O, H, L, C = d.Open, d.High, d.Low, d.Close; out = {}
    sma = {n: C.rolling(n).mean() for n in (5, 10, 20, 30, 50, 100, 150, 200, 250)}
    up200 = C > sma[200]
    # ---------- mean reversion ----------
    for n in (2, 3, 5):
        R = rsi(C, n)
        for x, y, f in itertools.product((5, 10, 15, 20, 25, 30), (50, 65, 80), (0, 1)):
            out[("mean_reversion", f"RSI{n}<{x} exit>{y}" + (" +200SMA" if f else ""), "RSI", (n, x, y, f))] = state((R < x) & (up200 if f else True), R > y)
    for n, k, f in itertools.product((10, 20, 30), (1, 1.5, 2, 2.5), (0, 1)):
        m = C.rolling(n).mean(); sd = C.rolling(n).std()
        out[("mean_reversion", f"Bollinger {n},{k} exit>mid" + (" +200SMA" if f else ""), "BB", (n, k, f))] = state((C < m - k * sd) & (up200 if f else True), C > m)
    for n, ex, f in itertools.product((3, 5, 7, 10), ("prevhigh", "sma5"), (0, 1)):
        ent = (C <= C.rolling(n).min()) & (up200 if f else True)
        xt = C > H.shift(1) if ex == "prevhigh" else C > sma[5]
        out[("mean_reversion", f"{n}-day low exit {ex}" + (" +200SMA" if f else ""), "NLOW", (n, ex, f))] = state(ent, xt)
    ibs = (C - L) / (H - L).replace(0, np.nan)
    for x, y, f in itertools.product((0.1, 0.2, 0.3), (0.5, 0.7, 0.8), (0, 1)):
        out[("mean_reversion", f"IBS<{x} exit>{y}" + (" +200SMA" if f else ""), "IBS", (x, y, f))] = state((ibs < x) & (up200 if f else True), ibs > y)
    # ---------- trend following ----------
    for a, b in itertools.product((5, 10, 20, 50), (50, 100, 150, 200)):
        if a < b: out[("trend", f"SMA {a}/{b} cross", "SMAX", (a, b))] = (sma[a] > sma[b]).astype(float)
    for n, bd in itertools.product((20, 50, 100, 150, 200, 250), (0, 0.02)):
        out[("trend", f"Close>SMA{n}" + (f" band{int(bd*100)}%" if bd else ""), "PSMA", (n, bd))] = state(C > sma[n] * (1 + bd), C < sma[n] * (1 - bd))
    for n, m in itertools.product((20, 50, 100, 200), (10, 20, 50)):
        if m < n: out[("trend", f"Donchian {n}/{m}", "DON", (n, m))] = state(C >= C.shift(1).rolling(n).max(), C <= C.shift(1).rolling(m).min())
    for a, b in ((8, 21), (12, 26), (21, 55), (34, 89), (50, 200)):
        out[("trend", f"EMA {a}/{b} cross", "EMAX", (a, b))] = (C.ewm(span=a, adjust=False).mean() > C.ewm(span=b, adjust=False).mean()).astype(float)
    # ---------- momentum ----------
    for n, th in itertools.product((21, 63, 126, 189, 252), (0, 0.05, 0.10)):
        out[("momentum", f"ROC{n}>{int(th*100)}%", "ROC", (n, th))] = (C / C.shift(n) - 1 > th).astype(float)
    for n in (63, 126, 189, 252):
        out[("momentum", f"ROC{n} skip21 >0", "ROCS", (n,))] = (C.shift(21) / C.shift(n) - 1 > 0).astype(float)
        out[("momentum", f"Dual: ROC{n}>6% & >200SMA", "DUAL", (n,))] = ((C / C.shift(n) - 1 > (1.06 ** (n / 252) - 1)) & up200).astype(float)
    # ---------- volatility ----------
    ret = C.pct_change()
    for vl, pc in itertools.product((10, 20, 60), (0.5, 0.6, 0.7, 0.8)):
        v = ret.rolling(vl).std(); rk = v.rolling(252, min_periods=126).rank(pct=True)
        out[("volatility", f"Low-vol regime: vol{vl} < {int(pc*100)}th pct", "LOWV", (vl, pc))] = (rk < pc).astype(float)
    tr = pd.concat([H - L, (H - C.shift()).abs(), (L - C.shift()).abs()], axis=1).max(axis=1)
    for n, k, hd in itertools.product((10, 20), (0.5, 1, 1.5, 2), (5, 10, 20)):
        atr = tr.rolling(n).mean()
        out[("volatility", f"Vol breakout: +{k} ATR{n}, hold {hd}d", "VBO", (n, k, hd))] = hold_n(C > C.shift(1) + k * atr.shift(1), hd)
    for n, k in itertools.product((10, 20), (1.5, 2, 2.5)):
        m = C.ewm(span=20, adjust=False).mean(); atr = tr.rolling(n).mean()
        out[("volatility", f"Keltner breakout {k} ATR{n} exit<EMA20", "KELT", (n, k))] = state(C > m + k * atr, C < m)
    return out

def returns(d, pos, cost, lag=0):
    """pos decided at close t -> executed at open t+1 (lag adds extra days of delay)."""
    O, C = d.Open, d.Close; p = pos.shift(lag).fillna(0)
    g = O / C.shift(1) - 1; intr = C / O - 1
    pt, pp = p.shift(1).fillna(0), p.shift(2).fillna(0)                     # pt = position held during day t+1 session
    r = (1 + pp * g) * (1 + pt * intr) - 1 + (1 - pt) * LIQ - (pt - pp).abs() * cost
    return r.fillna(0), pt

def metr(r, pt=None):
    if len(r) < 50 or r.std() == 0: return dict(sharpe=np.nan, cagr=np.nan, dd=np.nan)
    e = (1 + r).cumprod(); yrs = len(r) / 252
    return dict(sharpe=(r.mean() - LIQ) / r.std() * np.sqrt(252), cagr=e.iloc[-1] ** (1 / yrs) - 1, dd=(e / e.cummax() - 1).min())

if __name__ == "__main__":
    t0 = time.time(); rows = []; RET = {}
    for asset, d0 in RAW.items():
        d = d0[d0.index >= "2010-01-01"].copy()
        r1 = d.Close.pct_change(); bad = (r1.abs() > 0.25) & (r1.shift(-1).abs() > 0.2)      # bad ticks in thin ETF data
        d.loc[bad, ["Open", "High", "Low", "Close"]] = np.nan; d = d.ffill()
        r1 = d.Close.pct_change()
        for t in r1.index[(r1.abs() > 0.40)]:                          # unadjusted splits (e.g. ETF 1:10): rescale history
            k = d.Close.loc[t] / d.Close.shift(1).loc[t]; d.loc[d.index < t, ["Open", "High", "Low", "Close"]] *= k
            print("  split-adjusted", asset, t.date(), round(1 / k, 2))
        cost = 0.0015 if asset in STOCKS else 0.0010
        S = strategies(d); m = d.index >= START; isx = d.index < SPLIT
        bh, _ = returns(d, pd.Series(1.0, index=d.index), cost)
        for (fam, name, rule, prm), pos in S.items():
            r, pt = returns(d, pos, cost); r, pt = r[m], pt[m]
            r2, _ = returns(d, pos, 2 * cost); r2 = r2[m]
            rl, _ = returns(d, pos, cost, lag=1); rl = rl[m]
            ent = int(((pt - pt.shift(1).fillna(0)) > 0).sum())
            full, IS, OOS = metr(r), metr(r[isx[m]]), metr(r[~isx[m]])
            yr = (1 + r).groupby(r.index.year).prod() - 1; cashy = (1 + LIQ) ** r.groupby(r.index.year).size() - 1
            rows.append(dict(asset=asset, family=fam, strategy=name, rule=rule, params=str(prm), trades=ent, invested=pt.mean(),
                             sharpe=full["sharpe"], cagr=full["cagr"], dd=full["dd"], is_sharpe=IS["sharpe"], is_dd=IS["dd"], is_cagr=IS["cagr"],
                             oos_sharpe=OOS["sharpe"], oos_dd=OOS["dd"], oos_cagr=OOS["cagr"], sharpe_cost2=metr(r2)["sharpe"],
                             sharpe_lag1=metr(rl)["sharpe"], yrs_beat_cash=(yr > cashy).mean()))
            RET[(asset, fam, name)] = r.astype("float32")
        bm = metr(bh[m]); rows.append(dict(asset=asset, family="buy_hold", strategy="Buy & hold", rule="BH", params="", trades=1, invested=1,
                                           sharpe=bm["sharpe"], cagr=bm["cagr"], dd=bm["dd"], is_sharpe=metr(bh[m & isx])["sharpe"], oos_sharpe=metr(bh[m & ~isx])["sharpe"],
                                           is_dd=metr(bh[m & isx])["dd"], oos_dd=metr(bh[m & ~isx])["dd"], oos_cagr=metr(bh[m & ~isx])["cagr"], is_cagr=metr(bh[m & isx])["cagr"]))
        print(f"{asset:28s} {len(S)} strategies  {time.time()-t0:.0f}s", flush=True)
    A = pd.DataFrame(rows); A.to_csv("all_backtests.csv.gz", index=False, compression="gzip")
    pd.to_pickle(pd.DataFrame(RET), "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/funnel_returns.pkl")
    print("total backtests:", (A.family != "buy_hold").sum())
