"""Parse NSE MTO delivery files (EQ series) into one wide table of delivery % for Nifty 500 symbols."""
import glob, os, sys, pandas as pd
RAW = sys.argv[1]; OUT = sys.argv[2]
syms = {l.split("|")[0] for l in open("/home/claude/nsedata/lists/nifty500_sectors.txt") if "|" in l}
rows = []
for f in sorted(glob.glob(f"{RAW}/MTO_*.DAT")):
    d = pd.to_datetime(os.path.basename(f)[4:12], format="%d%m%Y")
    for line in open(f, errors="ignore"):
        p = line.strip().split(",")
        if len(p) >= 7 and p[0] == "20" and p[3] == "EQ" and p[2] in syms:
            try: rows.append((d, p[2], float(p[4]), float(p[5]), float(p[6])))
            except ValueError: pass
D = pd.DataFrame(rows, columns=["date", "sym", "traded", "deliv", "pct"])
D.to_csv(OUT, index=False, compression="gzip"); print(len(D), D.date.min(), D.date.max(), D.sym.nunique())
