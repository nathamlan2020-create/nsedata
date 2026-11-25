import sys, glob, pandas as pd

raw, out = sys.argv[1], sys.argv[2]
frames = []
for f in sorted(glob.glob(f"{raw}/*/DAT_ASCII_XAUUSD_M1_*.csv")):
    d = pd.read_csv(f, sep=";", header=None,
                    names=["dt", "open", "high", "low", "close", "vol"])
    frames.append(d)
df = pd.concat(frames, ignore_index=True)
df["dt"] = pd.to_datetime(df["dt"], format="%Y%m%d %H%M%S")
# HistData: fixed EST (UTC-5), no DST -> IST = +10:30
df["dt_ist"] = df["dt"] + pd.Timedelta(hours=10, minutes=30)
df = df.drop_duplicates("dt").sort_values("dt").reset_index(drop=True)
df = df[["dt_ist", "open", "high", "low", "close"]].rename(columns={"dt_ist": "datetime_ist"})

bad = ((df.high < df[["open", "close"]].max(axis=1)) | (df.low > df[["open", "close"]].min(axis=1))).sum()
print("rows", len(df), "from", df.datetime_ist.iloc[0], "to", df.datetime_ist.iloc[-1], "bad_ohlc", bad)
yr = df.groupby(df.datetime_ist.dt.year).agg(rows=("close", "size"), first=("open", "first"), last=("close", "last"),
                                              hi=("high", "max"), lo=("low", "min"))
print(yr.to_string())
gaps = df.datetime_ist.diff().dt.total_seconds().div(60)
print("gaps>3 days:", (gaps > 3 * 1440).sum())
df.to_pickle(out + ".pkl")
g = df.datetime_ist.diff()
print(df.loc[g > pd.Timedelta(days=3), "datetime_ist"].to_string())
print(g[g > pd.Timedelta(days=3)].to_string())
df.to_csv(out + ".csv", index=False)
