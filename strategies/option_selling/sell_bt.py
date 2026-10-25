"""Daily option-selling backtests on NIFTY and BANKNIFTY, Jan 2016 - Oct 2026, NSE F&O bhavcopy (daily OHLC per contract).

Contract: nearest expiry (weekly when it exists; BANKNIFTY weekly ended Nov 2024 -> monthly after).
ATM at the open = strike where |CE open - PE open| is smallest (put-call parity, no index feed needed).
Intraday trades: SELL at the 9:15 open price, BUY back at the close (15:30 close price ~ 15:15-15:25 exit).
Stop-loss per leg: if the day's HIGH reaches entry x (1+SL) the leg is bought back there (+1% slippage). With only daily
bars the order of high/low is unknown, so the stop is assumed hit whenever the high touches it (conservative).
Overnight trades: sell at the close, buy back at the next day's open / close.
Costs per leg round trip: STT 0.1% of sell premium + exchange/SEBI/GST/stamp ~0.08% + Rs 40 brokerage
+ slippage 0.5 pt/side NIFTY, 1 pt/side BANKNIFTY.  Rs figures use today's lot sizes (NIFTY 65, BANKNIFTY 30).
Return on margin: naked straddle/strangle margin ~12% of notional, hedged (iron fly/condor) ~4% of notional, simple sum per year."""
import numpy as np, pandas as pd
D = pd.read_pickle("/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/idxopt.pkl")
D = D[(D.date <= D.exp)]
LOT = {"NIFTY": 65, "BANKNIFTY": 30}; SLIP = {"NIFTY": 0.5, "BANKNIFTY": 1.0}
def leg_cost(sym, prem_in, prem_out):
    return prem_in * 0.0010 + (prem_in + prem_out) * 0.0004 + 47.2 / LOT[sym] + 2 * SLIP[sym]

rows = []
for (sym, dt), g in D.groupby(["sym", "date"]):
    ne = g.exp.min(); g = g[g.exp == ne]
    ce = g[g.typ == "CE"].set_index("k"); pe = g[g.typ == "PE"].set_index("k")
    ks = ce.index.intersection(pe.index)
    ok = ks[(ce.loc[ks, "o"] > 0).values & (pe.loc[ks, "o"] > 0).values & (ce.loc[ks, "vol"] > 0).values & (pe.loc[ks, "vol"] > 0).values]
    if len(ok) < 5: continue
    atm = (ce.loc[ok, "o"] - pe.loc[ok, "o"]).abs().idxmin()
    spot = atm + ce.at[atm, "o"] - pe.at[atm, "o"]                     # synthetic open
    rows.append(dict(sym=sym, date=dt, exp=ne, dte=(ne - dt).days, spot=spot, atm=atm, ce=ce, pe=pe, ks=np.array(sorted(ok))))
print("days:", len(rows))

def near(ks, x): return ks[np.abs(ks - x).argmin()]
def short_leg(sym, q, sl):
    """q: option row (o,h,l,c). returns (pnl_pts, stopped)"""
    e = float(q.o); st = False; ex = float(q.c)
    if sl is not None and q.h >= e * (1 + sl): ex = e * (1 + sl) * 1.01; st = True
    return e - ex - leg_cost(sym, e, ex), st
def long_leg(sym, q):
    e, ex = float(q.o), float(q.c); return ex - e - leg_cost(sym, ex, e)

def run(kind="straddle", sl=None, otm=0.0, wing=None, only_expiry=False, skip_expiry=False):
    out = []
    for r in rows:
        if only_expiry and r["dte"] != 0: continue
        if skip_expiry and r["dte"] == 0: continue
        sym, ce, pe, ks, s = r["sym"], r["ce"], r["pe"], r["ks"], r["spot"]
        kc = r["atm"] if otm == 0 else near(ks, s * (1 + otm)); kp = r["atm"] if otm == 0 else near(ks, s * (1 - otm))
        if kc not in ce.index or kp not in pe.index: continue
        a, sa = short_leg(sym, ce.loc[kc], sl); b, sb = short_leg(sym, pe.loc[kp], sl)
        pnl = a + b; prem = float(ce.at[kc, "o"] + pe.at[kp, "o"]); hedged = False
        if wing:
            wc, wp = near(ks, s * (1 + wing)), near(ks, s * (1 - wing))
            if wc in ce.index and wp in pe.index and ce.at[wc, "o"] > 0 and pe.at[wp, "o"] > 0:
                pnl += long_leg(sym, ce.loc[wc]) + long_leg(sym, pe.loc[wp]); prem -= float(ce.at[wc, "o"] + pe.at[wp, "o"]); hedged = True
            else: continue
        out.append(dict(sym=sym, date=r["date"], dte=r["dte"], spot=s, prem=prem, pnl_pts=pnl, stops=int(sa) + int(sb),
                        pnl_rs=pnl * LOT[sym], pnl_pct_notional=pnl / s * 100, margin_pct=4.0 if hedged else 12.0))
    return pd.DataFrame(out)

