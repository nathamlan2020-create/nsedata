"""
5 EMA trend-reversal intraday backtest (Kiran Bala style), 60-min and 30-min bars.
Short setup: an "alert" candle closes entirely above the 5 EMA (its low > EMA). If a later candle
  breaks below the alert candle's low, go short there; stop = alert candle high.
  While no entry has triggered, each new candle fully above the EMA becomes the new alert candle.
Long setup: mirror image (alert candle entirely below the 5 EMA, buy on break of its high, stop at its low).
Exits: fixed target (1:2 or 1:3) or trail (exit at the close of the first candle that closes back
  across the 5 EMA), always squared off at the day's last candle close. No new entries in the last candle.
Stop is assumed to hit first if a candle touches both stop and target.
Usage: python ema5.py <intra_dir> <interval>
"""
import sys, glob, os
import numpy as np
import pandas as pd

D, IV = sys.argv[1], sys.argv[2]

def trades_for(df, exit_mode="t3", cost=0.0005, side="both", same_bar="stop"):
    df = df.copy()
    df["ema"] = df.close.ewm(span=5, adjust=False).mean()
    df["day"] = df.index.date
    last_of_day = df.groupby("day").tail(1).index
    is_last = df.index.isin(last_of_day)
    o, h, l, c, e = (df[k].values for k in ("open", "high", "low", "close", "ema"))
    out, pos, alert_s, alert_l = [], None, None, None
    for i in range(1, len(df)):
        # manage open position
        if pos is not None:
            done = None
            if pos["dir"] == 1:
                if l[i] <= pos["stop"]:
                    done = (min(o[i], pos["stop"]) if i > pos["i"] else pos["stop"], "stop")
                elif exit_mode != "trail" and h[i] >= pos["tgt"]:
                    done = (max(o[i], pos["tgt"]) if i > pos["i"] else pos["tgt"], "target")
                elif exit_mode == "trail" and i > pos["i"] and c[i] < e[i]:
                    done = (c[i], "trail")
            else:
                if h[i] >= pos["stop"]:
                    done = (max(o[i], pos["stop"]) if i > pos["i"] else pos["stop"], "stop")
                elif exit_mode != "trail" and l[i] <= pos["tgt"]:
                    done = (min(o[i], pos["tgt"]) if i > pos["i"] else pos["tgt"], "target")
                elif exit_mode == "trail" and i > pos["i"] and c[i] > e[i]:
                    done = (c[i], "trail")
            if done is None and is_last[i]:
                done = (c[i], "eod")
            if done is not None:
                px, why = done
                risk = abs(pos["px"] - pos["stop0"])
                R = pos["dir"] * (px - pos["px"]) / risk - 2 * cost * pos["px"] / risk
                out.append(dict(t_in=df.index[pos["i"]], t_out=df.index[i], dir=pos["dir"], entry=pos["px"],
                                exit=px, R=R, why=why, ret=pos["dir"] * (px / pos["px"] - 1) - 2 * cost))
                pos = None
                alert_s = alert_l = None
            if pos is not None:
                continue
        # new entries (not on the day's last candle; alerts must be from the same day)
        if alert_s is not None and df["day"].iat[alert_s] != df["day"].iat[i]:
            alert_s = None
        if alert_l is not None and df["day"].iat[alert_l] != df["day"].iat[i]:
            alert_l = None
        if not is_last[i]:
            if side in ("both", "short") and alert_s is not None and l[i] < l[alert_s]:
                entry = min(o[i], l[alert_s]); stop = h[alert_s]
                if stop > entry:
                    pos = dict(dir=-1, px=entry, stop=stop, stop0=stop, i=i, tgt=entry - (3 if exit_mode == "t3" else 2) * (stop - entry))
            elif side in ("both", "long") and alert_l is not None and h[i] > h[alert_l]:
                entry = max(o[i], h[alert_l]); stop = l[alert_l]
                if entry > stop:
                    pos = dict(dir=1, px=entry, stop=stop, stop0=stop, i=i, tgt=entry + (3 if exit_mode == "t3" else 2) * (entry - stop))
            if pos is not None and same_bar == "stop":
                # same-candle stop check
                if (pos["dir"] == 1 and l[i] <= pos["stop"]) or (pos["dir"] == -1 and h[i] >= pos["stop"]):
                    risk = abs(pos["px"] - pos["stop0"])
                    out.append(dict(t_in=df.index[i], t_out=df.index[i], dir=pos["dir"], entry=pos["px"], exit=pos["stop"],
                                    R=-1 - 2 * cost * pos["px"] / risk, why="stop_same_bar", ret=-risk / pos["px"] - 2 * cost))
                    pos = None
                continue
        # update alert candles (candle fully above / below the 5 EMA)
        if l[i] > e[i]:
            alert_s = i
        if h[i] < e[i]:
            alert_l = i
    return pd.DataFrame(out)

def summarize(tr, risk=0.01, label=""):
    tr = tr.sort_values("t_out")
    eq = (1 + risk * tr.R.clip(lower=-3)).cumprod()            # 1% of capital risked per trade
    days = (tr.t_out.max() - tr.t_in.min()).days / 365.25
    dd = (eq / eq.cummax() - 1).min()
    return dict(label=label, trades=len(tr), per_day=len(tr) / (days * 248), win=(tr.R > 0).mean(), avgR=tr.R.mean(),
                avg_winR=tr.R[tr.R > 0].mean(), total_R=tr.R.sum(), cagr=eq.iloc[-1] ** (1 / days) - 1, max_dd=dd,
                long_R=tr.R[tr.dir == 1].mean(), short_R=tr.R[tr.dir == -1].mean())

if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(D, f"*_{IV}.csv")))
    data = {os.path.basename(f).replace(f"_{IV}.csv", ""): pd.read_csv(f, index_col=0, parse_dates=True) for f in files}
    rows = []
    for mode, mlab in (("t3", "1:3 target"), ("t2", "1:2 target"), ("trail", "trail on 5 EMA")):
        for grp, keys, cost in (("Nifty 50 index", ["IDX_NSEI"], 0.0003), ("Bank Nifty index", ["IDX_NSEBANK"], 0.0003),
                                ("Nifty 50 stocks", [k for k in data if not k.startswith("IDX")], 0.0005)):
            tr = pd.concat([trades_for(data[k], mode, cost).assign(sym=k) for k in keys if k in data])
            s = summarize(tr, label=f"{IV} {grp} | {mlab}")
            if grp == "Nifty 50 stocks":       # 50 instruments: risk 0.2% each so total risk is comparable
                s = summarize(tr, risk=0.002, label=f"{IV} {grp} | {mlab}")
            rows.append(s)
            if mode == "t3" and grp == "Nifty 50 index":
                tr.to_csv(f"ema5_trades_{IV}_nifty_t3.csv", index=False)
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(res.assign(win=lambda x: (x.win * 100).round(0), cagr=lambda x: (x.cagr * 100).round(1), max_dd=lambda x: (x.max_dd * 100).round(1))
          .round(3).to_string(index=False))
    res.to_csv(f"ema5_summary_{IV}.csv", index=False)
