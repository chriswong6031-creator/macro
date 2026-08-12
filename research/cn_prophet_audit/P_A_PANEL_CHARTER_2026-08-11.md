# P-A charter — the actual Prophet pick panel: read contract + two-phase study design (2026-08-11)

Status: **ACTIVE charter** for wave P-A of the CN limit-move alpha program
(`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md`). Authority:
`none_research_display_only` — nothing here ranks, sizes, gates, alerts, or trades.
Governing rulings unchanged: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` and the amended
reconciliation ledger. Written by the master session from a verified 2026-08-11 cross-repo
census (facts verified directly against `origin/main` @ `b8af2c54d78`).

---

## §0 The correction this charter makes

Program home v2 chartered P-A as *"requires the Terminal cross-repo read contract for
Golden Oracle pick/state history."* The census (§1) falsifies that premise: **no
Terminal-side CN pick/state history exists, and none ever did.** The actual pick panel
behind the operator's genesis claim — "Prophet ranked 300363.SZ #1 the day before its 20%
board" — lives **in this repo**, as an append-only point-in-time ledger written nightly by
`engine/china_standout_track.py`. P-A therefore needs no cross-repo plumbing at all for
its core question. The v2 home's P-A row is amended per §6; the Terminal-side forward
accrual becomes ore (§7), not a dependency.

## §1 Census verdict (2026-08-11, both repos)

- The Terminal's Golden Oracle (`signal_layer/confluence.py` / `confluence_v2.py` in
  charting-app) is **server-precomputed nightly for ~34 US/crypto flagship names only**;
  its sole durable output (`terminal/public/data/<SYM>.slice.json`) is overwritten in
  place on the VPS each night, outside git. **Zero `.SS`/`.SZ` slice files exist or have
  ever existed.** The Terminal's Prophet tab proxies an external backend + R2 artifacts;
  no CN-specific code path exists in that repo (`terminal/components/prophet/*` greps
  clean for china/cn/A-share).
- Consequence: a *retroactive* Terminal-sourced CN panel is impossible; only a forward
  accrual could ever create one (ore, §7). W-P0's transcription (its `CONFLUENCE_SPEC`
  pin, deviations declared) remains the only way to evaluate the oracle math on CN
  history, and it already exists.
- The one standing cross-repo signal contract (`site/factordata/contracts/golden_signals.json`,
  produced by `scripts/export_signal_contracts.py`, consumed by charting-app
  `signal_layer/golden_gate.py`) is an engine-parity CI fixture (3 symbols, fixed window)
  — not a pick history, and not extended by this charter.

## §2 The panel — read contract

Two in-repo PIT stores constitute the panel. Both are **read-only inputs** to this
program; the standout-track program owns their write path and their defects.

**A. `data/china_standout_track/board.parquet`** — the surfaced board (what the operator
saw). Append-only, keep-first per (date, ticker), "a logged rank is never overwritten"
(engine docstring). As of `b8af2c54d78`: 1,485 rows, 27 sessions 2026-06-30 → 2026-08-11,
median 60 names/session. **Five definition streams share the file** — a definition
migration, not one panel:

| board_definition | sessions | span | rows | distinct names |
|---|---|---|---|---|
| legacy | 18 | 06-30 → 07-29 | 1,082 | 464 |
| cn_prophet_v2 | 5 | 07-30 → 08-05 | 72 | 47 |
| cn_prophet_v2_shadow | 4 | 08-06 → 08-11 | 53 | 35 |
| cn_prophet_v3 | 4 | 08-06 → 08-11 | 96 | 61 |
| cn_reversal_watch_v1 | 6 | 08-04 → 08-11 | 182 | 81 |

Rows carry the engine's own footprint stamps (`washout`, `washout_2w`, `species_id`,
`coiled*`, `setup`, `ext_score`, `hold_state`, `stage`, tier/lane) and a PIT regime
vector (`own_market_regime` from the SA-W2 keep-first store).

**B. `data/china_prophet_rank/candidates.parquet`** — the pre-gate scored universe.
9 sessions 2026-07-30 → 2026-08-11, ~1,657 rows/session, v2+v3 definitions,
`raw_eligible` True for 1,777 of 14,190 rows, with `gate_reason` strings (themselves
footprint receipts — "no 200-reclaim/hold" is an under-200DMA read).

**Contract terms (binding on every P-A instrument):**

1. **Read-only; vintage-stamp** the data commit of both parquets in every receipt (A4
   ancestry guard applies).
2. **Per-definition conditioning is mandatory.** A `board_definition` is a different
   instrument; pooling across streams is the cadence trap in its plainest form. Same-day
   cross-definition collisions on one ticker: the instrument must verify and stamp the
   effective keep-first key before using any collision-affected row.
3. **Embedded outcome columns are quarantined.** `fwd_mfe_*`, `terminal_state_*`,
   `post_cushion_breach` run on the **dividend-adjusted** `china_stocks` plane by the
   engine's own statement ("uses the same dividend-adjusted close series…"), and the
   ledger has a receipted history of a silently restated entry level. No P-A read may
   cite them for anything; board outcomes are re-derived per term 4. The `level` column
   carries the engine's own pre-settle stamping caveat and is likewise not evidence.
4. **Board outcomes re-derived lawfully**: first-board events (N: 0→1) come from
   `data/china_stocks_raw` via the tolerant detector inside the instrument — the W-P0
   pattern — never from embedded columns, never from any withdrawn artifact.
5. **The two streams contradict and must not be reconciled silently.** Same-day
   board-vs-candidates disagreement is a known, formally flagged defect (the 300363 case
   study is stamped `STOP_SHIP_UNVALIDATED_QUANTITATIVE_EXHIBIT`; its finding #1 is this
   contradiction). P-A reads report per-stream. Reconciliation belongs to the
   standout-track program.

## §3 The genesis receipts (verified at `b8af2c54d78`)

The row-pair, quoted from the PIT stores:

- **board.parquet 2026-08-05**: `300363.SZ`, `board_rank=1`, `cn_prophet_v2`,
  lane `featured`, tier T2, `prophet_score=90.32`, **`washout=True`, `washout_2w=1.0`,
  `species_id='cn_washout'`**, `prophet_bottom_quality=0.4`, `hold_state='launched'`,
  `own_market_regime='Q3'`.
- **candidates.parquet 2026-08-05 (same session)**: `score_rank=367`,
  `raw_eligible=False`, `buyable=False`, `gate_reason="buy blocked by filter:
  counter-trend, no 200-reclaim/hold"`, `prophet_score=44.07` — decaying 41→26→22→16
  across 08-06 → 08-11.

Reading, and the program thesis in one row-pair: **the washout-species lane surfaced the
name at rank 1 while the buyability gate blocked it for being exactly what it was — a
counter-trend name under its 200DMA.** Prophet's quality floor rejects the state this
program exists to rank inside. (Price/return claims for the case remain withdrawn per the
case-study stamp; the board outcome itself is re-derived lawfully in P-A1.)

## §4 Honest-N and the two-phase design

The panel is **27 sessions, one era, entirely in-sample of the current regime** — and the
genesis stream (`cn_prophet_v2`) is frozen at 5 sessions, superseded by v3 on 08-06. It
will never support inference. Therefore:

**P-A1 — descriptive read (commissioned with this charter).** Display-tier, counts and
episode lists only, **no lift headlines, no t-statistics, no inference rows**:

- Footprint presence at pick time: W-P0's pinned washout/confluence/sector definitions,
  re-derived from `china_stocks_raw` availability-stamped at each pick date, versus the
  engine's own stamps (`washout`, `species_id`) — an agreement matrix per definition
  stream. Where the two washout notions diverge, list the names; divergence is data, not
  error.
- First-board incidence among panel names within H ∈ {5, 10} sessions of the pick,
  re-derived per contract term 4, per definition stream, with the panel-session count and
  distinct-name honest-N printed beside every count.
- The 300363 case row-pair (§3) traced end-to-end as the worked example.
- A stated "what this does not establish" section: no selection-skill claim, no
  comparison to any non-panel baseline, nothing about the withdrawn W1–W3 constructions.

**P-A2 — accrual-gated battery (pre-stated now to avoid cadence peeking).** The ledger
accrues nightly for free. When a single definition stream reaches **≥120 distinct panel
sessions AND spans ≥2 `own_market_regime` segments**, run the W-P0-style within-panel
ranking battery on that stream (f3/f7/f1 with the directions preregistered in W-P0 §6,
era-preserving permutation nulls, date-clustered t). Until a stream crosses the trigger,
no inference is computed on it — partial peeks are forbidden, and this paragraph is the
preregistration of that discipline. At current cadence the earliest crossing is
`cn_prophet_v3` around 2027-02.

## §5 P-A1 instrument requirements (builder spec)

File: `research/cn_prophet_audit/pa1_panel_read.py`; receipts
`PA1_PANEL_READ_2026-08-11.{md,json}`. Requirements, each a "not done unless":

1. Footprint definitions **imported or copied with a pin** from
   `research/cn_prophet_audit/washout_onset_w1.py` (name the source lines in the pin
   comment; if the module is not import-safe, copy verbatim and say so). No third
   re-derivation of the oracle math.
2. Verify battery with **mutation probes** (a check that cannot fail is a defect),
   minimum: (a) PIT availability of every footprint at every pick date; (b) detector
   cross-check against `data/china_zt_pool` where coverage overlaps; (c) keep-first key
   verification on both parquets (term 2); (d) definition-stream disjointness of every
   table; (e) proof the instrument never reads the quarantined columns (term 3 — assert
   the frame is loaded without them).
3. `TZ=UTC` determinism: consecutive runs byte-identical; vintage stamps with the A4
   ancestry guard (stamp must be an ancestor of `build_head_sha`, refuse to write
   otherwise).
4. STOP-SHIP compliance: zero references to withdrawn artifacts (grep-verified in the
   receipt); display-tier language throughout; banned-vocab rules apply to any prose.
5. GitHub annotations, if any, via bare `print("::warning …", flush=True)` — never a
   logger.
6. Every count table prints its honest-N (panel sessions, distinct names, episodes)
   inline, and the frozen-stream fact (§4) appears wherever `cn_prophet_v2` is shown.

## §6 Program home v2 amendment (applied when both files are on main)

- §3 P-A row becomes: *"P-A | Do the W-P0 footprints describe / eventually rank the
  actual Prophet pick panel (`data/china_standout_track/board.parquet` +
  `data/china_prophet_rank/candidates.parquet` — in-repo PIT ledgers; census 2026-08-11:
  no Terminal-side CN history exists)? | P-A1 descriptive read commissioned
  (`P_A_PANEL_CHARTER_2026-08-11.md`); P-A2 battery accrual-gated (≥120 sessions + ≥2
  regime segments per stream)."*
- §5 queue item 2 becomes: *"P-A1 descriptive read ships; P-A2 waits on ledger accrual —
  no cross-repo contract needed (charter §1)."*

## §7 Ore ledger (mapped, not built)

- **Terminal CN forward accrual** — charting-app's nightly `gen_slices_all.py` could emit
  CN oracle slices to a durable append-only store (census options: extend the
  `export_signal_contracts.py` pattern, or a repo-A accrual job reading served slices).
  Only worth building if production-feed fidelity ever becomes the binding question;
  W-P0's transcription covers the math today.
- **`gate_reason` taxonomy as footprint source** — the candidates ledger's block reasons
  are machine-readable washout receipts ("no 200-reclaim"); a parser would give
  gate-state × footprint joint tables for free in P-A2.
- **Two-stream reconciliation** — owned by the standout-track program; P-A only consumes.
- **Chips/minute joins** — P-C, post-backfill, unchanged.

*Related: `research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md` (program home),
`research/cn_prophet_audit/WASHOUT_ONSET_W1_2026-08-10.md` (W-P0, the pinned
definitions), `research/cn_prophet_audit/CASE_300363_FULL_CHAIN_2026-08-08.md`
(stamped exhibit; contradiction finding), `engine/china_standout_track.py` (ledger
owner).*
