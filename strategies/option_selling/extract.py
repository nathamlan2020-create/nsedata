"""Extract NIFTY / BANKNIFTY index options (nearest 3 expiries) from NSE F&O bhavcopies 2016-2026 -> one compact table."""
import glob, zipfile, io, pandas as pd, numpy as np
from multiprocessing import Pool
FILES = sorted(glob.glob("/home/claude/nsedata/options/bhavcopy/*/*/*.zip"))
OUT = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad/idxopt.pkl"
def one(f):
    try:
        with zipfile.ZipFile(f) as z: d = pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), low_memory=False)
    except Exception as e: return None
    if "TckrSymb" in d.columns:
        d = d[(d.FinInstrmTp == "IDO") & d.TckrSymb.isin(["NIFTY", "BANKNIFTY"])]
        x = pd.DataFrame(dict(date=pd.to_datetime(d.TradDt), sym=d.TckrSymb, exp=pd.to_datetime(d.XpryDt), k=d.StrkPric.astype(float), typ=d.OptnTp,
                              o=d.OpnPric, h=d.HghPric, l=d.LwPric, c=d.ClsPric, settle=d.SttlmPric, vol=d.TtlTradgVol, und=d.UndrlygPric, lot=d.NewBrdLotQty))
    else:
        d = d[(d.INSTRUMENT == "OPTIDX") & d.SYMBOL.isin(["NIFTY", "BANKNIFTY"])]
        x = pd.DataFrame(dict(date=pd.to_datetime(d.TIMESTAMP, format="%d-%b-%Y"), sym=d.SYMBOL, exp=pd.to_datetime(d.EXPIRY_DT, format="%d-%b-%Y"),
                              k=d.STRIKE_PR.astype(float), typ=d.OPTION_TYP, o=d.OPEN, h=d.HIGH, l=d.LOW, c=d.CLOSE, settle=d.SETTLE_PR, vol=d.CONTRACTS,
                              und=np.nan, lot=np.nan))
    if x.empty: return None
    keep = []
    for s, g in x.groupby("sym"):
        ex = sorted(g.exp.unique())[:3]; keep.append(g[g.exp.isin(ex)])
    return pd.concat(keep)
if __name__ == "__main__":
    with Pool(8) as p: parts = [r for r in p.map(one, FILES, chunksize=20) if r is not None]
    D = pd.concat(parts, ignore_index=True)
    for c in ("o", "h", "l", "c", "settle", "vol", "und", "lot"): D[c] = pd.to_numeric(D[c], errors="coerce").astype("float32")
    D.to_pickle(OUT); print(len(D), D.date.min(), D.date.max(), D.date.nunique(), D.groupby("sym").date.nunique().to_dict())
