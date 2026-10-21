import momentum_rotation as M, pandas as pd, numpy as np
e = pd.read_csv("momentum_monthly_20L_aftertax.csv", index_col=0)
S=M.SC["blend"]; on=M.FLT["50EMA->cash"]
# for each rebalance/buy day: size of one position (after-tax equity/20) vs each top-20 stock's avg daily turnover
eq = pd.Series(e.end_after_tax.values, index=pd.PeriodIndex(e.index, freq="M"))
rows=[]
for t in M.first:
    t=pd.Timestamp(t)
    if not on.loc[t]: continue
    sc=S.loc[t].where(M.elig.loc[t]).dropna().sort_values(ascending=False).index[:20]
    p=eq.get(t.to_period("M")-1, 2e6)/20
    tv=M.turn.loc[t, sc]
    rows.append(dict(month=str(t.date())[:7], pos_size_L=p/1e5, median_turnover_cr=tv.median()/1e7, pct_of_daily_turnover=(p/tv).median()*100,
                     stocks_over_5pct=(p/tv>0.05).sum()))
R=pd.DataFrame(rows); R["year"]=R.month.str[:4]
print(R.groupby("year").agg(pos_size_L=("pos_size_L","mean"), med_turnover_cr=("median_turnover_cr","median"),
      pct_of_daily_turnover=("pct_of_daily_turnover","median"), stocks_over_5pct=("stocks_over_5pct","mean")).round(1).to_string())
