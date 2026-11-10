"""'Nison pullback' strategy on Nifty 500, last 5 years (18 Oct 2021 - Oct 2026), Rs 5 lakh, 0.15%/side, tax computed.
Setup  : Hammer / Bullish harami / Dragonfly doji after a short decline (Nison trend rule), stock above its 200 SMA,
Confirm: next day closes above the pattern-day high -> buy at that close (3 PM-style).
Market : only when Nifty 500 > 50 EMA.  Max 10 positions x 10% equity; rank same-day signals by 63-day return.
Stop   : low of the pattern day (intraday). Exits tested: fixed 10 / 20 days, target 2R, trail close < 20 SMA, 3R target + 20 SMA trail."""
exec(open("patterns_event.py").read().split("FWD = {")[0])
COST = 0.0015; CAP = 5e5
ic = idx.close.reindex(dates).ffill(); MKT = (ic > ic.ewm(span=50, adjust=False).mean()).values
SETUP = (P["Hammer"] | P["Bullish harami"] | P["Dragonfly / doji in downtrend"]).fillna(False) & (C > sma200) & liq
mom63 = C / C.shift(63) - 1
def fy(t): return t.year + 1 if t.month >= 4 else t.year
def run(exit="time10", maxpos=10, use_mkt=True, tax=True, setup=SETUP, start=START):
    syms = list(C.columns); col = {s: j for j, s in enumerate(syms)}
    Ov, Hv, Lv, Cv, S20, M63 = O.values, H.values, L.values, C.values, sma20.values, mom63.values
    SG = setup.values; di = {d: i for i, d in enumerate(dates)}
    cash = CAP; pos = {}; vals = []; trades = []; st = lt = cfs = cfl = 0.0; cur = None
    days = dates[dates >= start]
    for t in days:
        i = di[t]
        if cur is None: cur = fy(t)
        if tax and fy(t) != cur:
            S_, L_ = st + cfs, lt + cfl
            if S_ < 0 and L_ > 0: L_ += S_; S_ = 0
            cfs, cfl = min(S_, 0), min(L_, 0); cash -= (max(S_, 0) * 0.20 + max(max(L_, 0) - 125000, 0) * 0.125) * 1.04; st = lt = 0.0; cur = fy(t)
        def sell(s, px, why):
            nonlocal cash, st, lt
            p = pos.pop(s); pr = p["sh"] * px * (1 - COST); cash += pr; g = pr - p["cost"]
            if (t - p["d"]).days >= 365: lt += g
            else: st += g
            trades.append(dict(sym=s, entry=p["d"], exit=t, ret=pr / p["cost"] - 1, why=why, days=i - p["i"]))
        for s in list(pos):
            j = col[s]; p = pos[s]
            if np.isnan(Cv[i, j]): continue
            if Lv[i, j] <= p["sl"]: sell(s, min(Ov[i, j], p["sl"]) if not np.isnan(Ov[i, j]) else p["sl"], "stop"); continue
            R = p["px"] - p["sl"]
            if exit in ("t2R", "t3R_trail") and Hv[i, j] >= p["px"] + (2 if exit == "t2R" else 3) * R:
                sell(s, max(Ov[i, j], p["px"] + (2 if exit == "t2R" else 3) * R), "target"); continue
            n = i - p["i"]
            if exit == "time10" and n >= 10: sell(s, Cv[i, j], "time")
            elif exit == "time20" and n >= 20: sell(s, Cv[i, j], "time")
            elif exit == "t2R" and n >= 20: sell(s, Cv[i, j], "time")
            elif exit in ("trail20", "t3R_trail") and n >= 2 and Cv[i, j] < S20[i, j]: sell(s, Cv[i, j], "trail")
        eq = cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items())
        # confirmation today for a setup yesterday -> buy at today's close
        if (MKT[i] or not use_mkt) and len(pos) < maxpos and i >= 1:
            c = [syms[j] for j in np.flatnonzero(SG[i - 1]) if syms[j] not in pos and Cv[i, j] > Hv[i - 1, j]]
            c.sort(key=lambda s: -(M63[i, col[s]] if not np.isnan(M63[i, col[s]]) else -9))
            for s in c[: maxpos - len(pos)]:
                j = col[s]; px = Cv[i, j]; sl = Lv[i - 1, j]
                if px <= sl: continue
                amt = min(eq / maxpos, cash)
                if amt < 0.02 * eq: break
                cash -= amt; pos[s] = dict(sh=amt * (1 - COST) / px, cost=amt, px=px, sl=sl, d=t, i=i)
        vals.append(cash + sum(p["sh"] * (Cv[i, col[s]] if not np.isnan(Cv[i, col[s]]) else p["px"]) for s, p in pos.items()))
    e = pd.Series(vals, index=days); tr = pd.DataFrame(trades); yrs = (e.index[-1] - e.index[0]).days / 365.25
    yr = e.resample("YE").last(); yret = yr.pct_change(); yret.iloc[0] = yr.iloc[0] / CAP - 1
    h = e[e.index < "2024-04-01"]; h2 = e[e.index >= "2024-04-01"]
    return dict(CAGR=round(((e.iloc[-1] / CAP) ** (1 / yrs) - 1) * 100, 1), maxDD=round((e / e.cummax() - 1).min() * 100, 1),
                cagr_first_half=round(((h.iloc[-1] / h.iloc[0]) ** (365.25 / (h.index[-1] - h.index[0]).days) - 1) * 100, 1),
                cagr_second_half=round(((h2.iloc[-1] / h2.iloc[0]) ** (365.25 / (h2.index[-1] - h2.index[0]).days) - 1) * 100, 1),
                trades_yr=round(len(tr) / yrs), win=round((tr.ret > 0).mean() * 100, 1), avg_trade=round(tr.ret.mean() * 100, 2),
                avg_days=round(tr.days.mean(), 1), losing_yrs=int((yret < 0).sum()), final_L=round(e.iloc[-1] / 1e5, 1)), e, tr