def run_overnight(exit_at="o"):
    out = []; by = {}
    for r in rows: by.setdefault(r["sym"], []).append(r)
    for sym, rs in by.items():
        for r0, r1 in zip(rs[:-1], rs[1:]):
            ce, pe = r0["ce"], r0["pe"]; ks = r0["ks"]
            if r0["dte"] == 0: continue                                       # don't carry an expiring contract
            closes = (ce.loc[ks, "c"] - pe.loc[ks, "c"]).abs(); k = closes.idxmin()
            c1, p1 = r1["ce"], r1["pe"]
            if r1["exp"] != r0["exp"] or k not in c1.index or k not in p1.index: continue
            e = float(ce.at[k, "c"] + pe.at[k, "c"]); x = float(c1.at[k, exit_at] + p1.at[k, exit_at])
            if x <= 0: continue
            pnl = e - x - leg_cost(sym, ce.at[k, "c"], c1.at[k, exit_at]) - leg_cost(sym, pe.at[k, "c"], p1.at[k, exit_at])
            s = k + ce.at[k, "c"] - pe.at[k, "c"]
            out.append(dict(sym=sym, date=r1["date"], dte=r1["dte"], spot=s, prem=e, pnl_pts=pnl, stops=0, pnl_rs=pnl * LOT[sym],
                            pnl_pct_notional=pnl / s * 100, margin_pct=12.0))
    return pd.DataFrame(out)

def summ(t, name):
    res = []
    for sym, g in t.groupby("sym"):
        g = g.sort_values("date"); yrs = (g.date.iloc[-1] - g.date.iloc[0]).days / 365.25
        eq = g.pnl_rs.cumsum(); rom = (g.pnl_pct_notional / g.margin_pct * 100)       # % return on margin per trade
        yr = rom.groupby(g.date.dt.year).sum()
        l2 = g[g.date >= g.date.iloc[-1] - pd.DateOffset(years=2)]
        res.append(dict(strategy=name, sym=sym, trades=len(g), win=round((g.pnl_pts > 0).mean() * 100, 1), avg_pts=round(g.pnl_pts.mean(), 1),
                        rs_per_lot_total=round(g.pnl_rs.sum()), rs_per_lot_yr=round(g.pnl_rs.sum() / yrs), worst_day_rs=round(g.pnl_rs.min()),
                        max_dd_rs=round((eq - eq.cummax()).min()), ret_on_margin_yr=round(yr.mean(), 1), losing_yrs=int((yr < 0).sum()),
                        last2y_rs=round(l2.pnl_rs.sum()), stop_rate=round(g.stops.mean() / 2 * 100, 1)))
    return res

if __name__ == "__main__":
    V = [("ATM straddle, no SL", dict()), ("ATM straddle, SL 25%/leg", dict(sl=0.25)), ("ATM straddle, SL 30%/leg", dict(sl=0.30)),
         ("ATM straddle, SL 50%/leg", dict(sl=0.50)), ("ATM straddle, SL 100%/leg", dict(sl=1.0)),
         ("Strangle 1% OTM, SL 50%/leg", dict(otm=0.01, sl=0.5)), ("Strangle 2% OTM, SL 50%/leg", dict(otm=0.02, sl=0.5)),
         ("Iron fly (wings 2%), no SL", dict(wing=0.02)), ("Iron fly (wings 2%), SL 30%/leg", dict(wing=0.02, sl=0.30)),
         ("Iron condor 1% short / 3% wings, no SL", dict(otm=0.01, wing=0.03)),
         ("Expiry day only: straddle SL 30%", dict(sl=0.30, only_expiry=True)), ("Expiry day only: straddle no SL", dict(only_expiry=True)),
         ("Non-expiry days: straddle SL 30%", dict(sl=0.30, skip_expiry=True))]
    allr = []; keep = {}
    for name, kw in V:
        t = run(**kw); keep[name] = t; allr += summ(t, name); print(name, "done", flush=True)
    for nm, ex in (("Overnight straddle: sell close, exit next open", "o"), ("Overnight straddle: sell close, exit next close", "c")):
        t = run_overnight(ex); keep[nm] = t; allr += summ(t, nm); print(nm, "done", flush=True)
    R = pd.DataFrame(allr); pd.set_option("display.width", 260); pd.set_option("display.max_rows", 100)
    for sym in ("NIFTY", "BANKNIFTY"): print("\n", sym); print(R[R.sym == sym].drop(columns="sym").to_string(index=False))
    R.to_csv("option_selling_summary.csv", index=False)
    pd.to_pickle(keep, "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/optsell_trades.pkl")
    for nm in keep: keep[nm].assign(strategy=nm)
    pd.concat([v.assign(strategy=k) for k, v in keep.items()]).to_csv("option_selling_trades.csv.gz", index=False, compression="gzip")
