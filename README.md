# NSE data

Price data archive for Indian and US stocks. Source: Yahoo Finance, daily OHLCV adjusted for splits and dividends.

## Daily data

- `daily/nse500_daily_2005-2026.zip`: Nifty 500 stocks, 2005 to Oct 2026, one CSV per stock plus the Nifty 500 index (`IDX_CRSLDX.csv`).
- `daily/nse_all/nse_all_daily_max_part1-2.zip`: all NSE mainboard stocks (EQ and BE series; no SME, ETFs or bonds), maximum history Yahoo has, to 19 Oct 2026. About 2,600 stocks. `_manifest.csv` inside lists each file's first date, last date and row count.
- `daily/us/us_daily_2000-2026_part1-4.zip`: about 5,300 NYSE, NASDAQ and AMEX common stocks and ADRs (no warrants, units or preferreds), Jan 2000 to 20 Oct 2026. Used as the closest public proxy for INDmoney's US stock list. `_manifest.csv` is in the last part.
- `daily/indices/`: S&P 500 (`IDX_GSPC`), NASDAQ Composite (`IDX_IXIC`), Nifty 50 (`IDX_NSEI`), Nifty 500 (`IDX_CRSLDX`), Nifty Midcap 50.

Each zip holds plain CSVs with columns `date,open,high,low,close,volume`. Unzip all parts of a set into one folder.

## Intraday data

- `intraday/5min/`: 5-minute bars, last 60 days.
- `intraday/1min/YYYY/MM/`: 1-minute bars and chart image for each trading day.

## Other folders

- `lists/`: ticker lists used for the downloads (`nse_tickers.csv`, `us_tickers.csv`).
- `scripts/download_all.py`: re-download or extend any list (`python download_all.py lists/us_tickers.csv out_dir`). It skips files already present.
- `scripts/bt3pm.py`: 3 PM breakout backtest for any folder of daily CSVs (`python bt3pm.py <stock_dir> <index_csv> <min_turnover> <min_price> <label> <out_dir> [start]`).
- `backtests/`: results of the 3 PM strategy on all NSE stocks and on US stocks (summary and every trade).

## Caveat

All lists are of stocks listed today, so delisted companies are missing (survivorship bias). Yahoo data can contain occasional unadjusted corporate actions.
