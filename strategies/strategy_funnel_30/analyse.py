"""Funnel filters, per-family walk-forward, and the 4-layer system (base signal -> risk sizing -> uncorrelated mix -> HMM regime)."""
import numpy as np, pandas as pd, warnings
from hmmlearn.hmm import GaussianHMM
warnings.filterwarnings("ignore")
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"
A = pd.read_csv("all_backtests.csv.gz"); R = pd.read_pickle(f"{SP}/funnel_returns.pkl"); RAW = pd.read_pickle(f"{SP}/funnel_data.pkl")
LIQ = 0.06 / 252; pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
S = A[A.family != "buy_hold"].copy()
# ---------------- funnel ----------------
slow = S.family.isin(["trend", "momentum"])
f1 = np.where(slow, (S.trades >= 10) & (S.invested >= 0.15), S.trades >= 30)
f2 = f1 & (S.is_sharpe >= 0.40) & (S.is_dd > -0.25)
f3 = f2 & (S.oos_sharpe >= 0.30) & (S.oos_sharpe >= 0.4 * S.is_sharpe) & (S.oos_dd > -0.30)
nb = S.groupby(["asset", "rule"]).sharpe.transform(lambda x: (x >= 0.20).mean())
f4 = f3 & (S.sharpe_cost2 >= 0.25) & (S.sharpe_lag1 >= 0.20) & (nb >= 0.5) & (S.yrs_beat_cash >= 0.55)
S["F1"], S["F2"], S["F3"], S["F4"] = f1, f2, f3, f4
F = S.groupby("family")[["F1", "F2", "F3", "F4"]].sum(); F.insert(0, "tested", S.groupby("family").size())
F.loc["TOTAL"] = F.sum(); F["pass_%"] = (F.F4 / F.tested * 100).round(1)
print("FUNNEL\n", F.to_string()); F.to_csv("funnel_counts.csv")
surv = S[S.F4].sort_values("sharpe", ascending=False)
surv.to_csv("survivors.csv", index=False)
cols = ["asset", "family", "strategy", "trades", "invested", "sharpe", "cagr", "dd", "is_sharpe", "oos_sharpe", "oos_cagr", "oos_dd"]
print("\nTOP SURVIVORS\n", surv[cols].head(25).round(2).to_string(index=False))
print("\nsurvivors per asset\n", surv.groupby("asset").size().sort_values(ascending=False).to_string())
print("\nsurvivors by rule\n", surv.groupby(["family", "rule"]).size().to_string())
BH = A[A.family == "buy_hold"].set_index("asset")[["sharpe", "cagr", "dd", "oos_sharpe", "oos_cagr"]]
# ---------------- walk-forward by family ----------------
keys = pd.DataFrame(list(R.columns), columns=["asset", "family", "strategy"])
years = range(2016, 2027); WF = {}; pick_log = []
for fam in ["mean_reversion", "trend", "momentum", "volatility"]:
    pieces = []
    for y in years:
        tr = R[(R.index >= f"{y-5}-01-01") & (R.index < f"{y}-01-01")]; te = R[(R.index >= f"{y}-01-01") & (R.index < f"{y+1}-01-01")]
        if te.empty: continue
        sh = (tr.mean() - LIQ) / tr.std() * np.sqrt(252)
        cols_y = []
        for a in keys.asset.unique():
            c = [k for k in R.columns if k[0] == a and k[1] == fam]; best = sh[c].idxmax(); cols_y.append(best)
            pick_log.append(dict(year=y, family=fam, asset=a, strategy=best[2], train_sharpe=round(sh[best], 2)))
        pieces.append(te[cols_y].mean(axis=1))                          # equal capital in 30 sleeves
    WF[fam] = pd.concat(pieces)
WF = pd.DataFrame(WF); pd.DataFrame(pick_log).to_csv("walkforward_picks.csv", index=False)
nifty = RAW["Nifty 500"].Close; nb_r = nifty.pct_change().reindex(WF.index).fillna(0)
def st(r):
    e = (1 + r).cumprod(); yrs = len(r) / 252; v = r.std() * np.sqrt(252)
    yr = (1 + r).groupby(r.index.year).prod() - 1
    return dict(CAGR=round((e.iloc[-1] ** (1 / yrs) - 1) * 100, 1), vol=round(v * 100, 1), sharpe=round((r.mean() - LIQ) / r.std() * np.sqrt(252), 2),
                maxDD=round((e / e.cummax() - 1).min() * 100, 1), worst_yr=round(yr.min() * 100, 1), losing_yrs=int((yr < 0).sum()))
