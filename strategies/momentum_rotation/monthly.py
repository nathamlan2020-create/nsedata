import momentum_rotation as M, pandas as pd, numpy as np
S=M.SC["blend"]; on=M.FLT["50EMA->cash"]; N=20; COST=M.COST; CAP=500000
cash=CAP; pos={}; was_on=True; rows=[]; log=[]
for t in M.days:
    px=M.Cf.loc[t]; f=bool(on.loc[t]); reb=t in M.first
    if not f and pos:
        for s,(sh,bp) in pos.items(): cash+=sh*px[s]*(1-COST); log.append((t,'SELL',s,px[s]/bp-1,'filter off'))
        pos={}
    if f and (reb or not was_on):
        sc=S.loc[t].where(M.elig.loc[t]).dropna().sort_values(ascending=False); ok=set(sc.index[:2*N])
        for s in [s for s in pos if s not in ok]:
            sh,bp=pos.pop(s); cash+=sh*px[s]*(1-COST); log.append((t,'SELL',s,px[s]/bp-1,'out of top 40'))
        eq=cash+sum(sh*px[s] for s,(sh,bp) in pos.items())
        for s in sc.index[:N]:
            if len(pos)>=N: break
            if s in pos: continue
            amt=min(eq/N,cash)
            if amt<=0: break
            pos[s]=[amt*(1-COST)/px[s],px[s]]; cash-=amt; log.append((t,'BUY',s,np.nan,''))
    was_on=f
    rows.append((t,cash+sum(sh*px[s] for s,(sh,bp) in pos.items()),len(pos),f))
E=pd.DataFrame(rows,columns=['date','value','n','filter']).set_index('date')
L=pd.DataFrame(log,columns=['date','act','sym','ret','why']); L['m']=L.date.dt.to_period('M')
g=E.groupby(E.index.to_period('M'))
mo=pd.DataFrame({'start':g.value.last().shift(1).fillna(CAP),'end':g.value.last(),'stocks_held_at_month_end':g.n.last(),
                 'days_in_cash_pct':(g.n.apply(lambda x:(x==0).mean())*100).round(0)})
mo['return_%']=((mo.end/mo.start-1)*100).round(2); mo['pnl_rs']=(mo.end-mo.start).round(0)
mo['drawdown_%']=((mo.end/mo.end.cummax()-1)*100).round(1)
mo['buys']=L[L.act=='BUY'].groupby('m').size(); mo['sells']=L[L.act=='SELL'].groupby('m').size()
sl=L[L.act=='SELL'].groupby('m'); mo['sells_won']=sl.ret.apply(lambda r:(r>0).sum())
mo[['buys','sells','sells_won']]=mo[['buys','sells','sells_won']].fillna(0).astype(int)
mo['start']=mo.start.round(0); mo['end']=mo.end.round(0); mo.index.name='month'
mo=mo[['start','end','pnl_rs','return_%','drawdown_%','stocks_held_at_month_end','days_in_cash_pct','buys','sells','sells_won']]
mo.to_csv('momentum_monthly_5L.csv')
yr=E.value.resample('YE').last(); y=pd.DataFrame({'end':yr.round(0)}); y['start']=y.end.shift(1).fillna(CAP); y['ret%']=((y.end/y.start-1)*100).round(1)
y['worst_month%']=mo.groupby(mo.index.year)['return_%'].min().values; y['best_month%']=mo.groupby(mo.index.year)['return_%'].max().values
y['months_up']=mo.groupby(mo.index.year)['return_%'].apply(lambda r:f"{(r>0).sum()}/{len(r)}").values
y['trades']=(mo.groupby(mo.index.year).buys.sum()+mo.groupby(mo.index.year).sells.sum()).values
y.index=y.index.year; print(y.to_string())
print('final',round(E.value.iloc[-1]),'CAGR',round(((E.value.iloc[-1]/CAP)**(365.25/(E.index[-1]-E.index[0]).days)-1)*100,1),'maxDD',round((E.value/E.value.cummax()-1).min()*100,1))
print('months',len(mo),'up',(mo['return_%']>0).sum(),'flat(cash)',(mo['days_in_cash_pct']==100).sum())
print(mo.tail(14).to_string())
