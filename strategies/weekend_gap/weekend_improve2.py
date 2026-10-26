exec(open("weekend_improve.py").read().split("B = T.trend50")[0].replace('T = pd.DataFrame(rows).set_index("fri")', 'T = pd.read_csv("weekend_improve_trades.csv", index_col=0, parse_dates=True)').split("rows = []")[0] + "\nT = pd.read_csv('weekend_improve_trades.csv', index_col=0, parse_dates=True)\nT['strong_close']=np.where(T.dir==1,T.close_pos>0.7,T.close_pos<0.3)\nyrs=(T.index[-1]-T.index[0]).days/365.25\n" + open("weekend_improve.py").read().split("yrs = (T.index[-1] - T.index[0]).days / 365.25")[1].split("B = T.trend50")[0])
B = T.trend50; L = T.dir == 1; S = T.dir == -1; NLW = ~T.long_weekend
V = [rep("BASE: 50-EMA trend filter", B),
     rep("Skip long weekends", B & NLW),
     rep("Longs: 50 EMA | Shorts: also below 200 SMA", (B & L) | (B & S & T.trend200)),
     rep("  + skip long weekends", ((B & L) | (B & S & T.trend200)) & NLW),
     rep("Both sides need 200 SMA + skip long weekends", B & T.trend200 & NLW),
     rep("Longs: 50 EMA | Shorts: 200 SMA + move>0.3%", (B & L) | (B & S & T.trend200 & (T.day_move > 0.3))),
     rep("  + skip long weekends", ((B & L) | (B & S & T.trend200 & (T.day_move > 0.3))) & NLW)]
R = pd.DataFrame(V); pd.set_option("display.width", 260); print(R.to_string(index=False)); R.to_csv("weekend_improve2_summary.csv", index=False)