W = pd.DataFrame({k: st(WF[k]) for k in WF} | {"Nifty 500 buy & hold": st(nb_r)}).T
print("\nWALK-FORWARD 2016-2026 (each family, 30 equal sleeves, params re-picked yearly on prior 5y)\n", W.to_string())
print("\nfamily correlation\n", WF.corr().round(2).to_string())
# ---------------- layers ----------------
L = {}
L["L1 base: mean reversion (walk-forward)"] = WF.mean_reversion
def voltgt(r, tgt=0.12, cap=3.0):                                    # risk sizing: scale to target vol (lagged 60d), max 3x of sleeve exposure
    v = r.rolling(60, min_periods=20).std().shift(1) * np.sqrt(252); w = (tgt / v).clip(upper=cap).fillna(1)
    ex = r - LIQ                                                      # scale the excess-over-cash part only
    return LIQ + w * ex, w
L["L2 + volatility-target sizing (12%)"], w_mr = voltgt(WF.mean_reversion)
iv = 1 / WF.rolling(252, min_periods=60).std().shift(1); wts = iv.div(iv.sum(axis=1), axis=0).fillna(0.25)
mix = (WF * wts).sum(axis=1)
L["L3 + uncorrelated mix (inverse-vol 4 families)"], _ = voltgt(mix)
# HMM regime on Nifty 500 daily returns: refit each Jan on all prior data, forward-filter only (no look-ahead)
nr = nifty.pct_change().dropna(); feat = pd.concat([nr, nr.rolling(10).std()], axis=1).dropna(); feat.columns = ["r", "v"]
prob_hi = pd.Series(np.nan, index=WF.index)
for y in years:
    tr = feat[feat.index < f"{y}-01-01"]; te = feat[(feat.index >= f"{y}-01-01") & (feat.index < f"{y+1}-01-01")]
    if te.empty: continue
    m = GaussianHMM(n_components=2, covariance_type="full", n_iter=200, random_state=7).fit(tr.values * 100)
    hi = int(np.argmax([m.covars_[k][0, 0] for k in range(2)]))
    alpha = np.full(2, 0.5); out = []
    full = pd.concat([tr.tail(250), te]).values * 100
    from scipy.stats import multivariate_normal as mvn
    for i, x in enumerate(full):
        lik = np.array([mvn.pdf(x, m.means_[k], m.covars_[k]) for k in range(2)])
        alpha = (alpha @ m.transmat_) * lik; alpha /= alpha.sum(); out.append(alpha[hi])
    prob_hi.loc[te.index.intersection(prob_hi.index)] = pd.Series(out[-len(te):], index=te.index).reindex(te.index.intersection(prob_hi.index)).values
reg = (prob_hi.shift(1) > 0.5).astype(float)                         # yesterday's regime decides today's mix
calm_mix = (0.5 * WF.trend + 0.5 * WF.momentum); hv_mix = WF.mean_reversion
L["L4 + HMM regime switch (calm: trend+mom, stressed: mean rev)"], _ = voltgt(reg * hv_mix + (1 - reg) * calm_mix)
L["Regime switch without vol sizing"] = reg * hv_mix + (1 - reg) * calm_mix
L["Nifty 500 buy & hold"] = nb_r
mom = pd.read_csv(f"{SP}/mrot/lab_n500_equity.csv.gz", index_col=0, parse_dates=True)["YOUR MODEL: blend top 20, keep 40, daily 50 EMA"]
L["Your momentum model (pre-tax)"] = mom.pct_change().reindex(WF.index).fillna(0)
LY = pd.DataFrame({k: st(v) for k, v in L.items()}).T
LY["time_in_stressed_regime_%"] = ""; LY.loc[LY.index.str.startswith("L4"), "time_in_stressed_regime_%"] = str(round(reg.mean() * 100))
print("\nLAYERED SYSTEM 2016-2026 (all out-of-sample)\n", LY.to_string()); LY.to_csv("layers_summary.csv")
W.to_csv("walkforward_family.csv"); pd.DataFrame(L).to_csv("layers_daily_returns.csv.gz")
yr = pd.DataFrame({k: (1 + v).groupby(v.index.year).prod() - 1 for k, v in L.items()}) * 100
print("\nyearly %\n", yr.round(1).to_string()); yr.round(1).to_csv("layers_yearly.csv")
print("\nBuy & hold per asset\n", BH.round(2).to_string())
