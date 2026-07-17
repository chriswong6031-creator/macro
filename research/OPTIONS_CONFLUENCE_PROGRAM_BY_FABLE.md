# Options Confluence Program

Author: Fable (adjudicated program of record)
Date: 2026-07-16
Status: RATIFIED as plan-of-record for the data/measurement lanes (P0–P1); product and
research lanes are display-tier until their own gates pass. No directional-alpha claim.
Supersedes/absorbs: see §2 adjudication table.
Origin: operator request (2026-07-16, MSFT/QuantData case) + Codex handoff
`research/OPTIONS_CONFLUENCE_ENGINE_HANDOFF_FOR_FABLE.md` + full repo audit (6 auditors,
5 adversarial verifiers) + 3-lens adversarial design review (constitution / ops / product),
all run 2026-07-16.

---

## 0. The one-paragraph mission

Build the point-in-time data spine and honest display surfaces that let Mastermind detect
QuantData-style option confluences (per-ticker signed-premium drift, IV-rank state, strike
topology, intraday IV/exposure evolution) across the FULL followed universe at multiple
horizons — while every directional claim stays inside the existing research constitution:
display/shadow until the ledger gates mature, confirmers may only lower confidence, the
Neural Web remains the sole originator, and one successful MSFT screenshot is a hypothesis
generator, not validation.

## 1. What the MSFT case actually was (defensible reading)

MSFT 2026-07-14 displayed: potentially bullish short-term *inferred* option flow (~$2.6M
inferred-bought 7/17 $400 calls, volume > prior OI), historically expensive vol (IV Rank
~100 on a ~30-DTE band), a dominant positive conventional-GEX concentration at the 7/17
$400 strike, and later price confirmation. Forensic problems (Codex §4 stand): the panels
mix expiries and maturities, the 7/17 expiry excluded the 7/29 earnings, several panels are
transformations of the same chain, and the screenshots are post-hoc selected. We can
already reproduce every panel's *measurement* from owned data. What we cannot yet do —
and what this program builds — is (a) see it live for any name (not 122), (b) replay it
point-in-time, (c) grade it against outcomes without leakage, (d) express it honestly.

## 2. Adjudication of existing roadmaps (binding)

