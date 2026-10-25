"""StockMock-style statistics for the 7-hedged-lot plan (base, and with loss limits), plus Nifty-only / Sensex-only books."""
exec(open("loss_limits.py").read().split("V = [")[0])
import pandas as pd, numpy as np
MARGIN = CAP
def stats(s, name):
    s = s[s != 0] if name.endswith("(traded days)") else s
    eq = s.cumsum(); dd = eq - eq.cummax(); mdd = dd.min(); i_mdd = dd.idxmin(); i_peak = eq[:i_mdd].idxmax() if (eq[:i_mdd] > 0).any() else s.index[0]
    rec = eq[i_mdd:][eq[i_mdd:] >= eq[i_peak]]; rec_d = rec.index[0] if len(rec) else None
    w, l = s[s > 0], s[s <= 0]
    def streak(mask):
        best = cur = 0
        for v in mask: cur = cur + 1 if v else 0; best = max(best, cur)
        return best
    M = s.groupby(s.index.to_period("M")).sum(); yrs = (s.index[-1] - s.index[0]).days / 365.25
    ret_yr = s.sum() / yrs
    return {"Overall Profit": f"Rs {s.sum():,.0f} ({s.sum()/MARGIN*100:.0f}%)", "Avg Expiry-Day Profit": f"Rs {s.mean():,.0f} ({s.mean()/MARGIN*100:.2f}%)",
            "Max Profit (day)": f"Rs {s.max():,.0f} ({s.max()/MARGIN*100:.2f}%)", "Max Loss (day)": f"Rs {s.min():,.0f} ({s.min()/MARGIN*100:.2f}%)",
            "Win% (days)": f"{len(w)/len(s)*100:.0f}% ({len(w)})", "Loss% (days)": f"{len(l)/len(s)*100:.0f}% ({len(l)})",
            "Avg Monthly Profit": f"Rs {M.mean():,.0f} ({M.mean()/MARGIN*100:.2f}%)", "Avg Profit On Win Days": f"Rs {w.mean():,.0f} ({w.mean()/MARGIN*100:.2f}%)",
            "Avg Loss On Loss Days": f"Rs {l.mean():,.0f} ({l.mean()/MARGIN*100:.2f}%)", "Max Drawdown (MDD)": f"Rs {mdd:,.0f} ({mdd/MARGIN*100:.2f}%)",
            "MDD Period (Recovery)": f"{i_peak.date()} -> {i_mdd.date()} -> {'recovered ' + str(rec_d.date()) if rec_d is not None else 'running'}",
            "Return to MDD Ratio (yearly)": f"{ret_yr/-mdd:.2f}", "Max Winning Streak": f"{streak(s > 0)} days", "Max Losing Streak": f"{streak(s <= 0)} days",
            "Expectancy (avg win x win% / avg loss x loss%)": f"{(w.mean()*len(w)/len(s)) / (-l.mean()*len(l)/len(s)):.2f}",
            "Reward:Risk (avg win / avg loss)": f"{w.mean()/-l.mean():.2f}", "Losing months": f"{(M<0).sum()} of {len(M)}", "Worst month": f"Rs {M.min():,.0f}"}
books = {}
base = run(); combo = run(day_stop=20000, green=True, dd_resize=30000)
books["7 lots - base"] = base; books["7 lots - with loss limits"] = combo
nifty_days = {p["dt"] for k, p in DAYS if k == "N"}
books["Nifty only (Tue) - with loss limits"] = combo[combo.index.isin(nifty_days)]
books["Sensex only (Thu) - with loss limits"] = combo[~combo.index.isin(nifty_days)]
T = pd.DataFrame({k: stats(v, k) for k, v in books.items()})
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60); print(T.to_string())
with pd.ExcelWriter("stockmock_style_report.xlsx") as xw:
    T.to_excel(xw, sheet_name="Summary")
    for k, s in (("Base", base), ("Loss limits", combo)):
        dw = pd.DataFrame({"year": s.index.year, "day": s.index.day_name().str[:3], "pnl": s.values}).pivot_table(index="year", columns="day", values="pnl", aggfunc="sum").fillna(0)
        dw["Total"] = dw.sum(axis=1); dw.round(0).to_excel(xw, sheet_name=f"Day wise - {k}")
        mo = s.groupby([s.index.year, s.index.month]).sum().unstack().fillna(0); mo.columns = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][:len(mo.columns)]
        mo["Total"] = mo.sum(axis=1)
        ydd = {y: (lambda e: (e - e.cummax()).min())(s[s.index.year == y].cumsum()) for y in mo.index}
        mo["MDD"] = pd.Series(ydd); mo["ROI on 7.5L"] = (mo.Total / CAP * 100).round(0).astype(int).astype(str) + "%"
        mo.round(0).to_excel(xw, sheet_name=f"Monthly - {k}")
        pd.DataFrame({"date": s.index, "day": s.index.day_name(), "index": ["NIFTY" if d in nifty_days else "SENSEX" for d in s.index], "pnl_rs": s.round(0).values,
                      "cumulative": s.cumsum().round(0).values}).to_excel(xw, sheet_name=f"By date - {k}", index=False)
    for k, s in (("Base", base), ("Loss limits", combo)):
        dw = pd.DataFrame({"year": s.index.year, "day": s.index.day_name().str[:3], "pnl": s.values}).pivot_table(index="year", columns="day", values="pnl", aggfunc="sum").fillna(0)
        print(f"\nDay wise - {k}\n", dw.round(0).to_string())
        mo = s.groupby([s.index.year, s.index.month]).sum().unstack().fillna(0); print(f"Monthly - {k}\n", mo.round(0).to_string())
