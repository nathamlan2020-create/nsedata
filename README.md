# SurgerySaathi daily Short pipeline ("Dr Saathi ke OT Kisse")

Owner: an anaesthesiologist in India (timezone Asia/Kolkata). Brand: **SurgerySaathi**. Characters (cutouts in assets/cast/): **Dr Saathi**, a female anaesthesiologist cartoon (AI character), answers a nervous patient: **uncle** (older man, moustache), **dadi** (elderly woman) or **didi** (young pregnant woman — use for C-section / pregnancy / women's topics). Rotate patients so the same one is not used 3 days running; pick the one that fits the topic.
Every video = Uncle's question → Dr Saathi's one-line answer → "SACH KYA HAI?" with 4 facts → end card "Darr nahi, taiyaari!".

## Files
- `ss_make.py spec.json OUTDIR` — validates the spec, makes TTS (Microsoft Edge neural voices via `edge-tts`: Swara for Dr Saathi/Dadi/Didi, Madhur for Uncle; automatic fallback to Kokoro if Edge fails), animates (slide-ins, talking bounce, bubble pops, camera push-in, whooshes), renders `OUTDIR/<slug>.mp4` (1080×1920, ~30–36 s), `<slug>_cover.jpg` and `<slug>_check.jpg` (6-frame contact sheet). Add `--preview` to make only the jpgs. Invalid spec → prints `{"ok":false,"invalid":[...]}` and exits 1: fix and rerun.
- `tg_send.py spec.json video.mp4` — sends the video + an "upload kit" (title, description, tags, settings) to the owner's Telegram. Needs env `TG_TOKEN`, `TG_CHAT`.
- `topics.txt` — topic bank (`topic | stage idea | category`) (take the first one not already in `used.txt`). `used.txt` — log of made episodes (last `ep` number + 1 = next number).
- `examples/` — finished specs. **Read at least the latest example before writing a new spec**; copy its structure exactly.
- `specs/` — every spec the agent made (keep them).
- `assets/` — character art (cast/), font. Do not change. Channel handle shown on the end card comes from env SS_HANDLE (default @surgerysathi).

## Spec format (JSON)
| key | rule |
|---|---|
| `lang` | "en" = English captions + Indian English voices (Neerja/Prabhat); "or" = Odia script + Meta MMS Odia voice (needs huggingface.co and *.hf.co allowed); "hi" (default, Hinglish captions + Hindi voices) or "bn" (Bengali script captions/bubbles/bullets + Microsoft Bengali voices Tanishaa/Bashkar; patient names কাকু / দিদা / দিদি). Voice text for bn is Bengali script, numbers in words |
| `layout` | **"ot" (default for new episodes)**: conversation in an operating theatre (OT light, OT table, monitor with normal readings, laparoscopy tower); `tiles` and `stage` are ignored (use `[]` and `{}`), bullets ≤ 34 chars, one line each. "classic" (omit the key) = old infographic layout with tiles + checklist/meter |
| `slug` | `ep<NUM>_<oneword>` ASCII |
| `num` | episode number (int) |
| `patient` | `uncle`, `dadi` or `didi` (sets the patient's art and voice). Captions and Dr Saathi's lines must address that patient ("Uncle", "Dadi", "Didi") |
| `topic` | short topic text (same as used.txt) |
| `category` | REQUIRED: the topic's last field in topics.txt — one of pre, intra, post, surgery, doctor, patient, time, place. It picks the YouTube playlist (playlists.json) shown in the upload kit. Frame every episode as a common MYTH (the patient's question/belief) answered by the SACH. Spread categories: avoid the same category 3 days running (skip ahead in topics.txt if needed) |
| `intro` | `[line1, line2, subtitle]` — lines ≤16 chars, CAPS Hinglish (line2 shows in red); subtitle ≤38 chars |
| `q_vo` | the patient's voice, list of `[Devanagari text, pause_seconds]`. Starts with `["डॉक्टर मैडम...", 0.22]`. 2–3 phrases, ≤ 5 s total |
| `a_vo` | Dr Saathi's short answer, 2–3 phrases, ≤ 4.5 s |
| `f_vo` | facts. First phrase `["सच क्या है?", 0.3]`. Then 6–9 short phrases (≤ 6 words each), pauses 0.06 inside a sentence, 0.2 at sentence end. 12–17 s total |
| `bullet_starts` | 4 increasing indexes into `f_vo` where each on-screen bullet appears (index ≥ 1) |
| `switch_bullet` | 1–4: at this bullet the tiles flip from "before" to "after" and the meter moves (default 2) |
| `q_bubble`, `a_bubble` | 2–3 lines each, ≤ 24 chars per line, Hinglish (Latin script) |
| `bullets` | exactly 4, ≤ 36 chars, Hinglish |
| `cap` | captions `q`, `a`, `f` (shown during facts until bullet 3), `f2` (rest) — Hinglish, ≤ 120 chars each, matching what is said |
| `tiles` | exactly 4 `[LABEL ≤11, BEFORE ≤9, AFTER ≤9]` CAPS; before shows red, after green (same text both = neutral) |
| `stage` | either `{"type":"checklist","title":"≤26 CAPS","rows":[4 × {"icon":…,"label":"≤27"}]}` (row i ticks when bullet i appears) or `{"type":"meter","title":…,"min":0,"max":10,"from":7,"to":1,"left":"…","right":"…","good_low":true,"unit":"","fmt":"{:.0f}"}` (value rises to `from`, then moves to `to` at switch_bullet) |
| `youtube` | `title` (≤95 chars, ends "\| Dr Saathi ke OT Kisse #N #shorts", one emoji), `description` (same layout as example: question, answer, "Sach kya hai?" ✅ lines, "Darr nahi, taiyaari!", follow line, AI disclaimer, 5 hashtags), `tags` (14–18, Hinglish + English search phrases) |

Icons: ring nail teeth glasses file pill person drop cube heart leaf clock glass plate bandage phone cigarette lungs thermo syringe.

## Voice text rules (Kokoro Hindi)
- Devanagari only. Numbers in words (दो, छह, चौबीस). English medical words written in Devanagari (एनेस्थीसिया, ऑपरेशन, नर्स, बीपी, ऑक्सीजन).
- Short phrases; end sentences with "।" or "?" or "!".

## Medical content rules (non-negotiable)
- General patient education only. No drug names with doses, no diagnosis, no "stop your medicine" — always "doctor se poochhiye / doctor ki batayi timing".
- Every number or time you state (hours, days, %) must be checked against a reputable source (guideline, PubMed, NHS/ASA/RCoA/major hospital site) in this run. If not verifiable, say it without the number or pick the next topic.
- Reassuring tone, never fear-mongering. Red-flag symptoms always say "turant doctor ko dikhaiye".
- No promotion of any hospital, doctor or brand. No self-promotion of the owner.

## Daily Bengali twin (since 9 Nov 2026)
Every day, after the Hindi episode, make a Bengali twin of the SAME episode: copy the Hindi spec to `specs/ep<N>_<word>_bn.json`, set `"lang": "bn"`, slug `ep<N>_<word>_bn`, same `num`, `layout`, `patient`, `bullet_starts`.
Translate everything into simple spoken Kolkata Bengali in Bengali script: intro, q_vo/a_vo/f_vo (Bengali script, numbers in words, first f_vo phrase `["সত্যিটা কী?", 0.3]`), bubbles, bullets (≤34 chars), captions, youtube title/description/tags.
Names: Dr Saathi → ডাঃ সাথী; uncle → কাকু; dadi → দিদা; didi → দিদি. Header is automatic ("ডাঃ সাথীর OT গপ্পো #N"); in the youtube title use "| ডাঃ সাথীর OT গপ্পো #N #shorts"; description ends with "ভয় নয়, প্রস্তুতি!", the follow line and the Bengali AI disclaimer (see specs/ep16_bath_ot_bn.json).
Build and Read its _check.jpg the same way, then send it with tg_send.py.

## Long videos (16:9, normal uploads) — since 11 Nov 2026
- `long_make.py spec.json OUTDIR [--preview]` — story video, 1920×1080: title card → "STEP i/n" chapter cards → Dr Saathi + patient talking in the OT with a board of bullets that tick in → end card. Spec: see `specs/long01_poora_din.json` (lines = `[role p|dr, Devanagari voice, Hinglish caption, expression, bullets_visible]`). Writes `<slug>.mp4`, `<slug>_thumb.jpg` (1280×720), `<slug>_check.jpg`.
- `comp_make.py spec.json OUTDIR` — compilation of finished Shorts in 16:9 (Short on the left over a blurred copy, "SAWAAL i/n" panel on the right; end cards trimmed except the last; prints chapter timestamps). Spec: `specs/comp01_6sawaal.json`.
- `tg_send_long.py spec.json video.mp4 thumb.jpg` — sends video, thumbnail and long-video upload kit (chapters in description).
- Same medical rules apply: every fact verified in the run, no numbers unless verified.