| Existing doc | Ruling |
|---|---|
| `OPTIONS_SENSOR_CONTRACT.md` | **EXTENDED** → measurement-contract v2 (§6). Same contract, versioned; no parallel contract. Authority-tier ladder and reliability vocabulary unchanged. |
| `FLOW_SIGNAL_ML_MASTERPLAN` (FS-0/FS-1/FS-2 shipped 07-13) | **EXTENDED**. FS-0 stays the single alert/outcome ledger writer; alert-snapshot schema v2 rides it (detector_version + upstream-config hash per row). No third ledger. The Codex handoff's §6.7 "no closed learning loop" claim is **SUPERSEDED as stale** — FS-0/FS-1 shipped 2026-07-13 with a populated 7.3M-event graded cohort store. |
| `OPTIONS_ALPHA_MASTERPLAN` §4 registry | **AMENDED later, not now.** New bucket registrations (S-TOPO-SIGMA, S-IVMOVE, S-LEADCHASE) are DEFERRED to a dedicated registration PR after the P0.5 probes, with full mechanics: enlarged-family BH-FDR arithmetic (28 → N restated), A10 gate currency, A9 single-writer stamps, RUL-2 adjacency paragraphs (S-TOPO-SIGMA vs S-WALL/S-PIN_RISK; S-IVMOVE vs S-SKEW_DECEL/S-CWIV; S-LEADCHASE vs O-OPT-1/FLW-1/FS crowdedness), and per-bucket era grids keyed to actual data availability (single-era 2026→ for live-accrual features unless a verified intraday retro-backfill exists, registered BEFORE any harness run). Era partitions of the RATIFIED amendment apply only to the greeks/OI families they cover. |
| S-NETDRIFT-X (draft bucket) | **DROPPED from registration.** Per-ticker signed-premium extremes → forward outcomes sits inside the FROZEN `OPTIONS_TAPE_RESIDUAL_PREREG_2026-07-08` claim territory (universe frozen, auto-trigger ≥100×250d, ~Q1-2027). The Net-Drift *panel* ships as display (no outcome grading); the *bucket* waits for w5b's trigger or a separate Fable ruling with an explicit RUL-2 adjacency + non-front-running clause. |
| `FLOW_LEADERS_DESK_MASTERPLAN` | **AMENDED narrowly, three-way split**: (a) conform-to-registration repairs where builder wiring diverges from registered legs (e.g. A5 price-leg inputs not wired) — documented bug fixes, no re-registration; (b) cold-start legs (A1 recurrence ≥5 sessions, A2 ≥20 obs, A4 tape accrual) — WAIT for accrual, they are null by design; (c) lead/chase + topology-context land as **display-only context chips** (non-fire-qualifying, B4 precedent). The registered fire rules (A1∧A8∧≥1{A2,A3}) are NEVER loosened to make fires appear; the FL-R6 frozen leg sets and the FLW 2026-10-15 first read stand untouched. |
| `LIVE_FLOW_PRODUCTION_ROADMAP` | **AMENDED**: the U-TAPE stream daemon (§4) supersedes the intraday `live_flow_poller` as the live source once it survives 5 full sessions (poller stays primary until then, fallback after). The P2.x EOD bulk-REST tape builders are **RETAINED** as the historical/gap-heal plane (they still serve FL-R11 W5b episode backfill and FS-1 tape_recon; the stream cannot backfill). P2.2/P2.3 (vendor-IV → opt_iv_rank_252) remains the chartered A9 unlock lane — see §7 WP-IVR. F-B's default-360 universe ruling is REOPENED by explicit operator ask — see §5 U-FULL. F-D license filing (P0.6) is pulled into this program's P0. |
| `OPTIONS_OPEX_VANNA_CHARM_*` (findings + adjudication) | **CONSUMED.** S-FRONT-CHARM / S-VANNA-RELIEF registered buckets are the positioning-family foundation; the kills (signed-charm, charm-intensity narratives, DOI-directional, skew-decel-bullish) bind every feature list in this program. |
| `O_OPT` / `EXIT_CROWDING` preregs | **UNTOUCHED.** Frozen; the confluence program registers nothing in their claim territory. |
| MomoEdge/Prophet `MASTER_BUILD_DOCKET` | **AMENDED** per §8: Prophet origination is NOT swapped in this program (blocker ruling). The scanner surface is a new display desk; Prophet changes ride a separate stamped, era-split step. |
| Codex handoff `OPTIONS_CONFLUENCE_ENGINE_HANDOFF_FOR_FABLE.md` | **ABSORBED** into this doc: its 14 binding epistemic laws are adopted verbatim (§3), its Phase-0 exit gate is adopted (§10), its §6.7 claim superseded, its §18 "no UI before docket items 1–10" is adopted for *new-data* panels but display-parity panels on EXISTING data are exempt (product ruling — they carry no alpha claim). |

## 3. Binding laws (inherited, non-negotiable)

