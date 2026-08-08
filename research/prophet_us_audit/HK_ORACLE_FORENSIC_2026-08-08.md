# HK Golden Oracle forensic — Tencent sell, Alibaba grey dot, 200MA gate map — 2026-08-08

**Charter:** operator escalation 2026-08-08 (Tencent 0700.HK "SELL Jul 24 with no visible
MACD-RSI cross-down"; Alibaba 9988.HK buy chased Jul 10 vs the Jul-2 grey dot; Tencent's
Jun-5/Jul-3 bottoms never flagged; HK board stuck at 2 picks). Cross-repo READ-ONLY forensic
by an Opus review lane over charting-app `signal_layer/` + this repo. Measurement/receipt
only. Replay basis: `data/hk_stocks/{0700,9988}.HK.parquet` through 2026-08-07; NO production
slice exists locally (terminal HK JSONs dated Jul 25), so replayed dates can differ from what
production served — itself a finding (see §4).

## 1. Tencent 2026-07-24 SELL — verdict: a trailing structure stop, not an oracle sell

- The MACD-RSI cross-down (`CS`) is **no longer emitted** to the user stream
  (charting-app `signal_layer/contracts.py:164-165`). Every user-facing SELL comes from
  `v2["sell_confirms"]` — reasons `["distribution_confirmed","structure_break"]`
  (`contracts.py:202-221`).
- **The rule** (`confluence_v2.py:482-486` + `:399-441`): ARM on (leg A) 2D RSI-MACD bear
  cross while 3D stoch ≥75, or (leg B) 3D stoch bear cross from ≥80; ARMED window 15
  sessions; CONFIRM when the daily close breaks the last confirmed radius-3 swing low.
- **0700.HK fired leg B** (bar labeled 07-20, k.shift=92.6) and confirmed when the daily
  close 440.60 (replay 07-22) broke the 07-14 swing low 456.20.
- **The operator was right:** the 3D RSI-MACD had `CS=False` on every bar 05-21→08-05 and
  `macd > sig` continuously from 06-01, RISING at the fire. The red "GOLDEN ORACLE · SELL"
  pill printed while the oracle's own momentum read bull.

Blockers filed: (B1) a stream whose own docstrings say "never a scored exit" / "DISPLAY
only" (`confluence_v2.py:448`, `:18`) sets `position_hint` flat (`contracts.py:250-253`) —
display-tier promoted to a position event with no gauntlet; (B2) marker price stamps the
close of a 3D bar up to **2 sessions after** the marker's own date (`contracts.py:210-216`
searchsorted; 9988's 05-27 SELL carries the 05-26-open bar's close) — PIT violation; (B3)
the BACKTEST exits on `CS` (`confluence_v2.py:72`) while the DRAWN sell is the confirm event
— stats beside the markers measure a different strategy; (B4) replay says 07-22, production
showed 07-24 — the confirm date is feed-sensitive (see §4 grids).

## 2. Alibaba grey dot — identity, and the chase marker's second lie

- Grey dot = `early_dots` (`confluence_v2.py:351-383`): 3D StochRSI %K×%D cross AND %D <20
  within 8 bars AND calendar-2B MACD hist rising. Drawn 2.2px muted behind the "Signals
  detail" chip (`ChartPanel.tsx:2190`, `:2183`). Never enters `signals[]`, never touches
  `position_hint`, never keeper-graded, capped to last 40.
- **9988.HK replay: dot on the bar opening 2026-06-30 at 94.10 — the low.** Next emitted
  BUY: bar opening 2026-07-09 at 110.70, **+17.6% later**.
- **The Jul-9/10 BUY the operator chased was itself `regime_blocked`** — stamped
  `tier=None, score=None` (`contracts.py:191-192`) and rendered slate (`ChartPanel.tsx:2149`,
  `:2035`). A vetoed entry drawn with BUY geometry on the price series.
- "Extended — don't chase" on the same card is a DIFFERENT pipeline entirely (this repo,
  `engine/cycles.py:1238-1245` → `entry_signal.py:178-179`) and `contracts.py:260` publishes
  a second, unrelated `extended` (= `strong_bull`). Two meanings of one word on one card.

