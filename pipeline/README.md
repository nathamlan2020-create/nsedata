# Daily Reel pipeline (Hindi health + trading explainers)

`python3 make.py SPECS_DIR OUT_DIR --jobs 3` turns one JSON script per video into finished 1080x1920 Reels
(Hindi AI voice via Kokoro, Hindi captions, music bed, end card with disclaimer). Setup:
`pip install --break-system-packages kokoro-onnx soundfile`; the Kokoro model (~350 MB) downloads from GitHub on first run
into `$KOKORO_DIR` (default `~/kokoro`). Fonts are in `fonts/`.

## Writing a spec (see `examples/`)
- `theme`: `health` (brand सेहत दीदी, female voice, blue) or `trading` (brand @trading71639, male voice, teal).
- `icon` for the hook: lungs, heart, candles, pill, clock, shield, stomach, brain.
- Scenes, in order: `hook` first, `caution` last, 3 scenes in between chosen from `steps`, `zones`, `counter`, `chart`.
  Aim for 5 scenes and 40-55 seconds total (about 12-14 short phrases).
- `cap`: list of `[text, 0|1]` parts; 1 = highlighted word. Max 2 lines (`\n`), about 22 characters per line.
- `vo`: Hindi phrases in **Devanagari only** (no Latin letters: write "सी ओ पी डी", "ई एम ए"). Numbers in words
  ("पच्चीस सेकंड"). Short, spoken sentences; commas create natural pauses.
- `steps`: 2-4 items (one `vo` phrase per item, spoken as each card appears). Keep items under ~28 characters.
- `zones`: 2-3 items `[range, meaning, g|a|r]` (green/amber/red), one `vo` phrase per item.
- `counter`: `to` (number) and `unit`; counts up while the single phrase plays.
- `caution`: 1-2 warning items, `vo` = one phrase per item **plus** a final follow line ("ऐसी और जानकारी के लिए, फ़ॉलो कीजिए.").
- `chart` (trading only): synthetic candles, never a real stock. `labels` (one `vo` phrase each) attach to the pattern's key points:
  - `breakout`: 1 breakout candle closing above resistance · 2 volume spike (box on volume bar) · 3 pullback low after breakout
  - `fakeout`: 1 breakout candle above resistance · 2 candle closing back below resistance (exit) · 3 where price ended up (big fall). Lines: resistance + stop loss
  - `retest`: 1 breakout close · 2 retest low at old resistance · 3 trend continues up
  - `pullback`: 1 swing high in uptrend · 2 pullback low (entry zone) · 3 new high
  - `downtrend`: 1 lower low · 2 lower high (bounce that fails) · 3 new lower low
  - `range`: 1 top at resistance · 2 bottom at support (2 labels max)
  - `trail`: 1 first swing low (stop) · 2 higher swing low (stop raised) · 3 drop that hits the trailed stop

- `payoff` (trading only): expiry profit/loss diagram; `strategy` one of short_straddle, short_strangle, bull_put, bear_call,
  batman, iron_fly, long_straddle. Up to 3 `labels` (one `vo` phrase each) at these points:
  - short_straddle / iron_fly / long_straddle: 1 at the strike (max profit, or max loss for long) · 2 upper breakeven · 3 far move
  - short_strangle: 1 middle (profit zone) · 2 upper breakeven · 3 far move (loss)
  - bull_put: 1 above both strikes (full premium kept) · 2 breakeven · 3 below both (capped loss)
  - bear_call: 1 below both strikes (full premium kept) · 2 breakeven · 3 above both (capped loss)
  - batman (1 ATM buy + 2 OTM sells on each side): 1 peak at a short strike · 2 middle (small debit/credit) · 3 far move (unlimited loss)
  Indian stock options are physically settled: mention closing before expiry when relevant.

## Content rules
- Health: patient-friendly Hindi, conservative, cite-able numbers only (guidelines / PubMed / standard textbooks);
  always "see a doctor" for red zones; no drug doses; no diagnosis claims.
- Trading: education only. Never name a stock, index constituent or fund as a pick; no buy/sell/target calls; no
  promises of returns. Every video ends with the education-only disclaimer (built into the end card).
- Topic banks: `topics_health.txt`, `topics_trading.txt`; used topics are appended to `used_topics.txt` (date | theme | topic | slug).
