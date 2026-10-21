"""
Vivek Bajaj 3-layer capital sizing framework, backtested on Nifty 500 data (2006-2026).
Layer 1 regime (4 signals) -> equity / gold / cash split
Layer 2 sector allocation  -> only buy stocks in the strongest sectors
Layer 3 stock sizing       -> position size scaled by regime, trimmed on downgrades
Tested (a) standalone on the Nifty 500 index and (b) as an overlay on the user's 3 PM breakout system.
Usage: python regime.py <data_dir> <extra_dir> <sectors.txt> <out_dir>
"""
import sys, os, glob, json
import numpy as np
import pandas as pd

DATA, EXTRA, SECT, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)
START, COST, CASH_Y = "2006-01-01", 0.0015, 0.06

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    return d[~d.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]].astype(float)

idx = load(os.path.join(DATA, "IDX_CRSLDX.csv"))
dates = idx.index[idx.index >= pd.Timestamp(START) - pd.Timedelta(days=500)]
O, L, C, V = {}, {}, {}, {}
for f in glob.glob(os.path.join(DATA, "*.NS.csv")):
    s = os.path.basename(f)[:-7]
    d = load(f); d = d[d.close > 0].reindex(dates)
    O[s], L[s], C[s], V[s] = d.open, d.low, d.close, d.volume
O, L, C, V = (pd.DataFrame(x) for x in (O, L, C, V))
r = C.pct_change(fill_method=None)
bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
for X in (O, L, C):
    X[bad] = np.nan
syms = list(C.columns)
ic = idx.close.reindex(dates).ffill()

# gold in INR = COMEX gold (USD/oz) x USDINR
g = pd.read_csv(os.path.join(EXTRA, "GC_F.csv"), index_col=0, parse_dates=True)["close"]
fx = pd.read_csv(os.path.join(EXTRA, "INR_X.csv"), index_col=0, parse_dates=True)["close"]
gold = (g * fx.reindex(g.index).ffill()).reindex(dates).ffill()

# ---------------------------------------------------------------- Layer 1: regime signals
sma200_i = ic.rolling(200).mean()
sig_trend = ic > sma200_i                                               # 1. index above 200-DMA
sma200_s = C.rolling(200, min_periods=200).mean()
breadth = (C > sma200_s).sum(axis=1) / sma200_s.notna().sum(axis=1)
sig_breadth = breadth >= 0.5                                            # 2. >=50% of stocks above their 200-DMA
rv20 = ic.pct_change().rolling(20).std() * np.sqrt(252)
sig_vol = rv20 <= rv20.rolling(252).median()                            # 3. volatility calmer than its 1-yr norm
mkt_turn = (C * V).sum(axis=1)
sig_liq = mkt_turn.rolling(50).mean() >= mkt_turn.rolling(200).mean()  # 4. liquidity proxy: market turnover rising
score = sig_trend.astype(int) + sig_breadth.astype(int) + sig_vol.astype(int) + sig_liq.astype(int)
# evaluated on Friday close, applied from the next session (no lookahead)
wk_score = score.resample("W-FRI").last()
regime_score = wk_score.shift(1).reindex(dates, method="ffill")      # last completed week's score
regime_score = wk_score.reindex(dates, method="ffill").shift(1)       # value known at prior day's close
def regime_of(sc):
    return "Bullish" if sc >= 3 else ("Neutral" if sc == 2 else "Crisis")
REGIME = regime_score.map(lambda x: regime_of(x) if not np.isnan(x) else "Bullish")

ALLOC = {  # equity, gold, cash
    "default": {"Bullish": (1.0, 0.0, 0.0), "Neutral": (0.6, 0.2, 0.2), "Crisis": (0.2, 0.4, 0.4)},
    "crisis0": {"Bullish": (1.0, 0.0, 0.0), "Neutral": (0.6, 0.2, 0.2), "Crisis": (0.0, 0.5, 0.5)},
    "nogold":  {"Bullish": (1.0, 0.0, 0.0), "Neutral": (0.6, 0.0, 0.4), "Crisis": (0.2, 0.0, 0.8)},
}

# ---------------------------------------------------------------- Layer 2: sector strength
sector = {}
for line in open(SECT):
    if "|" in line:
        a, b = line.strip().split("|", 1); sector[a] = b
sec_of = pd.Series({s: sector.get(s, "Other") for s in syms})
ret = r.clip(-0.5, 0.5)
SI = pd.DataFrame({k: (1 + ret[list(m)].mean(axis=1).fillna(0)).cumprod() for k, m in sec_of.groupby(sec_of).groups.items()})
SN = pd.DataFrame({k: ret[list(m)].notna().sum(axis=1) for k, m in sec_of.groupby(sec_of).groups.items()})
sscore = ((SI / SI.shift(21) - 1).rank(axis=1, pct=True) + (SI / SI.shift(63) - 1).rank(axis=1, pct=True)).where(SN >= 3)
sec_top = sscore.rank(axis=1, ascending=False) <= 8                    # top 8 of ~22 sectors
stock_in_top_sector = pd.DataFrame({s: sec_top[sec_of[s]] for s in syms})