1–14. The Codex handoff §20 epistemic laws verbatim (calls-bought = inferred; vol>OI ≠
opening; GEX = proxy under assumed sign; positive GEX ≠ upward pressure; static DEX ≠
future demand; IV Rank ≠ direction; correlated transformations ≠ independent confluences;
horizon alignment; no same-day OI; no later-evidence leakage; immutable snapshots; Greek
topology = display/path/vol until gauntlet-passed; the system may abstain; screenshots are
hypotheses).
15. F7: flow direction is permanently soft on bar data (0.41); tape signing is under an
ACTIVE SUSPEND (0/3 extension sessions ≥0.75). NBBO-at-trade from the stream gives
quote-rule *execution classification* (measurement, FS-R6a) — direction authority does NOT
follow; re-enable requires a passed calibration extension + Fable adjudication, and the
stream source gets its own calibration session before signed shadow features accrue from it.
16. NW is the sole originator; Prophet manages; LLMs narrate/de-escalate. Options families
are display/confirmer tier and may only LOWER confidence pre-gate (doctrine §2.1, RO-2/RO-3).
17. AVOID-not-SHORT: no bear/short origination lane anywhere in this program. Bearish
options evidence expresses as AVOID/de-escalation annotations only.
18. Gate maturity (~2026-10-15 clocks) yields VERDICTS; survivors become caution-only
confirmers first — never originators by default.
19. Single writers: FS-0 for alert/outcome rows; `scripts/stamp_options_state.py` for stamp
columns; nightly Prophet job for its ledger. New sources get new source tags
(`stream_feed` ≠ `live_feed`) and are never pooled across detector_version in any
training/calibration table (FS-R4).
20. Probe-before-commit (house law): no architecture commitment on unmeasured vendor
behavior. §5's lanes are gated on the P0.5 probe results.

## 4. Verified current state (what the audit established, 2026-07-16)

- **Deep store**: 60 GiB at `~/theta-ops-wt/data/thetadata_eod` — 380 roots × 2012–2026
  (greeks 2017→, 51 GiB / 84.8%); 90.3 B/contract-day across the 3 tiers; ~494k
  contracts/day tracked (~34% of the ~1.45M-contract market). Only 47 roots refresh
  nightly; the ~333-root tail is **frozen** at backfill dates (root cause: the resume state
  marks the current year "completed" mid-year).
- **Live**: `com.mastermind.liveflow` launchd, 122 roots, configured 120s but **measured
  ~35.7 min/cycle** (terminal rejects current-day wildcard → full-day re-pull, 244
  req/cycle; meta.json cadence_sec_measured=2140.8). Raw tape aggregated inline and
  discarded everywhere (T2a law); the build_tape_flow_daily "raw retention" writes only a
  byte-count manifest — the docstring's "bytes on R2-plane" is FALSE today.
- **Store resolution**: ≥11 fragmented sites, 4+ fallback chains, one silent-empty path
  (engine/thetadata_store) that already produced a real incident: the published
  `site/basketdata/options_witness.json` (as_of 07-14) is 0/18-themes-suppressed because a
  GH runner resolved an empty repo-local store.
- **IV Rank**: `options_entry_state.iv_rank_252` structurally null (A9, tests enforce);
  `options_hub` computes a real iv_rank_252/iv_rank_all nightly to R2 `options_hub/vol/`.
- **Prophet**: originates ONLY from `us_standouts.json` `buy[]` (top-120 *alpha-sorted*
  trend rows + recovery rows, of an S&P-1500-ish universe), bull-only, ≤6 new plans/night.
  The operator's structural-blindness complaint is confirmed; the alphabetical cap is a
  defect on the price side (a worse "A" name can crowd out a better "W" name).
- **Terminal (product)**: /flow hub, 10 visible tabs; genuinely intraday = Tape/Tide/Desk
  (+Prophet 5-min marks); Screener/GEX/Prism/Leaders/Radar/Vol are nightly EOD. QuantData
  parity: Net Drift = market-wide HAVE / per-ticker partial (no price overlay, top-40 cap);
  Interval Map MISSING; Exposure-by-Strike bars HAVE but single overwritten EOD snapshot
  (no scrubber history); Heat Map partial (EOD matrix + intraday chain-heat campaigns);
  IV Rank HAVE (EOD); Volatility Drift MISSING (no intraday IV series anywhere).
- **Ledger infrastructure**: FS-0 event ledger + grader and FS-1 historical cohorts
  (7,336,004 events, 383 roots, 2012-06→2026-07) SHIPPED 07-13. flow_leaders board fires 0
  by cold-start design (A1/A2/A4 accruing) — not (only) by defect.
