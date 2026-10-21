import dd_control as D, pandas as pd, momentum_rotation as M
V=[("Current: monthly top 20, keep while top 40",dict(N=20,K=2)),
   ("Monthly top 10, keep while top 20",dict(N=10,K=2)),
   ("DAILY top 10, keep while top 20",dict(N=10,K=2,daily=True)),
   ("DAILY top 10, sell when out of top 10",dict(N=10,K=1,daily=True)),
   ("DAILY top 10, keep while top 15",dict(N=10,K=1.5,daily=True)),
   ("DAILY top 20, keep while top 40",dict(N=20,K=2,daily=True))]
rows=[]
for n,kw in V:
    import time; t0=time.time()
    # count trades
    a,ea=D.sim(**kw,tax=False); b,eb=D.sim(**kw,tax=True)
    rows.append(dict(variant=n,CAGR=round(a['CAGR']*100,1),maxDD=round(a['maxDD']*100,1),CAGR_after_tax=round(b['CAGR']*100,1),
        maxDD_after_tax=round(b['maxDD']*100,1),last3y_at=round(b['last3y']*100,1),worst_year_at=round(b['worst_yr']*100,1),losing_yrs=b['losing'],final_at_L=round(b['final']/1e5,1)))
    print(n,'done',round(time.time()-t0),'s',flush=True)
R=pd.DataFrame(rows); pd.set_option('display.width',250); print(R.to_string(index=False)); R.to_csv('daily_top10_summary.csv',index=False)
