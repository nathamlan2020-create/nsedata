import json, time, io, zipfile, urllib.request, urllib.parse, sys, pandas as pd
from concurrent.futures import ThreadPoolExecutor
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
UA={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
def get(url,tries=5):
    for a in range(tries):
        try: return urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=30).read()
        except Exception as e:
            if '404' in str(e): return None
            time.sleep(2+3*a)
def chart(t,rng,itv):
    b=get(f'https://query2.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t)}?range={rng}&interval={itv}')
    if not b: return None
    r=(json.loads(b).get('chart') or {}).get('result')
    if not r or 'timestamp' not in r[0]: return None
    r=r[0]; q=r['indicators']['quote'][0]
    i=pd.to_datetime(r['timestamp'],unit='s',utc=True).tz_convert('Asia/Kolkata').tz_localize(None)
    d=pd.DataFrame({k:q[k] for k in ('open','high','low','close','volume')},index=i).dropna(subset=['close'])
    return d[~d.index.duplicated(keep='last')]
def add_today(d,m,day):
    d=d.copy(); d.index=d.index.normalize(); mm=m[m.index.normalize()==day] if m is not None else None
    if mm is not None and len(mm) and d.index[-1]<day:
        d.loc[day]=[mm.open.iloc[0],mm.high.max(),mm.low.min(),mm.close.iloc[-1],mm.volume.sum()]
    return d
day=pd.Timestamp.now(tz='Asia/Kolkata').tz_localize(None).normalize() if len(sys.argv)<2 else pd.Timestamp(sys.argv[1])
ni_all=chart('^CRSLDX','5d','1m')
if ni_all is None or not (ni_all.index.normalize()==day).any(): print('MARKET_CLOSED'); raise SystemExit
nidx_d=add_today(chart('^CRSLDX','1y','1d'),ni_all,day)
syms=pd.read_csv(io.BytesIO(get('https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv'))).Symbol.str.strip().tolist()
def one(s):
    m=chart(s+'.NS','5d','1m'); d=chart(s+'.NS','2y','1d')
    if d is not None: d=add_today(d,m,day)
    sig=None
    if d is not None and len(d)>260 and d.index[-1].normalize()==day:
        cl,v=d.close,d.volume; px=cl.iloc[-1]
        if px>cl.iloc[-253:-1].max() and v.iloc[-1]>1.5*v.iloc[-51:-1].mean() and px>cl.iloc[-200:].mean() and (cl*v).iloc[-21:-1].mean()>=5e7:
            sig=dict(symbol=s,close=round(px,2),r3m=round(100*(px/cl.iloc[-64]-1),1))
    if m is not None: m=m[m.index.normalize()==day]; m.insert(0,'symbol',s)
    return m,sig
t0=time.time()
with ThreadPoolExecutor(4) as ex: out=list(ex.map(one,syms))
data=pd.concat([m for m,_ in out if m is not None and len(m)]).reset_index(names='datetime')
data=data[(data.datetime.dt.time>=pd.Timestamp('09:15').time())&(data.datetime.dt.time<pd.Timestamp('15:30').time())]
for c in ('open','high','low','close'): data[c]=data[c].round(2)
data['volume']=data.volume.fillna(0).astype('int64')
sigs=pd.DataFrame([s for _,s in out if s]).sort_values('r3m',ascending=False) if any(s for _,s in out) else pd.DataFrame()
fn=f'nifty500_1min_{day:%Y-%m-%d}'
with zipfile.ZipFile(fn+'.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z: z.writestr(fn+'.csv',data.to_csv(index=False,date_format='%Y-%m-%d %H:%M'))
ni=ni_all[ni_all.index.normalize()==day]
c=nidx_d.close; ema50=c.ewm(span=50,adjust=False).mean().iloc[-1]; up=c.iloc[-1]>ema50
panels=[('NIFTY 500',ni)]+[(r.symbol,data[data.symbol==r.symbol].set_index('datetime')) for r in sigs.head(8).itertuples()]
n=len(panels); cols=1 if n==1 else 2; rows=(n+cols-1)//cols
fig,axs=plt.subplots(rows*2,cols,figsize=(7*cols,3.2*rows),gridspec_kw={'height_ratios':[3,1]*rows},squeeze=False)
for k,(name,d) in enumerate(panels):
    a,v=axs[2*(k//cols),k%cols],axs[2*(k//cols)+1,k%cols]
    if d is None or d.empty: a.set_title(name+' (no data)'); continue
    chg=100*(d.close.iloc[-1]/d.open.iloc[0]-1)
    a.plot(d.index,d.close,lw=1,color='#1f77b4'); a.set_title(f'{name}  {d.close.iloc[-1]:,.2f}  ({chg:+.2f}% today)',fontsize=10)
    vw=(d.close*d.volume).cumsum()/d.volume.cumsum().replace(0,float('nan'))
    if name!='NIFTY 500': a.plot(d.index,vw,lw=0.8,color='#ff7f0e',label='VWAP'); a.legend(fontsize=7,loc='upper left')
    v.bar(d.index,d.volume,width=0.0006,color='#7f7f7f'); v.set_yticks([])
    for x in (a,v): x.tick_params(labelsize=7); x.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%H:%M'))
for k in range(n,rows*cols): axs[2*(k//cols),k%cols].axis('off'); axs[2*(k//cols)+1,k%cols].axis('off')
fig.suptitle(f'{day:%d %b %Y}  |  Nifty 500 {c.iloc[-1]:,.0f} vs 50 EMA {ema50:,.0f}  |  Market filter {"ON" if up else "OFF"}  |  {len(sigs)} breakout signal(s) at close',fontsize=11)
fig.tight_layout(); fig.savefig(fn+'_charts.png',dpi=110)
print(f'DAY {day:%Y-%m-%d} stocks {data.symbol.nunique()} rows {len(data)} took {time.time()-t0:.0f}s nifty {c.iloc[-1]:.1f} ema50 {ema50:.1f} filter {"ON" if up else "OFF"}')
print('SIGNALS', sigs.to_dict('records') if len(sigs) else 'none')
print('FILES', fn+'.zip', fn+'_charts.png')