## 3. The 200MA / HTF-washout gate map — operator's belief confirmed

- ONE hard gate blocks all buys below the 200dMA: `bear_block = ~mo_bull & ~above200 &
  ~w2_bull` (`confluence.py:315`), consumed at `confluence.py:342`, `confluence_v2.py:71`,
  `:133`, `contracts.py:189-194`; plus soft gate `_reclaim_and_hold` (200dMA reclaim within
  2 bars, `confluence_v2.py:99-104`).
- **The sole release is `w2_bull` — a COMPLETED 2W RSI-MACD cross.** Monthly StochRSI pinned
  at 0.0 and turning (0.0→0.4→6.8→13.7 — a textbook washout-and-turn on 0700.HK) has **zero
  path into emission**: it exists only as `monthly_os_dwell`, 10/100 display-only recipe
  points (`confluence_v2.py:304-306`; "never a gate" `:14`). 1W StochRSI is not read at all.
- Measured: `bear_block=True` on EVERY 0700.HK bar 05-21→08-05 (2W macd −9.538 vs sig
  −9.413 on 08-07 — still no cross).
- **Jun-5 bottom: a raw CB buy DID fire** (bar opening 06-01, close 466.40) — emitted
  `regime_blocked`. **Jul-3 bottom: no CB possible** — `macd > sig` continuously from 06-01,
  so no new bull cross without an intervening bear cross: **a name in a shallow bull cross
  through a −20% drawdown can never re-fire a buy.** (An early dot fired 07-02.)
- S1/S2 HTF badges: absent from charting-app entirely; display-only rank-neutral in this
  repo (`confluence_tiers.py:537`).

## 4. Implementation census — a THIRD confluence implementation on FIVE grids

charting-app `confluence.py`/`confluence_v2.py` vs this repo's `engine/confluence_tiers.py`:
shared words, different machine. Tiers `aplus/quality/base` vs `T1..T4`; `not_topped` and
`FRESH_TICKS` do not exist in charting-app; 200MA vetoes ALL buys there vs T4-only here;
veto legs are bearish-divergence + reclaim-and-hold + recipe vetoes there vs
stoch_ob/stoch_bear/macd_bear here; it has a SELL machine (structure stop), this repo has
none; it has NO null disclosure, this repo prints `veto_legs_null`. Both run on the same HK
names on the same page (`build_hk_library.py:1408,1426` gates board inclusion on
`confluence_tiers` while the Terminal draws `signal_layer` markers): **two signal systems
disagree on the most consequential gate, on one page.**

**Five bar grids inside one emission:** session-grouped 3D (CB/CS) · calendar-3B (SELL ARM
leg B) · calendar-2B (ARM leg A + grey dots) · daily (SELL confirm + swing lows) ·
W-FRI/2W/ME. `confluence.py:177-179` documents calendar-3B as WRONG ("moved ~80% of signal
dates on NVDA") and `confluence_v2.py:411,428,432` reintroduces exactly it in the ARM path.
Measured 0700.HK: 1,823 session bars vs 1,920 calendar-3B bars — **5.3% divergence**; the
07-01 HK holiday re-anchors the calendar grid = the likely 07-22-vs-07-24 mechanism. SELL
dates are not stable across feeds.

## Remediation map (ruled 2026-08-08)

Wave HK-O1 (ships now, charting-app, truth-in-labeling + PIT — no gate/grid semantics
change): structure-stop sells re-badged truthfully; `regime_blocked` never drawn with BUY
geometry; marker price = the event's own day; the two `extended`s disambiguated.
Wave HK-O2 (next, measured): grid unification onto the session grid (blast-radius first —
their own doc says 80% of dates move); washout-state release for `bear_block` (monthly-washout
+ turn + cohort discriminators per ANTICIPATION §6.3); shallow-cross re-fire repair;
backtest/marker parity. HK board complete fix (this repo) remains gated on #4976.
