# Flow Origination Sandbox (FOS)

Author: Fable
Date: 2026-07-16
Status: OPERATOR-RATIFIED experiment. Paper-only. Firewalled from all production surfaces.
Relationship: companion to `OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` (which governs the
production/display lanes and remains unchanged by this doc).

---

## 0. The operator override (ruling of record)

On 2026-07-16 the operator explicitly ruled that the NW-sole-originator house law
(OPTIONS_SENSOR_CONTRACT §5) and the AVOID-not-SHORT kill (DO_NOT_REBUILD §1, RO-3) are
**bypassed for this sandbox and only this sandbox**. Rationale, in the operator's words
(paraphrased): the T1–T4 confluence gate restricts entries to names meeting its criteria;
live options flow may carry information about impending good/bad news that the confluence
inputs cannot see yet, including short-entry and sell-signal information; if we never try,
we cannot learn whether novel origination methods exist outside the current gate.

Scope of the override — narrow and explicit:
- The sandbox may ORIGINATE paper positions (long AND short) from options-flow evidence.
- Nothing in the sandbox touches, feeds, weights, or annotates: NW candidate state,
  Prophet plans/ledger, the Brain/bot books, us_standouts, flow_leaders fire rules, any
  §4 gate, or any liftable production surface. One-way glass: the sandbox may READ
  production data planes; it may WRITE only its own book and ledger.
- The frozen preregs (w5b_tape_residual, O-OPT, EXIT-CROWD) are untouched: this is a
  FORWARD-ONLY paper book, not a historical test of their frozen claims (adjacency
  statement in §5).
- Promotion out of the sandbox (into any production surface) requires a separate operator
  ruling AFTER the read clocks in §7 — a winning sandbox record is the *argument* for that
  ruling, not the ruling itself.

## 1. The hypothesis being tested (stated honestly)

H-FOS: aggressive, unusual, or persistently one-sided options flow contains directional
information about the underlying stock (informed positioning ahead of news, accumulation,
distribution) that (a) precedes the price move rather than chasing it, and (b) is NOT
captured by the T1–T4 confluence gate's price/breadth/positioning inputs — such that a
paper book originated from flow evidence alone earns positive residual returns vs matched
controls, on BOTH the long and short side.

Priors we do not hide (the sandbox exists to overcome them, not to ignore them):
- Bar-level signed direction recovery measured 0.41 (worse than coin flip) — F7.
- ThetaData tape signing is under an active calibration suspend (0/3 sessions ≥0.75).
- Volume > OI does not prove opening; next-day OI is the only confirmation and arrives T+1.
- Literature support exists for specific constructions (Pan–Poteshman put/call volume
  informativeness; Hu option-induced order flow), which is precisely what the archetypes
  below implement — the disagreement between our measured signing weakness and the
  literature is the interesting scientific question.

## 2. Implementation shape — a Pick Lab book, not new infrastructure

The sandbox is a new Pick Lab shadow book `plab_flow_origin_v1` riding the EXISTING
plumbing: FS-0 flow events (+ tape_flow daily features + live_flow feed) → deterministic
origination rules (§4) → paper positions with geometry → the existing forward grading
mechanics. No new ledger writer (FS-0 single-writer law respected: sandbox positions log
via the Pick Lab book, flow evidence stays in FS-0), no new outcome engine.

- Book: long lane + short lane, each position stamped with archetype id, full evidence
  bundle (the exact FS-0 event ids + feature snapshot), origination_version, and the data
  plane it fired from (`live_feed` today; `stream_feed` when FPSS is fixed — never pooled).
- Sizing: flat notional per position (paper), max N concurrent per lane (start: 15/15),
  one position per root per archetype at a time.
- Geometry: ATR-based stop + time stop (default 10 trading days, archetype-overridable),
  symmetric long/short. First-trigger-closes, same as the Prophet ledger convention.
- Display: admin/Terminal surface labeled "EXPERIMENTAL SANDBOX — paper, ungated,
  operator-ratified override" — never mixed into any picks board.

## 3. Data dependencies

Interim (available today): the 122-root live_flow feed (~36-min effective), tape_flow
daily signed features (375 roots, EOD), FS-1 historical cohorts for threshold calibration,
options_hub vol/GEX context. Full power: the FPSS Full Trade Stream fix (operator action,
see program doc §8) unlocks full-universe, minutes-latency origination — the sandbox
design is identical, only the detection surface widens; positions fired from the stream
get the `stream_feed` tag.

