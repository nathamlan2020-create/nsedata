import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.formatting.rule import CellIsRule
SP = "/tmp/claude-0/-home-claude/65f2a500-4991-5704-937b-9267d8da030c/scratchpad"
data = pd.read_pickle(f"{SP}/daywise.pkl")
wb = Workbook(); F = "Arial"
H = Font(name=F, bold=True, color="FFFFFF"); HF = PatternFill("solid", fgColor="1F4E78"); N = Font(name=F); B = Font(name=F, bold=True)
RS = '#,##0;[Red]-#,##0;-'; thin = Border(bottom=Side(style="thin", color="BBBBBB"))
red = PatternFill("solid", fgColor="F8D7DA"); green = PatternFill("solid", fgColor="D4EDDA")
def head(ws, row, vals):
    for j, v in enumerate(vals, 1):
        c = ws.cell(row, j, v); c.font = H; c.fill = HF; c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
# ---- daily sheets
short = {"Set A 9:22+9:35+10:05": "Set A daily", "Set B 9:45+10:05+10:35": "Set B daily"}
for name, d in data.items():
    ws = wb.create_sheet(short[name]); legs = [c.split(" ")[0] for c in d.columns if c.endswith("P&L Rs")]
    cols = ["Date", "Year", "Month", "Day", "Nifty open", "VIX (prev close)"]
    for et in legs: cols += [f"{et} premium (pts)", f"{et} P&L ₹", f"{et} legs stopped"]
    cols += ["Total P&L ₹ (3 lots)", "Cumulative ₹", "Drawdown ₹"]
    head(ws, 1, cols); n = len(cols)
    for i, (dt, r) in enumerate(d.iterrows(), start=2):
        ws.cell(i, 1, dt.to_pydatetime()).number_format = "dd-mmm-yyyy"
        ws.cell(i, 2, f"=YEAR(A{i})"); ws.cell(i, 3, f"=MONTH(A{i})"); ws.cell(i, 4, r["day"]); ws.cell(i, 5, float(r["nifty_open"])).number_format = "#,##0"
        ws.cell(i, 6, None if pd.isna(r["vix_prev_close"]) else float(r["vix_prev_close"])).number_format = "0.00"
        j = 7; pl = []
        for et in legs:
            ws.cell(i, j, float(r[f"{et} premium pts"])).number_format = "0.0"
            ws.cell(i, j + 1, float(r[f"{et} P&L Rs"])).number_format = RS; pl.append(f"{L(j+1)}{i}")
            ws.cell(i, j + 2, int(r[f"{et} legs stopped"])); j += 3
        ws.cell(i, j, "=" + "+".join(pl)).number_format = RS
        ws.cell(i, j + 1, f"={L(j)}{i}" if i == 2 else f"={L(j+1)}{i-1}+{L(j)}{i}").number_format = RS
        ws.cell(i, j + 2, f"={L(j+1)}{i}-MAX(0,MAX(${L(j+1)}$2:{L(j+1)}{i}))").number_format = RS
        for c in range(1, n + 1): ws.cell(i, c).font = N
    last = i; tc = L(n - 2)
    ws.conditional_formatting.add(f"{tc}2:{tc}{last}", CellIsRule(operator="lessThan", formula=["0"], fill=red))
    ws.conditional_formatting.add(f"{tc}2:{tc}{last}", CellIsRule(operator="greaterThan", formula=["0"], fill=green))
    ws.freeze_panes = "B2"; ws.row_dimensions[1].height = 42
    for c in range(1, n + 1): ws.column_dimensions[L(c)].width = 12
    ws.column_dimensions["A"].width = 13
    ws.auto_filter.ref = f"A1:{L(n)}{last}"
    data[name] = (d, last, tc)
