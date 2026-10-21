"""
Sector-momentum + contraction (VCP-style) swing strategy, Nifty 500, 2006-2026.
Mechanical reading of the video's rules:
  1 trending sector  2 trending stock, <=15% up in a month  3 contraction after a prior move
  4 volume dries up in the contraction   5 EMA 20/50/100/200 for timing, stop below 20 EMA, 1:2 R:R
Usage: python sector_vcp.py <data_dir> <sectors.txt> <out_dir>
"""
import sys, os, glob, json
import numpy as np
import pandas as pd

DATA, SECT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
START, COST = "2006-01-01", 0.0015

def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True)
    return d[~d.index.duplicated()].sort_index()[["open", "high", "low", "close", "volume"]].astype(float)

idx = load(os.path.join(DATA, "IDX_CRSLDX.csv"))
dates = idx.index[idx.index >= pd.Timestamp(START) - pd.Timedelta(days=500)]
O, H, L, C, V = {}, {}, {}, {}, {}
for f in glob.glob(os.path.join(DATA, "*.NS.csv")):
    s = os.path.basename(f)[:-7]
    d = load(f); d = d[d.close > 0].reindex(dates)
    O[s], H[s], L[s], C[s], V[s] = d.open, d.high, d.low, d.close, d.volume
O, H, L, C, V = (pd.DataFrame(x) for x in (O, H, L, C, V))
r = C.pct_change(fill_method=None)
bad = (r.abs() > 0.6) & (r.shift(-1).abs() > 0.35)
for X in (O, H, L, C):
    X[bad] = np.nan
syms = list(C.columns)

sector = {}
for line in open(SECT):
    if "|" in line:
        a, b = line.strip().split("|", 1); sector[a] = b
sec_of = pd.Series({s: sector.get(s, "Other") for s in syms})

# ---------------------------------------------------------------- 1. sector strength
ret = C.pct_change(fill_method=None).clip(-0.5, 0.5)
sec_idx, sec_n = {}, {}
for sname, members in sec_of.groupby(sec_of).groups.items():
    m = list(members)
    sec_idx[sname] = (1 + ret[m].mean(axis=1).fillna(0)).cumprod()
    sec_n[sname] = ret[m].notna().sum(axis=1)
SI, SN = pd.DataFrame(sec_idx), pd.DataFrame(sec_n)
s20, s60 = SI / SI.shift(20) - 1, SI / SI.shift(60) - 1
s_ema50 = SI.ewm(span=50, adjust=False).mean()
valid = SN >= 3
score = (s20.rank(axis=1, pct=True) + s60.rank(axis=1, pct=True)).where(valid)
srank = score.rank(axis=1, ascending=False)
# trending sector: top 5 by blended 1-month + 3-month strength, above its 50 EMA, both returns positive
sec_ok = (srank <= 5) & (SI > s_ema50) & (s20 > 0) & (s60 > 0) & valid
stock_sec_ok = pd.DataFrame({s: sec_ok[sec_of[s]] for s in syms})

# ---------------------------------------------------------------- 2-4. stock setup
e20, e50, e100, e200 = (C.ewm(span=n, adjust=False).mean() for n in (20, 50, 100, 200))
have200 = C.notna().rolling(200).sum() >= 200
ema_stack = (e20 > e50) & (e50 > e100) & (e100 > e200) & (C > e20) & have200
r21, r63 = C / C.shift(21) - 1, C / C.shift(63) - 1
moderate = (r21 >= 0) & (r21 <= 0.15)                 # up, but <=15% in a month
prior_move = r63 >= 0.10                               # an initial move happened
hi10, lo10 = H.rolling(10).max(), L.rolling(10).min()
rng10 = (hi10 - lo10) / C
rng_prev = (H.shift(10).rolling(20).max() - L.shift(10).rolling(20).min()) / C
contraction = (rng10 <= 0.10) & (rng10 <= 0.6 * rng_prev)
vol_dry = V.rolling(10).mean() <= 0.8 * V.rolling(50).mean()
liquid = (C * V).rolling(20, min_periods=15).mean() >= 5e7
setup = stock_sec_ok & ema_stack & moderate & prior_move & contraction & vol_dry & liquid
ic = idx.close.reindex(dates)
mkt_on = ic > ic.ewm(span=50, adjust=False).mean()

