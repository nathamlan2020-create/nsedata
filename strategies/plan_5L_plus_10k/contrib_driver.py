import runpy, io, contextlib, pandas as pd, numpy as np
CAP, ADD = 5e5, 1e4
def flows(idx):
    f = pd.Series(0.0, index=idx); firsts = pd.Series(idx, index=idx).groupby(idx.to_period("M")).first()
    f.loc[firsts.values] = ADD; f.iloc[0] = CAP; return f
def xirr(cf, final, end):
    t = np.array([(d - cf.index[0]).days / 365.25 for d in cf.index]); T = (end - cf.index[0]).days / 365.25
    lo, hi = -0.9, 2.0
    for _ in range(200):
        r = (lo + hi) / 2; v = (cf.values * (1 + r) ** (T - t)).sum()
        lo, hi = (r, hi) if v < final else (lo, r)
    return r
def twr_dd(v, f):
    r = (v - f) / v.shift(1) - 1; r.iloc[0] = 0; u = (1 + r).cumprod(); return (u / u.cummax() - 1).min()
def report(name, v, tax=None):
    f = flows(v.index); cf = f[f > 0]
    return dict(strategy=name, invested_L=f.sum() / 1e5, final_L=v.iloc[-1] / 1e5, xirr=xirr(cf, v.iloc[-1], v.index[-1]) * 100,
                maxDD_twr=twr_dd(v, f) * 100, tax_L=(tax.sum() / 1e5 if tax is not None else 0))
rows = []; yearly = {}
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path("mom_contrib.py", run_name="__main__")
for k, lab in (("none", "Momentum, before tax"), ("current", "Momentum, after tax")):
    e, tx = g["res"][k]; rows.append(report(lab, e, tx)); yearly[lab] = e
import pm3_robust as P
r6 = P.C / P.C.shift(126) - 1; P.base_sig = P.base_sig & (r6.rank(axis=1, pct=True) >= 0.80)
with contextlib.redirect_stdout(io.StringIO()):
    g2 = runpy.run_path("pm3_contrib.py", run_name="__main__")
for k, lab in (("none", "3 PM breakout, before tax"), ("current", "3 PM breakout, after tax")):
    e = g2["out"][k]; rows.append(report(lab, e)); yearly[lab] = e
# Nifty 500 buy & hold with same contributions, LTCG at the end
ix = P.idx.close; ix = ix[(ix.index >= "2007-01-01")]
f = flows(ix.index); units = (f / ix).cumsum(); v = units * ix
rows.append(report("Nifty 500 index, before tax", v)); yearly["Nifty 500 index"] = v
gain = v.iloc[-1] - f.sum(); v2 = v.copy(); v2.iloc[-1] -= max(gain - 1.25e5, 0) * 0.125 * 1.04
rows.append(report("Nifty 500 index, after tax (sold at end)", v2))
R = pd.DataFrame(rows).round(1); print(R.to_string(index=False))
Y = pd.DataFrame({k: v.resample("YE").last() / 1e5 for k, v in yearly.items()}).round(1)
inv = flows(ix.index).cumsum().resample("YE").last() / 1e5
Y.insert(0, "invested", inv.round(1).values[:len(Y)]); Y.index = Y.index.year; print(Y.to_string())
R.to_csv("contrib_summary.csv", index=False); Y.to_csv("contrib_yearly.csv")
