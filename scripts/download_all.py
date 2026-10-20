"""Download maximum daily OHLCV history from Yahoo Finance for a ticker list.
Usage: python download_all.py <tickers.csv with 'yahoo' column> <out_dir> [batch]
Writes one CSV per ticker (date, open, high, low, close, volume; split/dividend adjusted)
and a manifest.csv with first/last date and row count. Resumable: skips tickers already saved.
"""
import sys, os, time
import pandas as pd
import yfinance as yf

src, out = sys.argv[1], sys.argv[2]
batch = int(sys.argv[3]) if len(sys.argv) > 3 else 80
os.makedirs(out, exist_ok=True)
tickers = pd.read_csv(src)["yahoo"].dropna().astype(str).tolist()
fname = lambda t: os.path.join(out, t.replace("^", "IDX_").replace("/", "-") + ".csv")
todo = [t for t in tickers if not os.path.exists(fname(t))]
print(f"{len(tickers)} tickers, {len(todo)} to download", flush=True)

failed = []
for k in range(0, len(todo), batch):
    chunk = todo[k:k + batch]
    for attempt in range(3):
        try:
            df = yf.download(chunk, period="max", interval="1d", auto_adjust=True, group_by="ticker",
                             threads=True, progress=False, timeout=60)
            break
        except Exception as e:
            print("retry", attempt, e, flush=True); time.sleep(10 * (attempt + 1)); df = None
    for t in chunk:
        try:
            d = df[t] if len(chunk) > 1 else df
            d = d.dropna(how="all")
            d = d[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
            if len(d) == 0:
                failed.append(t); continue
            d.columns = ["open", "high", "low", "close", "volume"]
            d.index.name = "date"
            d.round(4).to_csv(fname(t))
        except Exception:
            failed.append(t)
    print(f"{min(k + batch, len(todo))}/{len(todo)} done, failed so far {len(failed)}", flush=True)
    time.sleep(1)

rows = []
for t in tickers:
    p = fname(t)
    if os.path.exists(p):
        d = pd.read_csv(p, usecols=[0])
        rows.append(dict(yahoo=t, first=d.iloc[0, 0], last=d.iloc[-1, 0], rows=len(d)))
pd.DataFrame(rows).to_csv(os.path.join(out, "_manifest.csv"), index=False)
pd.Series(failed, name="yahoo").to_csv(os.path.join(out, "_failed.csv"), index=False)
print("FINISHED saved", len(rows), "failed", len(failed), flush=True)
