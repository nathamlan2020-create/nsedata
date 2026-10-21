import glob, pandas as pd, sheet_strats as S
from multiprocessing import Pool
V = [("MST as sheet", "m", dict()), ("MST + market filter", "m", dict(mkt=True)), ("MST no RS21 exit", "m", dict(rs_exit=False)),
     ("MST no RS21 exit + market filter", "m", dict(rs_exit=False, mkt=True)),
     ("LST full entry as sheet", "l", dict(pyramid=False)), ("LST full + market filter", "l", dict(pyramid=False, mkt=True)),
     ("LST full, no RS55 exit", "l", dict(pyramid=False, rs_exit=False)), ("LST full, no RS55 exit + market filter", "l", dict(pyramid=False, rs_exit=False, mkt=True)),
     ("LST pyramid, no RS55 exit + market filter", "l", dict(pyramid=True, rs_exit=False, mkt=True))]
def job(f):
    X = S.prep(f)
    if X is None: return {}
    return {n: (S.sim_mst(X, **kw) if k == "m" else S.sim_lst(X, **kw)) for n, k, kw in V}
if __name__ == "__main__":
    with Pool(2) as p: res = p.map(job, sorted(glob.glob(f"{S.D}/*.NS.csv")), chunksize=8)
    rows = []
    for n, k, kw in V:
        T = pd.DataFrame([t for r in res for t in r.get(n, [])]); X = T[T.t_in >= "2007-01-01"]
        T.to_csv(f"var_{n.replace(' ','_').replace('+','plus').replace(',','')}.csv.gz", index=False)
        for tax in (False, True):
            s, cv = S.portfolio(T, 10 if k == "m" else 5, tax)
            rows.append(dict(variant=n + (" | after tax" if tax else ""), trades=len(X), win=f"{(X.ret>0).mean()*100:.0f}%", avg=f"{X.ret.mean()*100:+.2f}%",
                             med_days=int(X.days.median()), CAGR=f"{s['CAGR']*100:+.1f}%", maxDD=f"{s['maxDD']*100:.0f}%", last3y=f"{s['cagr_3y']*100:+.1f}%",
                             losing_yrs=s["losing_yrs"], x5L=f"₹{s['final']*5:.1f} L"))
    R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.to_string(index=False)); R.to_csv("variants_summary.csv", index=False)