## 4. Pre-registered origination archetypes (v1 — frozen at first fire)

Thresholds are calibrated ONCE on FS-1 historical cohorts (2012→) before the book opens,
then frozen; changes = origination_version bump + era split (never retro-applied).

- FO-A **Lead accumulation (long)**: repeated same-side call events on one root across ≥2
  sessions (or ≥3 intraday windows once streaming), aggressor-side ask-share high,
  opening-probability proxy high (volume vs prior OI + contract age), stock residual move
  since first event < +1σ (lead, not chase), next-day OI confirms ≥50% of the inferred
  opening volume. Entry at confirmation; the OI-confirmation leg makes this T+1 by design.
- FO-B **Lead distribution / informed bearish (short)**: mirror of FO-A on puts bought /
  calls sold aggressively, with borrow-availability sanity ignored (paper), same OI
  confirmation. This is the lane the production constitution forbids — here it trades.
- FO-C **Flow-divergence reversal (long)**: strong bullish delta-flow while the stock is
  flat/down on the day and sector is not down more (flow fighting tape), no chase leg
  required; smaller size, tighter stop.
- FO-D **Pre-event positioning (either side)**: unusual one-sided flow in an
  event-containing expiry 2–10 sessions before a known catalyst, direction = flow side,
  exit before or straddling the event per a frozen rule. This is the "sees the news
  coming" claim in its purest testable form.
- Explicit non-archetypes: nothing keyed on GEX walls/pin (that is path/vol context, and
  the production program already owns it); no IV-rank-as-direction; no signed-charm/DOI
  resurrections.

## 5. Adjacency and firewall statements

- vs w5b_tape_residual (FROZEN): w5b is a historical cross-sectional test of signed net
  premium → forward drift on a frozen 100-name universe, triggered ~Q1-2027. FOS is a
  forward-only, event-originated paper book with position geometry. FOS does not read,
  amend, or front-run the w5b claim; its record is not admissible as the w5b verdict.
- vs FS detector / flow_leaders: FOS consumes FS-0 events read-only; it never alters
  detector thresholds or board legs. flow_leaders remains a display board; FOS is a book.
- vs OPTIONS_ALPHA §4: FOS registers NO gate buckets and pays no FDR from that family;
  its statistics live entirely in its own read protocol (§7). If a FOS archetype is later
  promoted, THAT registration pays the family tax at promotion time.
- Signing honesty: every position's evidence bundle stamps side-confidence and
  signing_source; the suspension of tape-signing authority is disclosed on the sandbox
  surface. The sandbox is exactly the place where signed inference is allowed to act —
  paper consequences are the calibration.

## 6. Labels and grading

Per closed position: residual return vs SPY and vs sector at close of each of 1/5/10/20d
and at exit; MFE/MAE; stop-out vs time-stop vs target attribution; per-archetype and
per-side aggregates; matched-control comparison (same root-class, same vol bucket, random
entry dates) refreshed monthly. Event-archetype (FO-D) additionally labels: was there a
material news event in the window, and did direction match. All grading automatic,
nightly, same cadence as the existing plab books.

## 7. Read protocol and kill criteria

- No verdict language before n≥40 closed positions per lane (long/short read separately).
- Interim honesty reads at +30/+60/+90 calendar days (counts, hit rates, residuals — no
  promotion decisions).
- First promotion-eligible read: n≥40 per lane AND ≥90 days elapsed. Metric: mean residual
  10d return vs matched controls, hit rate, and drawdown; the short lane must clear the
  same bar as the long lane on its own record.
- Kill: any lane at n≥40 with negative mean residual AND hit rate <45% is closed (its
  archetypes retire); the sandbox itself sunsets after 2 consecutive failed reads unless
  the operator extends.
- The 2026-07-16 override expires with the sandbox: if FOS dies, the production laws stand
  unamended; if FOS wins, promotion is a NEW ruling scoped then.

## 8. Build packages

- FOS-1: origination engine (archetype rules over FS-0/tape_flow/live_flow) + calibration
  run on FS-1 cohorts + frozen thresholds doc appendix.
- FOS-2: `plab_flow_origin_v1` book wiring + nightly grading + matched controls.
- FOS-3: sandbox surface (admin card + Terminal tab section behind the experimental
  label, EN/ZH).
- FOS-4 (post-FPSS-fix): stream-sourced detection at full-universe breadth, `stream_feed`
  era.
