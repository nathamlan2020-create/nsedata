"""Steve Nison candlestick patterns on Nifty 500 stocks (clean daily data), last 5 years (Oct 2021 - Oct 2026).
Pattern definitions follow Nison's criteria; reversal patterns need a prior trend (Nison's rule).
Event study: return from next day's OPEN to the close 5/10/20 trading days later, net of 0.3% round-trip cost, vs the average
return of all liquid stock-days in the same period (baseline). Liquid = price > 50 and 20-day turnover > Rs 5 cr."""
import glob, os, numpy as np, pandas as pd
D = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/n500c"
START = pd.Timestamp("2021-10-18"); COST = 0.003
def load(p):
    d = pd.read_csv(p, index_col=0, parse_dates=True); return d[~d.index.duplicated()].sort_index()
idx = load(f"{D}/IDX_CRSLDX.csv"); dates = idx.index[idx.index >= "2020-06-01"]
X = {k: {} for k in ("open", "high", "low", "close", "volume")}
for f in glob.glob(f"{D}/*.NS.csv"):
    s = os.path.basename(f)[:-7]; d = load(f); d = d[d.close > 0].reindex(dates)
    for k in X: X[k][s] = d[k]
O, H, L, C, V = (pd.DataFrame(X[k]) for k in ("open", "high", "low", "close", "volume"))
body = (C - O).abs(); rng = (H - L).replace(0, np.nan); up = C > O; dn = C < O
uppsh = H - np.maximum(O, C); lowsh = np.minimum(O, C) - L
avgbody = body.rolling(20).mean()
sma20 = C.rolling(20).mean(); sma50 = C.rolling(50).mean(); sma200 = C.rolling(200).mean()
downtrend = (C.shift(1) < sma20.shift(1)) & (C.shift(1) / C.shift(6) - 1 < -0.03)        # prior decline (Nison: reversal needs a trend)
uptrend_prior = (C.shift(1) > sma20.shift(1)) & (C.shift(1) / C.shift(6) - 1 > 0.03)
liq = (C > 50) & ((C * V).rolling(20, min_periods=10).mean() > 5e7)
P = {}
P["Hammer"] = (lowsh >= 2 * body) & (uppsh <= 0.1 * rng) & (body > 0) & downtrend
P["Bullish engulfing"] = dn.shift(1) & up & (O <= C.shift(1)) & (C >= O.shift(1)) & (body > body.shift(1)) & downtrend
P["Piercing line"] = dn.shift(1) & (body.shift(1) > avgbody.shift(1)) & up & (O < L.shift(1)) & (C > (O.shift(1) + C.shift(1)) / 2) & (C < O.shift(1)) & downtrend
P["Morning star"] = dn.shift(2) & (body.shift(2) > avgbody.shift(2)) & (body.shift(1) < 0.3 * body.shift(2)) & \
    (np.maximum(O, C).shift(1) < C.shift(2)) & up & (C > (O.shift(2) + C.shift(2)) / 2) & downtrend.shift(1).fillna(False)
P["Bullish harami"] = dn.shift(1) & (body.shift(1) > avgbody.shift(1)) & up & (O > C.shift(1)) & (C < O.shift(1)) & (body < 0.5 * body.shift(1)) & downtrend
P["Dragonfly / doji in downtrend"] = (body <= 0.1 * rng) & (lowsh >= 0.6 * rng) & downtrend
P["Three white soldiers"] = up & up.shift(1) & up.shift(2) & (C > C.shift(1)) & (C.shift(1) > C.shift(2)) & \
    (O > O.shift(1)) & (O < C.shift(1)) & (O.shift(1) > O.shift(2)) & (O.shift(1) < C.shift(2)) & (uppsh < 0.25 * body) & (body > avgbody)
P["Shooting star (bearish)"] = (uppsh >= 2 * body) & (lowsh <= 0.1 * rng) & (body > 0) & uptrend_prior
P["Hanging man (bearish)"] = (lowsh >= 2 * body) & (uppsh <= 0.1 * rng) & (body > 0) & uptrend_prior
P["Bearish engulfing"] = up.shift(1) & dn & (O >= C.shift(1)) & (C <= O.shift(1)) & (body > body.shift(1)) & uptrend_prior
P["Dark cloud cover"] = up.shift(1) & (body.shift(1) > avgbody.shift(1)) & dn & (O > H.shift(1)) & (C < (O.shift(1) + C.shift(1)) / 2) & (C > O.shift(1)) & uptrend_prior
P["Evening star"] = up.shift(2) & (body.shift(2) > avgbody.shift(2)) & (body.shift(1) < 0.3 * body.shift(2)) & \
    (np.minimum(O, C).shift(1) > C.shift(2)) & dn & (C < (O.shift(2) + C.shift(2)) / 2) & uptrend_prior.shift(1).fillna(False)
FWD = {n: C.shift(-n) / O.shift(-1) - 1 - COST for n in (5, 10, 20)}
win = pd.Series(dates >= START, index=dates)
base = liq & C.notna() & win.values[:, None]
CONF = C.shift(-1) > H                     # Nison: wait for confirmation (next day closes above the pattern high)
FWDc = {n: C.shift(-n - 1) / C.shift(-1) - 1 - COST for n in (5, 10, 20)}    # enter at the confirmation day's close
UPT = C > sma200; VOL = V > 1.5 * V.rolling(20).mean()
def ev(mask, fw):
    m = (mask & base).values; r = {n: fw[n].values[m] for n in fw}
    out = dict(signals=int(m.sum()))
    for n in (5, 10, 20):
        x = r[n][~np.isnan(r[n])]; out[f"avg{n}d%"] = round(x.mean() * 100, 2) if len(x) else np.nan
    x = r[10][~np.isnan(r[10])]; out["win10d%"] = round((x > 0).mean() * 100, 1) if len(x) else np.nan
    out["t10"] = round(x.mean() / x.std() * np.sqrt(len(x)), 1) if len(x) > 30 else np.nan
    return out
rows = [dict(pattern="BASELINE: any liquid stock-day", context="-", **ev(pd.DataFrame(True, index=dates, columns=C.columns), FWD))]
for name, pm in P.items():
    pm = pm.fillna(False)
    rows.append(dict(pattern=name, context="raw (with Nison trend rule)", **ev(pm, FWD)))
    if "bearish" not in name.lower() and "dark" not in name.lower() and "evening" not in name.lower():
        rows.append(dict(pattern=name, context="+ confirmation, entry at confirm close", **ev(pm & CONF, FWDc)))
        rows.append(dict(pattern=name, context="+ stock above 200 SMA (pullback in uptrend)", **ev(pm & UPT, FWD)))
        rows.append(dict(pattern=name, context="+ 200 SMA + volume > 1.5x", **ev(pm & UPT & VOL, FWD)))
        rows.append(dict(pattern=name, context="+ 200 SMA + confirmation", **ev(pm & UPT & CONF, FWDc)))
R = pd.DataFrame(rows); pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200)
print(R.to_string(index=False)); R.to_csv("pattern_event_study_5y.csv", index=False)
pd.to_pickle(dict(P=P, CONF=CONF, UPT=UPT, VOL=VOL), "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/nison/pats.pkl")