- **ThetaData PRO entitlements** (docs-verified): tick history → 2012-06-01, 8 concurrent
  REST, quote streams capped 15k contracts, **Full Trade Stream = every OPRA option print,
  PRO-only, no cap** (ws :25520 /v1/events, STREAM_BULK). The port is LISTENING on the
  running terminal and `~/theta/config.toml` sets ws_port=25520 — but the repo has ZERO
  websocket consumer code: the stream daemon is greenfield.
- **Ops envelope**: everything runs on one Mac (terminal + store + 8 launchd lanes + 4 GH
  runner agents + the live bot). Boot volume free: ~283 GiB. Overnight window 18:00–01:00
  PT is empty. The idle-Mac-Studio migration script exists but was never executed — no
  plan step may assume that capacity until it runs.

## 5. Data architecture — tiered universes (probe-gated)

All lanes: ThetaData PRO, local terminal v3 :25503 / ws :25520. Concurrency allocation on
the 8-cap (explicit): nightly lanes 6 (+2 headroom, collector law); RTH snapshot loop ≤1
while the poller runs, ≤2 after the poller retires; stream daemon = websocket (outside the
REST cap).

**U-FULL — full-universe daily EOD spine.** Full optionable universe — **measured
2026-07-16: 15,636 roots total, 12,730 clean A-Z tradeable roots** (probe; the ~4–5k
assumption was 3× low; storage keys sized for 15.6k) — for **EOD OHLCV + OI**; **greeks
for a liquidity-ranked top ~1,200** (explicit amendment of the F-B
default-360 ruling; reopened by operator ask (e); the illiquid ~3k tail adds noise to
cross-sectional reads while tripling greeks cost). Mechanics: day-increment refactor of
`backfill_thetadata_eod` — state schema v2 `{root: {last_date, completed_years}}` +
migration that un-freezes falsely-completed current-year entries (fixes the 333-root
freeze); root-level executor at 6 workers; contract-key latest-wins upsert dedup
(root,expiration,strike,right,date), NOT full-row (repair_thetadata_dedup docstring gets a
note that post-refactor near-dupes are the append lane's responsibility); layout decision
= keep year files + upsert, accept the growing rewrite cost, revisit at Q4 with
day-partition staging + weekly compaction if nightly rewrite I/O exceeds budget. **Two
lanes honoring the OI timing law**: evening EOD+greeks (overnight window, post-witness —
probe confirmed same-day EOD is NOT served mid-session, HTTP 472; post-close availability
time to be measured once at ~16:30–18:00 ET), ~04:00 PT OI lane (post-OPRA-publication,
pre-RTH). `_manifest.json` completeness gets a re-specified predicate (per-root
`last_date` watermark) so R8-style "no reads until complete" consumers (FS-1, O-OPT,
EXIT-CROWD) don't read mid-increment stores. Cost: +117–144 MB/day, 30–36 GB/yr — trivial
(contract count, not root count, drives bytes); request budget at 12.7k roots ≈ 25–38k
req/night ≈ 1.5–3.5 h at 6 workers (measured 0.11–0.55 MB/s; re-benchmark after the
refactor).

**U-TAPE — full-universe live trades via Full Trade Stream.** PROBE STATUS (2026-07-16):
the websocket infrastructure is real (ws :25520 `/v1/events` connects; STREAM_BULK
OPTION TRADE subscribe accepted with no entitlement rejection; account is Options
PROFESSIONAL; terminal config carries a 1M-message stream buffer) but **zero trades flow
today: the terminal's upstream FPSS login fails `INVALID_CREDENTIALS` in an endless retry
loop** — an OPERATOR-side credential/enablement fix (terminal is launched with the
`THETADATA_API_KEY` env var — was `--api-key` argv until the 2026-07-16 plaintext-argv fix;
FPSS wants a credential it doesn't have; fix in run_theta_terminal.sh / account portal),
not a tier problem. Note: the probe's subscribe left the retry loop running (~2 log lines
per 2.4s until restart) — restart the terminal AFTER the close (the live poller depends on
it mid-RTH). Build proceeds against the documented message schema; the 5-session soak
clock starts only after FPSS auth works and a re-probe captures real trades.
New always-on ingestion daemon (greenfield): ws :25520 `/v1/events` STREAM_BULK OPTION
TRADE → append-only raw trade+NBBO-context parquet + per-contract minute aggregates →
derived live feeds.
Requirements carried from handoff §6.1 (these ARE the acceptance criteria): sequence/batch
ids, duplicate suppression, dropped-message counter wired to the config.toml stream buffer,
latency + missing-event telemetry, reconnect-with-gap-accounting + **gap-heal via REST
bulk_trade_quote re-pull of the outage window**, run_status/tripwire registration, orjson +
batched decode with a compiled-parser escape hatch. Deploys from a dedicated `~/tape-ops-wt`
worktree (TCC law), KeepAlive=true + ThrottleInterval + RTH-aware idle + log rotation
(terminal_v3.log is already 123 MB unrotated — rotate that too). Retention (written
budget + tripwire): raw hot window **7–14 days local** with verified-upload-then-delete to
R2 (HEAD/size check before delete); minute aggregates permanent for the followed set; full
raw windows around alerts/events permanent on R2, with an explicit growth tripwire (A4
pattern). Rollout: poller stays PRIMARY until the daemon survives 5 full sessions with
clean gap ledgers; then poller becomes fallback. Stream events carry `source=stream_feed`
+ their own detector_version; never pooled with `live_feed` cohorts. Baselines: same-time-
of-day per-ticker flow baselines are BACKFILLED from FS-1 tape_recon (already built,
resumable) so Net-Drift panels and the MSFT reconstruction have historical controls from
day one — no cold start.

**U-CHAIN — intraday chain greeks/IV series, top ~150 active roots.** PROBE RESOLVED
(2026-07-16, measured): the lane is buildable, with a two-path design.
- **Live path = RTH snapshot loop** — `/v3/option/snapshot/greeks/first_order` and
  `second_order` DO accept `expiration=*` and are fast (full SPY chain: 0.96s / 14,065
  rows first-order; 0.83s second-order incl. gamma/vanna/charm; OI snapshot 0.21s). A
  full 150-root × 2-order sweep ≈ 300 requests ≈ ~2.5 min wall at concurrency 2 — a
  15-min cadence fits easily inside the allocated cap share (≤1 concurrent while the
  poller runs). Snapshots are persisted as dated strike×time frames (this IS the Interval
  Map / Vol Drift data).
- **Retro/gap-heal path = history endpoints** — `/v3/option/history/greeks/{first,second,
  third}_order` accept `interval=15m` (and `1m` at ~31 MB/expiration-day) but reject
  `expiration=*`: one request per ACTIVE expiration (SPY = 34, mid-caps ≈ 17; 11–17s
  each; multi-day ≤1 month per call per expiration). **Intraday greeks history floor ≈
  2017** (2017-07-19 exists, 2016-07-13 does not; EOD reaches 2012). Retro-backfill is
  therefore bounded and real but priced: reserve it for the research set (~24–50 roots ×
  2023→) with its own budget; a separate era registration lands BEFORE any harness run
  touches retro data. Deep-history full-chain pulls can exceed 120s/expiration — generous
  timeouts.
This lane powers Interval Map, Volatility Drift, and the Exposure-by-Strike scrubber;
~0.4–1 GB/day forward.

**REJECTED**: full-universe continuous NBBO quote tape (30–270 GB/day; multi-TB/yr; the
stream's NBBO-at-trade context covers execution classification). Rejected pending a
dedicated firehose vendor + separate storage tier if ever needed.

**Storage/compute summary**: R2 $0.015/GB-mo (1 TB ≈ $15/mo — never the constraint). Local
disk is the constraint: 283 GiB free, so the 7–14d hot-tape window + a disk-free witness in
the healthcheck tripwires (fail LOUD). The current Mac CAN absorb the stream daemon +
snapshot loop (1 WS + parquet appends; overnight REST window is empty); the Mac Studio
migration is a P2 optimization, not a P1 prerequisite.

## 6. Measurement contract v2 (P0)

Extends `OPTIONS_SENSOR_CONTRACT.md` (same doc, version bump; schemas registered in
`config/synapse.yml`): units/sign/timestamp/spot-sync conventions for every published
number (GEX per-$1 vs per-1% vs raw; premium vs delta-notional; strike distance in
implied-sigma); source lineage stamps on every artifact (store path, formula version,
information cutoff); RO-1 evidence-quality vocabulary ({full,partial,thin,stale} +
structurally-null) emitted by the canonical resolver so consumers inherit the honesty
conventions; freshness tier labels (live / radar-active-live / T+0-EOD-reconstruction)
required on every UI panel fed by these planes.

## 7. Phase plan and work packages (dependency-ordered, PR-sized)

**P0 — measurement + integrity (now):**
- WP-RESOLVER: one canonical `resolve_thetadata_store()` in engine/thetadata_store.py —
  env → data_dir → ops-wt known path, existence-checked, `required=True` default for
  production consumers (fail LOUD; the silent-empty path is REMOVED, not deprecated),
  lineage + evidence_quality emission; migrate all ~11 sites (enumerated in the audit with
  anchors); regression test = the options_witness empty-store incident shape.
- WP-GEX-SNAPSHOTS: stop overwriting `options_hub/gex/{ROOT}.json` in place — retain dated
  per-strike snapshots (R2 `options_hub/gex_history/{ROOT}/{DATE}.json` + latest pointer).
  Near-zero cost; starts scrubber/topology history accruing immediately (S-TOPO-SIGMA
  needs it; PIT-required).
- WP-TAPE-TRUTH: make raw retention honest — implement the R2 raw plane for ETF anchors +
  episode windows via a dedicated verified uploader (upload → HEAD-verify → delete;
  publish_r2's sync model + 100-file guard is the wrong tool), or (if deferred) fix the
  false docstring/manifest claims. Implementation chosen: minimal true retention.
- WP-PROBE (P0.5): **DONE 2026-07-16** (mid-RTH, measured): universe 15,636/12,730;
  intraday greeks history per-expiration at 15m/1m, floor ≈2017; snapshots wildcard-exp
  fast (SPY full chain <1s incl. second_order); stream subscribe accepted but FPSS auth
  broken (operator fix) — results filed in `research/THETADATA_PROBE.md` §v3-2026-07-16.
  One residual measurement: post-close same-day EOD availability time (one evening check).
- WP-CONTRACT: measurement contract v2 (§6).
- WP-MSFT-ACCEPT: deterministic MSFT 2026-07-14 reconstruction script
  (`scripts/research/msft_20260714_reconstruction.py`) — IV rank (both conventions), $400
  GEX concentration with the unit contract making vendor-figure differences explainable,
  flow observation vs FS-1 baseline. Exit gate verbatim from the handoff: same timestamped
  state reproduced twice from immutable inputs; GEX unit differences explainable; no
  future OI / later screenshot state leaking into the initial signal.
- WP-LICENSE: file the ThetaData licensing terms in-repo (LIVE_FLOW P0.6, still unfiled)
  + the fused-surface pre-publish check note; confirm whether Full Trade Stream is inside
  the current PRO sub before U-TAPE build starts.
- WP-DOC-HONESTY: stale-claim sweep (options_matrix "unscheduled" docstring; repo
  keepalive copy 22-vs-47 roots drift; tape_flow docstring if WP-TAPE-TRUTH defers).
- WP-IVR (chartered lane, sequenced after #1363 confirmation): the A9 iv_rank unlock runs
  EXACTLY per LIVE_FLOW P2.2/P2.3 — vendor IV as source, stamps only via
  `scripts/stamp_options_state.py` (`source:vendor, reconstructed:false`), BS-inversion
  retained as audit tool, options_entry_state fields populated from the same source, the
  null-enforcing tests REPLACED (not deleted) with source/coverage assertions **in that
  same dedicated PR**, S-IVR §4 row amended with the actual source + 2018→ warm-up note,
  §8 status-log entry. Precondition checks in the PR: manifest-complete confirmation +
  #1363 greeks-dedup repair verified. NOT bundled with any other work package.

**P1 — data unlocks (gated on P0.5 probes):**
- WP-STREAM: U-TAPE daemon (§5 requirements are the acceptance list) + 5-session soak +
  stream-source signing calibration session (shadow only; no signed features before it).
- WP-UFULL: day-increment refactor + two lanes + state migration + tail unfreeze +
  re-benchmarked nightly budget.
- WP-UCHAIN: per probe verdict (history-endpoint lane or snapshot-loop fallback).
- WP-SNAPLEDGER: alert-snapshot schema v2 on FS-0 (feature snapshot ids, formula/model
  versions, horizon, invalidation, detector_version + config hash) + replay harness that
  reconstructs any historical alert from data available at its timestamp.
- WP-NETDRIFT-PANEL: per-ticker Net Drift with price overlay in the Terminal — for the
  live 122-root set immediately (existing poller ticker minutes + /api/intraday join;
  freshness label "live (≈36-min effective until stream)"), full universe when WP-STREAM
  lands. Display-tier copy laws apply (~soft direction language).

**P2 — preregistered research (parallel with P3 product, NOT blocking it):**
- Confluence hypothesis prereg: feature families fixed before outcome inspection
  (families: observed-flow, lead/chase, positioning topology, vol-surface/event state,
  underlying confirmation — with the dependency-graph cap: correlated transformations of
  one source count once); price-only / flow-only / topology-only / vol-only / combined
  baselines; matched controls; purged+embargoed walk-forward; horizon labels incl.
  residual returns (5/30/60m, 1/5/10/20/60d), triple-barrier, MFE/MAE, strike-touch, pin,
  realized-vs-implied; executable-P&L (entry ask / exit bid). Runs through the existing
  gauntlet discipline; §4 registration PR (with full FDR mechanics) lands here.
- The FDR family-enlargement tax on existing accruing buckets is stated explicitly to the
  operator at registration (28 → N; top-rank BH threshold tightens).

**P3 — product expression (display-tier, starts as soon as its data dependency lands):**
- SCANNER DESK (new tab; NOT named "Radar" — collision with Leader Radar): full-universe
  cross-sectional screener. Per-axis columns (flow z vs FS-1 baseline, IV-rank state,
  wall distance in implied-σ, front-expiry concentration, relative strength, event
  context), K-of-N tri-state boolean chips, ONE argued sort quantity (FL-R2/FL-R6
  precedent), contradiction flags rendered as first-class UI (the §10 dependency-cap law
  as product: five OI transformations ≠ five confirmations), NO fused composite anywhere
  liftable (RO-2). Event/OPEX context is display-only and never advances a candidate
  (RIC-R3). This surfaces non-standout names IMMEDIATELY without touching origination.
- PROPHET (two-step, constitution-compliant): Step 1 — widen the PRICE-side pool defect:
  the us_standouts buy-lane alphabetical [:120] cap is replaced by an explicit ranked cut
  on the same gauntlet-lineage conviction fields (a standouts-board change, price-first
  territory); Prophet mechanics untouched. Step 2 (separate, later, own ruling) — IF the
  scanner's shadow record earns it after the 2026-10-15 reads, Prophet origination may
  consume a widened deterministic price-first pool with options families as
  confirm/de-escalate only; any such flip stamps origination_version + source_engines on
  every plan/ledger row and splits eras (or runs a parallel shadow book). NO bear lane
  (law 17); bearish evidence renders as AVOID chips on candidates and held names.
- PANEL DELIVERY (each with freshness-tier label): Interval Map + Volatility Drift +
  Exposure-by-Strike scrubber from U-CHAIN (scrubber depth starts at P0 via
  WP-GEX-SNAPSHOTS); Heat Map = declared satisfied by Prism matrix + chain-heat campaigns,
  with one gap noted (intraday full-grid refresh rides U-CHAIN, same lane as Interval
  Map); IV Rank timeseries already served (options_hub vol column) — surfaced more
  prominently in the scanner.
- ALERT LANE: handoff §13 alert contract, display-tier language, via the FL masterplan's
  parked alert spine (Discord/push). Every alert row lands in FS-0 with the v2 snapshot
  schema. Kill-switch flag per new public surface; EN/ZH i18n per house law.
- NW/bot consumption: **PARKED** per rails §10/GAP-U4 until ~2026-10/12 gates. The bot
  reads nothing new from this program until then.

**P4 — governed limited deployment:** per handoff §17 Phase-4 gates (risk limits, kill
switches, drift monitoring, no unresolved PIT leakage, rollback paths). Not scheduled.

## 8. Ops rules for new lanes

Deploy worktrees in $HOME (TCC law), .env copies, plists in local PT with ET equivalence
commented (liveflow convention); evening ordering pinned: day-increment writer runs in the
empty 18:00–01:00 PT window after theme-options-witness, never concurrent with
optionshub/matrix/baseline store reads; every new lane registers run_status + audit
tripwires (P0.7 pattern) including the disk-free witness; terminal restart drops the
stream — daemon must detect + gap-heal + ledger the hole. Terminal API key currently
visible in process argv — move to env/config injection (tracked as a separate security
chip). Deep store has NO automated offsite copy — R2 mirror lane for `thetadata_eod` is
added to the overnight window (publish_r2 registration exists; needs a scheduled caller).

**Operator actions queue (from this program):** (1) fix FPSS stream credentials
(run_theta_terminal.sh / ThetaData account portal) and restart the terminal post-close —
also clears the probe-tripped retry loop; (2) confirm Full Trade Stream is included in the
current PRO subscription in writing (WP-LICENSE); (3) optional but recommended: execute the
delivered Mac Studio runner-migration script before P2 to relieve the single-host
concentration; (4) one-time evening check of post-close same-day EOD availability.

## 9. What this program does NOT claim

No options family predicts direction today. The strongest owned evidence remains
volatility/path-shaped (front-expiry concentration, vanna-relief). IV Rank 100 is a cost
state, not a signal. The MSFT case motivates the *measurement spine*, not a trading rule.
Anything that fires on the scanner is a display-tier candidate for the research program,
graded through FS-0 — and the system is allowed to abstain.

## 10. P0 acceptance tests

1. `resolve_thetadata_store(required=True)` raises loudly on an empty/absent store;
   options_witness lane cannot silently publish 0/18 again (regression test).
2. Dated GEX snapshots accrue for ≥2 sessions with stable schema + latest pointer intact.
3. Raw-plane manifest rows correspond to actual R2 objects (HEAD-verified) for one ETF
   anchor day + one episode window.
4. THETADATA_PROBE.md contains measured verdicts (stream msgs/sec + sample message +
   entitlement; greeks×interval matrix incl. second_order; same-day EOD timing;
   universe count).
5. MSFT 2026-07-14 reconstruction: reproduced twice from immutable inputs, byte-identical;
   GEX unit variants tabulated per contract v2; no post-14:00-ET-of-alert-day inputs.
6. License terms filed; Full Trade Stream entitlement confirmed in writing.

---

*Probe results appendix (P0.5, run 2026-07-16 12:04–12:17 PDT, mid-RTH): measured and
folded into the §5 lane verdicts above; full endpoint-level evidence filed in
`research/THETADATA_PROBE.md` (v3 probe section, 2026-07-16). Raw response CSVs retained
at `/tmp/theta_probe/` on the ops host for one week.*
