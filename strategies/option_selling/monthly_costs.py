"""Month-by-month gross P&L, costs and net for (1) Nifty 3-lot expiry plan and (2) full weekly plan (Nifty 3 lots + Sensex 1 lot + Bank Nifty 1 lot on monthly expiry)."""
import pandas as pd, numpy as np
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"
src = open("sensex_expiry.py").read(); fn = src[src.index("def straddle("):src.index("V = {")]
# ---- Nifty
NS = {}; exec(open("improve.py").read().split("def sim(")[0], NS); NS["STEP"] = 50; exec(fn, NS)
real_cost = NS["cost"]
def run(ns, legs, lot):
    out = {}
    for c in ("net", "gross"):
        ns["cost"] = real_cost_of[id(ns)] if c == "net" else (lambda a, b: 0.0)
        s = {}
        for p in ns["PRE"]:
            r = [ns["straddle"](p, **kw) for kw in legs]
            if all(x is None for x in r): continue
            s[p["dt"]] = sum(x for x in r if x is not None) * lot
        out[c] = pd.Series(s)
    return pd.DataFrame(out)
real_cost_of = {id(NS): real_cost}
D_LEGS = [dict(entry=e, sl=0.40, be=True, reentry=True) for e in ("09:22", "09:35", "10:05")]
nifty = run(NS, D_LEGS, 65)
# ---- Sensex (range-fitted rebuild)
import os; os.environ["SCALE_RANGE"] = "1"
SS = {}; exec(src[:src.index("V = {")], SS); real_cost_of[id(SS)] = SS["cost"]
sensex = run(SS, [dict(entry="10:05")], 20)
# ---- Bank Nifty: real-price bhavcopy version (open->close, 30% SL/leg), monthly expiries only
K = pd.read_pickle(f"{SP}/optsell_trades.pkl")["Expiry day only: straddle SL 30%"]; bn = K[K.sym == "BANKNIFTY"].copy()
bn["m"] = bn.date.dt.to_period("M"); bn = bn[bn.date == bn.groupby("m").date.transform("max")]      # last expiry of each month
# cost per trade from sell_bt leg_cost (approx: 2 legs at open premium, exit ~ half)
bn_cost = (bn.prem * 0.0010 + bn.prem * 1.5 * 0.0004 + 2 * (47.2 / 30 + 2 * 1.0)) * 30
bank = pd.DataFrame({"net": bn.pnl_rs.values, "gross": (bn.pnl_rs + bn_cost).values}, index=bn.date.values)
def grid(df, start):
    df = df[df.index >= start].copy(); df["costs"] = df.gross - df.net
    m = df.groupby(df.index.to_period("M"))[["gross", "costs", "net"]].sum()
    m["trades"] = df.groupby(df.index.to_period("M")).size(); return m
G1 = grid(nifty, "2019-01-01")
comb = pd.concat([nifty.assign(src="Nifty"), sensex.assign(src="Sensex"), bank.assign(src="BankNifty")])
comb = comb[comb.index >= "2023-05-01"]
G2 = comb.groupby([comb.index.to_period("M"), "src"])[["gross", "net"]].sum().unstack(fill_value=0)
G2.columns = [f"{a}_{b}" for a, b in G2.columns]
for s_ in ("Nifty", "Sensex", "BankNifty"): G2[f"costs_{s_}"] = G2[f"gross_{s_}"] - G2[f"net_{s_}"]
G2["gross_total"] = G2[[f"gross_{s_}" for s_ in ("Nifty", "Sensex", "BankNifty")]].sum(axis=1)
G2["net_total"] = G2[[f"net_{s_}" for s_ in ("Nifty", "Sensex", "BankNifty")]].sum(axis=1); G2["costs_total"] = G2.gross_total - G2.net_total
pd.to_pickle(dict(G1=G1, G2=G2), f"{SP}/monthly_costs.pkl")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
print(G1.round(0).to_string()); print(G2[["net_Nifty", "net_Sensex", "net_BankNifty", "gross_total", "costs_total", "net_total"]].round(0).to_string())
print("Nifty yearly:\n", G1.groupby(G1.index.year).sum().round(0).to_string())
print("Plan yearly:\n", G2.groupby(G2.index.year)[["gross_total", "costs_total", "net_total", "net_Nifty", "net_Sensex", "net_BankNifty"]].sum().round(0).to_string())