# ---------------------------------------------------------------- engine
def run(entry="anticipate", exit_mode="target2r", use_mkt=False, max_pos=10, w=0.10, rr=2.0,
        max_stop=0.10, expiry=5):
    dts = dates[dates >= pd.Timestamp(START)]
    di = {d: i for i, d in enumerate(dates)}
    col = {s: j for j, s in enumerate(syms)}
    Ov, Hv, Lv, Cv, E20 = O.values, H.values, L.values, C.values, e20.values
    cash, pos, curve, trades = 1.0, {}, [], []
    orders = {}        # sym -> dict(pivot, stop, exp)  (breakout entry)
    next_open_buys = []  # (sym, stop)                  (anticipation entry)
    exit_next_open = set()

    def close_pos(s, px, d, why):
        nonlocal cash
        p = pos.pop(s); cash += p["sh"] * px * (1 - COST)
        trades.append(dict(sym=s, sector=sec_of[s], entry_date=p["d"], exit_date=d, entry=p["px"], exit=px,
                           stop=p["stop"], target=p.get("tgt"), ret=px * (1 - COST) / (p["px"] * (1 + COST)) - 1, why=why))

    def equity(i):
        return cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())

    def open_pos(s, px, stop, d, eq):
        nonlocal cash
        if len(pos) >= max_pos or s in pos or np.isnan(px) or px <= 0:
            return False
        if stop >= px or (px - stop) / px > max_stop:
            return False
        val = min(w * eq, cash / (1 + COST))
        if val < 0.01 * eq:
            return False
        cash -= val * (1 + COST)
        pos[s] = dict(sh=val / px, px=px, stop=stop, d=d, tgt=px + rr * (px - stop) if exit_mode == "target2r" else None)
        return True

    for d in dts:
        i = di[d]
        eq0 = equity(i - 1) if i > 0 else cash
        # exits at open (trailing signal from yesterday)
        for s in list(exit_next_open):
            if s in pos:
                j = col[s]; px = Ov[i, j] if not np.isnan(Ov[i, j]) else Cv[i - 1, j]
                close_pos(s, px, d, "ema20_trail")
        exit_next_open = set()
        # entries at open (anticipation)
        for s, stop in next_open_buys:
            open_pos(s, Ov[i, col[s]], stop, d, eq0)
        next_open_buys = []
        # breakout buy-stop orders
        for s in list(orders):
            o = orders[s]; j = col[s]
            if s in pos or i > o["exp"]:
                orders.pop(s); continue
            if not np.isnan(Hv[i, j]) and Hv[i, j] >= o["pivot"]:
                px = max(Ov[i, j], o["pivot"]) if not np.isnan(Ov[i, j]) else o["pivot"]
                open_pos(s, px, o["stop"], d, eq0)
                orders.pop(s)
        # intraday stop / target (stop assumed first if both touched)
        for s in list(pos):
            j = col[s]; p = pos[s]
            lo, hi, op = Lv[i, j], Hv[i, j], Ov[i, j]
            if np.isnan(lo):
                continue
            if lo <= p["stop"] and not (p["d"] == d and op > p["stop"] and False):
                close_pos(s, min(op, p["stop"]) if not np.isnan(op) else p["stop"], d, "stop"); continue
            if p["tgt"] is not None and hi >= p["tgt"]:
                close_pos(s, max(op, p["tgt"]) if not np.isnan(op) else p["tgt"], d, "target")
        eq = equity(i)
        curve.append((d, eq, len(pos)))
        # end-of-day signals
        if exit_mode == "ema20_trail":
            for s in pos:
                j = col[s]
                if not np.isnan(Cv[i, j]) and Cv[i, j] < E20[i, j] * 0.99:
                    exit_next_open.add(s)
        # orders cancelled if the setup fails (close below 20 EMA)
        for s in list(orders):
            j = col[s]
            if not np.isnan(Cv[i, j]) and Cv[i, j] < E20[i, j]:
                orders.pop(s)
        if use_mkt and not mkt_on.iat[i]:
            continue
        free = max_pos - len(pos) + len(exit_next_open)
        if free <= 0:
            continue
        row = setup.iloc[i]
        cands = [s for s in row.index[row.fillna(False).values] if s not in pos and s not in orders]
        cands.sort(key=lambda s: -(r63.iat[i, col[s]]))
        for s in cands[:free]:
            j = col[s]
            stop = E20[i, j] * 0.99                       # stop just below the 20 EMA
            if entry == "anticipate":
                next_open_buys.append((s, stop))
            else:
                orders[s] = dict(pivot=hi10.iat[i, j] * 1.001, stop=stop, exp=i + expiry)

    return pd.DataFrame(curve, columns=["date", "equity", "npos"]).set_index("date"), pd.DataFrame(trades)