if __name__ == "__main__":
    rows = []; curves = {}
    V = [("Exit after 10 days", dict(exit="time10")), ("Exit after 20 days", dict(exit="time20")), ("Target 2R (max 20 days)", dict(exit="t2R")),
         ("Trail: close < 20 SMA", dict(exit="trail20")), ("Target 3R + trail 20 SMA", dict(exit="t3R_trail")),
         ("Trail 20 SMA, no market filter", dict(exit="trail20", use_mkt=False)), ("Trail 20 SMA, max 20 positions", dict(exit="trail20", maxpos=20))]
    for name, kw in V:
        a, _, _ = run(**kw, tax=False); b, e, tr = run(**kw); curves[name] = e
        rows.append(dict(exit_rule=name, **{k: a[k] for k in ("CAGR", "maxDD", "cagr_first_half", "cagr_second_half", "trades_yr", "win", "avg_trade", "avg_days", "losing_yrs")},
                         CAGR_after_tax=b["CAGR"], maxDD_after_tax=b["maxDD"], final_after_tax_L=b["final_L"]))
        print(rows[-1], flush=True)
        if name == "Trail: close < 20 SMA": tr.to_csv("nison_trades_trail20.csv", index=False)
    nb = ic[ic.index >= START]; yrs = (nb.index[-1] - nb.index[0]).days / 365.25
    rows.append(dict(exit_rule="Nifty 500 buy & hold (price)", CAGR=round(((nb.iloc[-1] / nb.iloc[0]) ** (1 / yrs) - 1) * 100, 1), maxDD=round((nb / nb.cummax() - 1).min() * 100, 1)))
    R = pd.DataFrame(rows); pd.set_option("display.width", 260); print(R.to_string(index=False)); R.to_csv("nison_strategy_summary_5y.csv", index=False)
    Y = pd.DataFrame({k: v.resample("YE").last() for k, v in curves.items()}); YR = Y.pct_change() * 100; YR.iloc[0] = (Y.iloc[0] / CAP - 1) * 100
    YR.index = YR.index.year; print(YR.round(1).to_string()); YR.round(1).to_csv("nison_yearly_after_tax.csv")