# ---------------------------------------------------------------- 3 PM breakout signals (user's system)
hi52 = C.shift(1).rolling(252, min_periods=240).max()
vavg50 = V.shift(1).rolling(50, min_periods=40).mean()
turn20 = (C * V).rolling(20, min_periods=15).mean()
mom63 = C / C.shift(63) - 1
low20 = C.shift(1).rolling(20, min_periods=20).min()
mkt_on = ic > ic.ewm(span=50, adjust=False).mean()
entry_sig = (C > hi52) & (V >= 1.5 * vavg50) & (C > sma200_s) & (turn20 >= 5e7)

def run_overlay(use_regime=True, use_sector=False, alloc="default", trim=True, max_pos=10, base_w=0.10, stop=0.10):
    A = ALLOC[alloc]
    dts = dates[dates >= pd.Timestamp(START)]
    di = {d: i for i, d in enumerate(dates)}
    col = {s: j for j, s in enumerate(syms)}
    Cv, Lv, Ov, Gv = C.values, L.values, O.values, gold.values
    cash, gold_units, pos, curve, trades = 1.0, 0.0, {}, [], []

    def px_of(s, i, p): v = Cv[i, col[s]]; return p["px"] if np.isnan(v) else v
    def equity(i): return cash + gold_units * Gv[i] + sum(p["sh"] * px_of(s, i, p) for s, p in pos.items())
    def sell(s, px, d, why, frac=1.0):
        nonlocal cash
        p = pos[s]; sh = p["sh"] * frac
        cash += sh * px * (1 - COST)
        if frac >= 0.999:
            pos.pop(s)
            trades.append(dict(sym=s, entry_date=p["d"], exit_date=d, entry=p["px"], exit=px,
                               ret=px * (1 - COST) / (p["px"] * (1 + COST)) - 1, why=why))
        else:
            p["sh"] -= sh

    prev_reg = None
    for d in dts:
        i = di[d]
        cash *= (1 + CASH_Y) ** (1 / 252)
        reg = REGIME.iat[i] if use_regime else "Bullish"
        eqf, gdf, _ = A[reg] if use_regime else (1.0, 0.0, 0.0)
        # GTT stop -10% intraday
        for s in list(pos):
            j = col[s]; sl = pos[s]["px"] * (1 - stop)
            if not np.isnan(Lv[i, j]) and Lv[i, j] <= sl:
                sell(s, min(Ov[i, j], sl) if not np.isnan(Ov[i, j]) else sl, d, "stop")
        # 3 PM exits
        for s in list(pos):
            c = Cv[i, col[s]]
            if np.isnan(c):
                continue
            if c < low20.iat[i, col[s]]:
                sell(s, c, d, "trail")
            elif not mkt_on.iat[i] and c < pos[s]["px"]:
                sell(s, c, d, "filter_off")
        eq = equity(i)
        tgt_w = base_w * eqf
        # Layer 3: trim existing positions when the regime downgrades
        if use_regime and trim and prev_reg is not None and reg != prev_reg:
            for s in list(pos):
                v = pos[s]["sh"] * px_of(s, i, pos[s])
                if v > tgt_w * eq * 1.02:
                    sell(s, px_of(s, i, pos[s]), d, "trim", frac=1 - (tgt_w * eq) / v if tgt_w > 0 else 1.0)
        # Layer 1: gold sleeve, rebalanced on regime change and every Friday
        if use_regime and (reg != prev_reg or d.weekday() == 4):
            want = gdf * eq; have = gold_units * Gv[i]; delta = want - have
            if abs(delta) > 0.02 * eq or (gdf == 0 and have > 0):
                if delta > 0:
                    delta = min(delta, cash / (1 + COST))
                    cash -= delta * (1 + COST); gold_units += delta / Gv[i]
                else:
                    cash += -delta * (1 - COST); gold_units += delta / Gv[i]
        prev_reg = reg
        # entries (3 PM rules), sized by regime
        eq = equity(i)
        if mkt_on.iat[i] and len(pos) < max_pos and tgt_w > 0:
            row = entry_sig.iloc[i]
            if use_sector:
                row = row & stock_in_top_sector.iloc[i]
            cands = [s for s in row.index[row.fillna(False).values] if s not in pos]
            cands.sort(key=lambda s: -(mom63.iat[i, col[s]] if not np.isnan(mom63.iat[i, col[s]]) else -9))
            for s in cands[: max_pos - len(pos)]:
                px = Cv[i, col[s]]
                val = min(tgt_w * eq, cash / (1 + COST))
                if val < 0.005 * eq:
                    break
                cash -= val * (1 + COST)
                pos[s] = dict(sh=val / px, px=px, d=d)
        curve.append((d, equity(i), len(pos), reg, gold_units * Gv[i] / equity(i)))
    ec = pd.DataFrame(curve, columns=["date", "equity", "npos", "regime", "gold_w"]).set_index("date")
    return ec, pd.DataFrame(trades)

