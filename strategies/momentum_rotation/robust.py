import momentum_rotation as M, pandas as pd, numpy as np
cfgs=[("blend",20,True,"50EMA->cash"),("6M",10,False,"50EMA->cash"),("12-1M",20,True,"50EMA->cash")]
base={k:v.copy() for k,v in M.SC.items()}; e0=M.elig.copy(); f0=M.FLT["50EMA->cash"].copy()
def run(tag):
    for c in cfgs:
        e,tr=M.sim(*c); s=M.stats(e); print(f"{tag:32s} {c[0]:6s} top{c[1]} buf={c[2]}  CAGR {s['CAGR']*100:5.1f}%  DD {s['maxDD']*100:4.0f}%  3y {s['cagr_3y']*100:5.1f}%")
run("base")
for k in M.SC: M.SC[k]=base[k].shift(1)
M.FLT["50EMA->cash"]=f0.shift(1).fillna(True).astype(bool); run("signals lagged 1 day")
for k in M.SC: M.SC[k]=base[k]
M.FLT["50EMA->cash"]=f0
M.elig=e0&(M.turn>5e8); run("liquid only: turnover>50cr")
M.elig=e0&(M.turn>2e9); run("very liquid: turnover>200cr")