# ---- monthly sheet
wm = wb.create_sheet("Monthly"); r0 = 1; months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
years = sorted({dt.year for d, _, _ in data.values() for dt in d.index})
for name, (d, last, tc) in data.items():
    sh = f"'{short[name]}'"
    wm.cell(r0, 1, f"{name} — monthly P&L ₹ (3 lots)").font = Font(name=F, bold=True, size=12)
    head(wm, r0 + 1, ["Year"] + months + ["Year total", "Expiry days", "Winning days"])
    for k, y in enumerate(years):
        rr = r0 + 2 + k; wm.cell(rr, 1, str(y)).font = B
        for m in range(1, 13):
            c = wm.cell(rr, m + 1, f"=SUMIFS({sh}!${tc}$2:${tc}${last},{sh}!$B$2:$B${last},{y},{sh}!$C$2:$C${last},{m})"); c.number_format = RS; c.font = N
        wm.cell(rr, 14, f"=SUM(B{rr}:M{rr})").number_format = RS; wm.cell(rr, 14).font = B
        wm.cell(rr, 15, f"=COUNTIFS({sh}!$B$2:$B${last},{y})").font = N
        wm.cell(rr, 16, f'=COUNTIFS({sh}!$B$2:$B${last},{y},{sh}!${tc}$2:${tc}${last},">0")').font = N
    tr = r0 + 2 + len(years); wm.cell(tr, 1, "Total").font = B
    for c in range(2, 17):
        wm.cell(tr, c, f"=SUM({L(c)}{r0+2}:{L(c)}{tr-1})").font = B
        if c <= 14: wm.cell(tr, c).number_format = RS
    wm.conditional_formatting.add(f"B{r0+2}:N{tr-1}", CellIsRule(operator="lessThan", formula=["0"], fill=red))
    wm.conditional_formatting.add(f"B{r0+2}:N{tr-1}", CellIsRule(operator="greaterThan", formula=["0"], fill=green))
    r0 = tr + 3
wm.column_dimensions["A"].width = 8
for c in range(2, 17): wm.column_dimensions[L(c)].width = 10
wm.column_dimensions["N"].width = 12
# ---- yearly sheet
wy = wb.create_sheet("Yearly")
head(wy, 1, ["Year", "Set A ₹ (9:22+9:35+10:05)", "Set A expiry days", "Set A win %", "Set A worst day ₹", "Set B ₹ (9:45+10:05+10:35)", "Set B expiry days", "Set B win %", "Set B worst day ₹"])
for k, y in enumerate(years):
    rr = k + 2; wy.cell(rr, 1, str(y)).font = B; col = 2
    for name, (d, last, tc) in data.items():
        sh = f"'{short[name]}'"
        wy.cell(rr, col, f"=SUMIFS({sh}!${tc}$2:${tc}${last},{sh}!$B$2:$B${last},{y})").number_format = RS
        wy.cell(rr, col + 1, f"=COUNTIFS({sh}!$B$2:$B${last},{y})")
        wy.cell(rr, col + 2, f'=IFERROR(COUNTIFS({sh}!$B$2:$B${last},{y},{sh}!${tc}$2:${tc}${last},">0")/{L(col+1)}{rr},0)').number_format = "0.0%"
        wy.cell(rr, col + 3, f"=_xlfn.MINIFS({sh}!${tc}$2:${tc}${last},{sh}!$B$2:$B${last},{y})").number_format = RS
        for c in range(col, col + 4): wy.cell(rr, c).font = N
        col += 4