def run_index(alloc="default", use_regime=True, simple200=False):
    """Standalone framework on the Nifty 500 index: equity sleeve = index, plus gold and cash."""
    A = ALLOC[alloc]
    dts = dates[dates >= pd.Timestamp(START)]
    val, w, out, prev = 1.0, None, [], None
    ir, gr = ic.pct_change().fillna(0), gold.pct_change().fillna(0)
    cr = (1 + CASH_Y) ** (1 / 252) - 1
    for d in dts:
        if simple200:
            reg = "Bullish" if sig_trend.shift(1).reindex([d]).iloc[0] else "Crisis"
            tgt = (1.0, 0.0, 0.0) if reg == "Bullish" else (0.0, 0.0, 1.0)
        else:
            reg = REGIME.loc[d] if use_regime else "Bullish"
            tgt = A[reg]
        if w is None or reg != prev or (d.is_month_end if hasattr(d, "is_month_end") else False):
            if w is not None:
                turnover = sum(abs(a - b) for a, b in zip(tgt, w)) / 2
                val *= 1 - turnover * COST
            w = list(tgt)
        rr = (ir.loc[d], gr.loc[d], cr)
        parts = [wi * (1 + ri) for wi, ri in zip(w, rr)]
        g_ = sum(parts); val *= g_; w = [p / g_ for p in parts]
        out.append((d, val, reg)); prev = reg
    return pd.DataFrame(out, columns=["date", "equity", "regime"]).set_index("date")

def stats(e, tr=None):
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = e / e.cummax() - 1; dr = e.pct_change().dropna()
    o = dict(cagr=e.iloc[-1] ** (1 / yrs) - 1, max_dd=dd.min(), sharpe=dr.mean() / dr.std() * np.sqrt(252),
             vol=dr.std() * np.sqrt(252), final_x=e.iloc[-1])
    o["calmar"] = o["cagr"] / abs(o["max_dd"])
    for n in (3, 10):
        s = e[e.index >= e.index[-1] - pd.DateOffset(years=n)]; o[f"cagr_{n}y"] = (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
    for a, b, lab in (("2008-01-01", "2009-03-31", "dd_2008"), ("2020-01-15", "2020-04-30", "dd_2020"), ("2024-09-20", "2026-10-16", "dd_2024_26")):
        s = e.loc[a:b]; o[lab] = (s / s.cummax() - 1).min()
    if tr is not None and len(tr):
        o.update(trades=len(tr), win_rate=(tr.ret > 0).mean())
    return o

if __name__ == "__main__":
    rg = REGIME[REGIME.index >= START]
    print("Time in each regime:", (rg.value_counts(normalize=True) * 100).round(1).to_dict(),
          "| regime changes per year:", round((rg != rg.shift()).sum() / 20.8, 1))
    res, eqs = {}, {}
    # (a) standalone on the index
    bh = (ic / ic.loc[START:].iloc[0]).loc[START:]
    for lab, e in (("Index: Nifty 500 buy & hold", bh),
                   ("Index: 200-DMA only (in/out to cash)", run_index(simple200=True).equity),
                   ("Index: 3-layer regime (equity/gold/cash)", run_index().equity),
                   ("Index: 3-layer regime, 0% equity in crisis", run_index(alloc="crisis0").equity)):
        res[lab] = stats(e); eqs[lab] = e
    # (b) overlay on the user's 3 PM system
    for lab, kw in (("3 PM: as is", dict(use_regime=False)),
                    ("3 PM + regime sizing (layers 1+3)", dict()),
                    ("3 PM + regime sizing + top sectors (all 3 layers)", dict(use_sector=True)),
                    ("3 PM + top sectors only (layer 2)", dict(use_regime=False, use_sector=True)),
                    ("3 PM + regime sizing, cash instead of gold", dict(alloc="nogold")),
                    ("3 PM + regime sizing, no trimming", dict(trim=False))):
        ec, tr = run_overlay(**kw)
        res[lab] = stats(ec.equity, tr); eqs[lab] = ec.equity
        if lab == "3 PM + regime sizing (layers 1+3)":
            ec.to_csv(os.path.join(OUT, "overlay_detail.csv"))
    for k, o in res.items():
        print(f"{k:52s} CAGR {o['cagr']*100:5.1f}%  DD {o['max_dd']*100:6.1f}%  Sh {o['sharpe']:.2f}  Calmar {o['calmar']:.2f}  "
              f"3y {o['cagr_3y']*100:5.1f}%  10y {o['cagr_10y']*100:5.1f}%  | 08 {o['dd_2008']*100:5.1f}%  20 {o['dd_2020']*100:5.1f}%  24-26 {o['dd_2024_26']*100:5.1f}%")
    pd.DataFrame(eqs).to_csv(os.path.join(OUT, "equity_all.csv"))
    json.dump(res, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=float)
    y = pd.DataFrame(eqs).resample("YE").last(); yr = y.pct_change(); yr.iloc[0] = y.iloc[0] - 1; yr.index = yr.index.year
    print((yr[["Index: Nifty 500 buy & hold", "Index: 3-layer regime (equity/gold/cash)", "3 PM: as is", "3 PM + regime sizing (layers 1+3)"]] * 100).round(1).to_string())
