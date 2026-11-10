"""Candles as entry timing inside momentum leaders: same Nison setups (+confirmation, 200 SMA, market filter) but only for stocks
in the top 20% / top 10% of Nifty 500 by 6-month return. Exits as before."""
exec(open("nison_strategy.py").read().split('if __name__ == "__main__":')[0])
r126 = C / C.shift(126) - 1; pct = r126.where(liq).rank(axis=1, pct=True)
rows = []
for top, lab in ((0.8, "top 20% momentum"), (0.9, "top 10% momentum")):
    sp = SETUP & (pct >= top)
    for ex, en in (("trail20", "trail 20 SMA"), ("t2R", "target 2R"), ("time20", "20 days")):
        a, _, _ = run(exit=ex, setup=sp, tax=False); b, e, tr = run(exit=ex, setup=sp)
        rows.append(dict(version=f"{lab} | {en}", **{k: a[k] for k in ("CAGR", "maxDD", "cagr_first_half", "cagr_second_half", "trades_yr", "win", "avg_trade", "losing_yrs")},
                         CAGR_after_tax=b["CAGR"]))
        print(rows[-1], flush=True)
R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("nison_momentum_summary_5y.csv", index=False)
