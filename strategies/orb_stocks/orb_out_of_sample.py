import pandas as pd, numpy as np
T = pd.read_csv("orb_features.csv.gz")
NEW = ["KOTAKBANK","MM","HINDUNILVR","BAJFINANCE","SUNPHARMA","MARUTI","HCLTECH","NTPC","ULTRACEMCO","TITAN"]
L = T.dir == 1; S = ~L
piv = (L & (T.entry > T.P)) | (S & (T.entry < T.P))
idx = pd.bdate_range("2015-03-02", "2026-10-19")
def stats(t, col="ret_tgt2"):
    dly = t.groupby("day")[col].mean(); dly.index = pd.to_datetime(dly.index); dly = dly.reindex(idx).fillna(0)
    eq = (1+dly).cumprod(); yr = dly.groupby(dly.index.year).apply(lambda r: (1+r).prod()-1)
    return f"{len(t):5d} {(t[col]>0).mean()*100:3.0f}% {t[col].mean()*100:+.3f} {t[t.day<'2022'][col].mean()*100:+.3f} {t[t.day>='2022'][col].mean()*100:+.3f} {(eq.iloc[-1]**(1/11.6)-1)*100:+5.1f}% {(eq/eq.cummax()-1).min()*100:4.0f}% {(yr<0).sum()}/12"
print("group / filter                trades win  avg%   15-21  22-26   CAGR   DD  losing yrs")
for g, m in (("OLD 12", ~T.sym.isin(NEW)), ("NEW 10", T.sym.isin(NEW)), ("ALL 22", T.sym==T.sym)):
    for fn, f in (("plain ORB", T.orv==T.orv), ("orv>2", T.orv>2), ("orv>2+pivot", (T.orv>2)&piv), ("orv>2.5+pivot", (T.orv>2.5)&piv)):
        print(f"{g:7s} {fn:20s} {stats(T[m & f])}")
print("\nNEW 10, orv>2+pivot by stock:")
t = T[T.sym.isin(NEW) & (T.orv>2) & piv]
print(t.groupby("sym").ret_tgt2.agg(["count","mean"]).assign(mean=lambda d: (d["mean"]*100).round(3)).sort_values("mean").to_string())
t = T[T.sym.isin(NEW) & (T.orv>2) & piv]
dly = t.groupby("day").ret_tgt2.mean(); dly.index=pd.to_datetime(dly.index); dly=dly.reindex(idx).fillna(0)
print("\nNEW 10 yearly %:", (dly.groupby(dly.index.year).apply(lambda r:(1+r).prod()-1)*100).round(0).astype(int).to_dict())