tr = len(years) + 2; wy.cell(tr, 1, "Total").font = B
for c in (2, 3, 6, 7): wy.cell(tr, c, f"=SUM({L(c)}2:{L(c)}{tr-1})").font = B
for c in (2, 6): wy.cell(tr, c).number_format = RS
for c, tcol in ((4, 3), (8, 7)): wy.cell(tr, c, f"=SUMPRODUCT({L(c)}2:{L(c)}{tr-1},{L(tcol)}2:{L(tcol)}{tr-1})/{L(tcol)}{tr}").number_format = "0.0%"
for c in (5, 9): wy.cell(tr, c, f"=MIN({L(c)}2:{L(c)}{tr-1})").number_format = RS
wy.conditional_formatting.add(f"B2:B{tr-1}", CellIsRule(operator="lessThan", formula=["0"], fill=red))
wy.conditional_formatting.add(f"F2:F{tr-1}", CellIsRule(operator="lessThan", formula=["0"], fill=red))
for c in range(1, 10): wy.column_dimensions[L(c)].width = 15
wy.row_dimensions[1].height = 32
# ---- summary
ws = wb["Sheet"]; ws.title = "Summary"
ws["A1"] = "Nifty expiry-day ATM straddle — 3 lots, backtest Jan 2016 – Oct 2026"; ws["A1"].font = Font(name=F, bold=True, size=14)
rows = [("", "Set A (9:22 + 9:35 + 10:05)", "Set B (9:45 + 10:05 + 10:35)")]
ws.append([]); head(ws, 3, ["Metric", "Set A (9:22 + 9:35 + 10:05)", "Set B (9:45 + 10:05 + 10:35)"])
items = []
for k, (name, (d, last, tc)) in enumerate(data.items()):
    sh = f"'{short[name]}'"; cum = L(d.shape[1] and (len([c for c in d.columns if c.endswith('P&L Rs')]) * 3 + 8)); dd = L(len([c for c in d.columns if c.endswith('P&L Rs')]) * 3 + 9)
    items.append({"Total profit ₹": f"=SUM({sh}!{tc}2:{tc}{last})", "Expiry days traded": f"=COUNT({sh}!{tc}2:{tc}{last})",
                  "Average ₹ per expiry day": f"=AVERAGE({sh}!{tc}2:{tc}{last})", "Win %": f'=COUNTIF({sh}!{tc}2:{tc}{last},">0")/COUNT({sh}!{tc}2:{tc}{last})',
                  "Best day ₹": f"=MAX({sh}!{tc}2:{tc}{last})", "Worst day ₹": f"=MIN({sh}!{tc}2:{tc}{last})", "Max drawdown ₹": f"=MIN({sh}!{dd}2:{dd}{last})",
                  "Average ₹ per year (10.8 yrs)": f"=SUM({sh}!{tc}2:{tc}{last})/10.8"})
for i, key in enumerate(items[0], start=4):
    ws.cell(i, 1, key).font = B
    for j in (0, 1):
        c = ws.cell(i, j + 2, items[j][key]); c.font = N; c.number_format = "0.0%" if key == "Win %" else RS
notes = ["Rules: Nifty weekly expiry day only; sell 1 lot ATM CE + 1 lot ATM PE at each entry time (3 straddles a day); 30% stop-loss on each leg checked every minute; everything still open is bought back at 15:15.",
         "₹ figures use today's lot size (65 qty) for every year; costs included: STT 0.1% on sell premium, ~0.04% other charges per side, ₹40 brokerage per leg round trip, 0.5 pt slippage per side, +1% slippage on stop fills.",
         "Minute-level option prices are not published for past years: prices are rebuilt from the real Nifty 1-minute path with Black-Scholes, using each day's implied volatility solved from the actual 9:15 straddle price in the NSE bhavcopy. Treat ₹ amounts as estimates; the comparison between entry times is more reliable.",
         "VIX = previous day's India VIX close (known before the trade). 2026 data runs to 23 Oct 2026. Approx. margin for 3 naked straddles: ₹7–7.5 lakh.",
         "Monthly and Yearly sheets are formulas on the daily sheets. Use the filter on the daily sheets to sort or filter by date, day or VIX."]
for k, t in enumerate(notes):
    c = ws.cell(14 + k, 1, t); c.font = Font(name=F, italic=True, size=9); ws.merge_cells(start_row=14 + k, start_column=1, end_row=14 + k, end_column=3); c.alignment = Alignment(wrap_text=True, vertical="top"); ws.row_dimensions[14 + k].height = 42
ws.cell(13, 1, "Notes and assumptions").font = B
ws.column_dimensions["A"].width = 34; ws.column_dimensions["B"].width = 30; ws.column_dimensions["C"].width = 30
wb.save("straddle_3lots_daywise.xlsx")