def stats(e, tr, npos):
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    dd = e / e.cummax() - 1; dr = e.pct_change().dropna()
    o = dict(cagr=e.iloc[-1] ** (1 / yrs) - 1, max_dd=dd.min(), sharpe=dr.mean() / dr.std() * np.sqrt(252), final_x=e.iloc[-1])
    for n in (3, 10):
        s = e[e.index >= e.index[-1] - pd.DateOffset(years=n)]; o[f"cagr_{n}y"] = (s.iloc[-1] / s.iloc[0]) ** (1 / n) - 1
    w, l = tr[tr.ret > 0], tr[tr.ret <= 0]
    hold = (pd.to_datetime(tr.exit_date) - pd.to_datetime(tr.entry_date)).dt.days
    o.update(trades=len(tr), per_year=len(tr) / yrs, win_rate=len(w) / len(tr), avg_win=w.ret.mean(), avg_loss=l.ret.mean(),
             payoff=w.ret.mean() / abs(l.ret.mean()), med_hold_days=float(hold.median()),
             avg_stop_dist=float(((tr.entry - tr.stop) / tr.entry).mean()),
             target_hits=float((tr.why == "target").mean()), stop_hits=float((tr.why == "stop").mean()),
             time_invested=float((npos > 0).mean()), avg_pos=float(npos.mean()))
    return o

if __name__ == "__main__":
    print("setup signals per year:", round(setup.sum().sum() / ((dates[-1] - pd.Timestamp(START)).days / 365.25)))
    variants = {
        "A. As described: buy in contraction, stop <20 EMA, 1:2 target": dict(entry="anticipate", exit_mode="target2r"),
        "B. Buy on breakout of contraction, 1:2 target": dict(entry="breakout", exit_mode="target2r"),
        "C. Buy in contraction, trail 20 EMA (no target)": dict(entry="anticipate", exit_mode="ema20_trail"),
        "D. Buy on breakout, trail 20 EMA (no target)": dict(entry="breakout", exit_mode="ema20_trail"),
    }
    allv = {}
    for k, kw in variants.items():
        allv[k] = kw
        allv[k[:2] + " + market filter" + k[2:]] = dict(kw, use_mkt=True)
    out, eqs = {}, {}
    for k, kw in allv.items():
        ec, tr = run(**kw)
        out[k] = stats(ec.equity, tr, ec.npos); eqs[k] = ec.equity
        tag = k.split(".")[0] + ("_mkt" if kw.get("use_mkt") else "")
        tr.to_csv(os.path.join(OUT, f"trades_{tag}.csv"), index=False)
        o = out[k]
        print(f"{k[:70]:70s} CAGR {o['cagr']*100:5.1f}%  DD {o['max_dd']*100:6.1f}%  Sh {o['sharpe']:.2f}  3y {o['cagr_3y']*100:5.1f}%  "
              f"10y {o['cagr_10y']*100:5.1f}%  tr/yr {o['per_year']:4.0f}  win {o['win_rate']*100:3.0f}%  W {o['avg_win']*100:4.1f}% L {o['avg_loss']*100:5.1f}%  "
              f"hold {o['med_hold_days']:.0f}d  stop {o['avg_stop_dist']*100:.1f}%  tgt {o['target_hits']*100:.0f}%  inv {o['time_invested']*100:.0f}% pos {o['avg_pos']:.1f}")
    pd.DataFrame(eqs).to_csv(os.path.join(OUT, "equity_all.csv"))
    json.dump(out, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=float)
