# Seasonality program — session handoff, 2026-08-02

**For:** the next session (any account) continuing the Biopharma Seasonality
Intelligence program. Everything durable is in the repo; account-local memory is
NOT assumed. Read this top to bottom before acting — the baton in §3 is
time-sensitive.

## §1 Orientation — what this program is

Clean-room competitor to Seasonax (calendar-seasonality workstation), rebuilt on
honest statistics, aimed at biopharma. Three clocks: calendar (SHIPPED), catalyst
event (next), regime (later). It is a **separate program from BioCatalyst** (the
pharma pipeline-facts plane a Codex session is building) — two lobes that
interoperate through a written seam, never one merged codebase.

| Authority doc | What it pins |
|---|---|
| `research/SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md` | the full program: teardown, 8 lanes, acceptance gates, kill conditions |
| `research/STOCK_SEASONALITY_LANE2_DESIGN_SPEC.md` | the shipped surface. **Read the revision-log table at top first** — later sections override earlier ones; §12–§17 record what real-data probes and a built mockup changed |
| `research/SEASONALITY_BIOCATALYST_INTEGRATION_SEAM.md` | the BioCatalyst boundary: one-writer rules, field mapping, the `known_at ← transaction_from` invariant (NEVER `knowledge_cutoff`), sequencing |
| `mockups/refs/stock_seasonality/` | committed design references (`window_fan.html` is the signature; `variants.html` is what failed and why) |
| `scripts/verify_stock_seasonality_live.sh` | live-verification script (committed with this handoff); prints PASS/FAIL with observed values |

## §2 State at handoff — verified against production 2026-08-02 ~19:45Z

**Merged and LIVE (verified, not assumed):**
- PR #4230 (docs: design spec + seam) — merged.
- PR #4235 (backend: `engine/seasonality/{panel,calendar,scanner}.py`,
  `scripts/build_stock_seasonality.py`, artifacts, nightly wiring) — **merged
  2026-08-02T19:28Z**, and live:
  - `https://www.mastermind-x.com/seasonalitydata/index.json` → 200, 220
    entities, `program_rates` raw 34/220 (15.4%) / neutral 24/219 (11.0%) vs 5%
    chance, labels 98% resolved;
  - `/seasonalitydata/entities/SPY.json` → 200, contract-exact (365 slots,
    2,645-window family, `independent_circular_year_shift` null B=2000,
    integer 1e-5 cum encoding, `default_window.state=market`);
  - `/seasonalitydata/methodology.json` → `status: calendar_clock_live`,
    availability booleans still honest (no forecast/screener/event-graph),
    authority ceiling intact.

**In flight — THE BATON (§3):**
- PR #4236 (frontend: `stock_seasonality.html` page) — OPEN, head
  `9fbe54eeaaa`, **`merge-on-green` label deliberately OFF** (held so the page
  could not go live before its data; that ordering concern is RESOLVED by
  #4235's merge). Needs one rebase + re-arm. The prior session's builder agents
  are dead; their worktrees remain at
  `.claude/worktrees/seasonality-backend-lane12` and
  `.claude/worktrees/seasonality-frontend-page` (branch
  `claude/seasonality-frontend-page`).

**Expected-pending (not defects):**
- R2 entity files 404 (`<DATA_BASE>/seasonalitydata/entities/XBI.json` etc.) —
  populated by the **first nightly** (`daily.yml` → `publish_r2 --dirs …,seasonalitydata/entities`).
  `DATA_BASE = https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev`.
- Page 302 / assets 401 — correct until #4236 merges (default-deny boundary).

**Known small defects, open:**
1. Live `methodology.json` `as_of` reads **2026-07-08** — predates the program;
   `status` is right but the date source is wrong somewhere in the
   `scripts/build_biopharma_seasonality.py` / `foundation.py` refresh. Diagnose,
   don't guess.
2. `QUBT` 2016 is a dead year (252 sessions at $0.20 — dormant shell). The
   artifact handles it honestly; a liquidity/instrument-identity filter is an
   open design question, deliberately unanswered.
3. 5/220 labels unresolved (within the 80% floor; cosmetic).

## §3 THE BATON — do these in order, first session-hour

1. **Rebase #4236 onto merged main.** Conflicts expected on exactly four files:
   `.github/workflows/daily.yml` (the `ORDER=` string is ONE line carrying both
   slugs), `config/dag.yml`, `config/site_access.yml`, `app/deploy/Caddyfile`
   (three occurrences). Resolution rule: **keep BOTH programs' entries** —
   `build_stock_seasonality` (backend, nightly lanes) AND
   `build_stock_seasonality_page` (page render, render lanes); both sets of
   public paths. After rebase, re-copy
   `tests/fixtures/seasonality/{SPY.entity,index}.json` from the merged
   `site/seasonalitydata/` and confirm byte-identity (fixtures must exercise the
   producer's real output). `MU.entity.json` stays generated.
2. **Re-verify the page renders against the merged artifacts** (Browser pane,
   not curl): strand field + window fan draw, gate drag updates stats, symbol
   picker works, no console errors.
3. **Re-apply `merge-on-green` to #4236** and let the sweeper take it. Do not
   `--admin` past pending packs; packs take 30–90 min on the busy pool.
4. **After merge + ~3 min VPS pull:** run
   `bash scripts/verify_stock_seasonality_live.sh`. Sections 1–3+5 must be all
   PASS (page/assets flip 302/401 → 200).
5. **After the first nightly:** run it again — section 4 (R2) must flip to
   PASS. This is the LAST unverified leg: publish credentials only exist in the
   nightly, the step is deliberately non-fatal, and if it fails the page looks
   perfectly healthy while every non-default symbol 404s. If still 404: check
   the daily run's `publish_r2` step log, then `scripts/audit_r2.py`.
6. Investigate defect 1 (methodology `as_of`) — small PR.

## §4 Tranche 2 — the pharma lobe (commission after §3 clears)

Ordering is dictated by one fact: **authority is earned on forward evidence,
which accrues in calendar time** — so the ledger starts first.

1. **Lane 6 shadow lobe emitter** (highest leverage, cheap): nightly
   `neuralweb.biopharma_seasonality_state.v1` per covered biopharma symbol via
   the already-merged, fail-closed
   `engine/seasonality/contracts.build_neuralweb_state` (built, tested, **no
   emitter exists**). Synapse-register at `shadow`/`context`, wire into
   `engine/neuralweb/mastermind_context.py` `candidate_context` as an
   annotate-only sparse map, **forward outcome ledger graded at horizon**
   (nightly sole advancer). RUL-C9/RUL-P10 apply (registry + SIGNAL_BUS regen +
   declared commit path).
2. **Lane 4 event engine**: `event_clock.py` seam adapter over BioCatalyst
   artifacts (their B1 ingestion merged #4218; B1b workbench was open as #4227 —
   re-check `gh pr list`) + interim known-at-time events
   (`collectors/clinicaltrials.py` Phase-3 start/halt, `collectors/openfda.py`
   approvals/label, earnings). Then `event_study.py`: AR/CAR, BMP, Corrado,
   issuer/date clustering, matched controls — extend `engine/event_window.py`
   and `engine/validation.py`, never fork them.
3. **Catalysts submode** on the page (display-tier timeline) once real event
   rows exist.
4. **Lane 7 Prophet overlay, narrative-only** (`prophet_bridge.py`,
   post-candidate-selection, NARRATE/ATTEND) + **pre-register the adverse-cap
   de-escalation experiment** — the only path that may ever touch Prophet
   numbers, shrink-only, and only after that experiment passes.
5. Later: Lane 5 probability engine (needs Lane 4 cohorts) → screener with a
   declared honest utility → regime clock.

**Constitutional lines (hook- and contract-enforced, do not re-litigate):**
positive seasonality never boosts/ranks/gates/sizes/originates; confluence is
display-only until separately gauntleted; LLMs de-escalate only; the word
"validated" is CI-guarded; no election/bull-bear cohort filters
(`DO_NOT_REBUILD.md` kill); no second pharma-facts collector (seam §5).

## §5 Session-learned traps (the ones that cost hours)

- **Re-fetch main before fixing a "base-side" red** — a pinned worktree ages
  silently; this session nearly shipped a redundant, worse fix to
  `check_validated_claims` (whole-line suppression) when main had already fixed
  it properly (in-place token mask). The checker's own selftest caught it.
- **Guard diagnostics can name the wrong cause** — the `'proven'` allowlist hint
  was a substring match inside `"provenance"`; the real trigger was a
  `"validated":0` telemetry counter elsewhere on the line.
- The **R2 key for entities is nested** (`seasonalitydata/entities/<SYM>.json`) —
  first nested dir in `publish_r2`; `key = f"{d}/{rel}"` preserves it. A
  flattened key 404s every non-default symbol invisibly.
- **`DATA_BASE` has no trailing slash** — normalize before concatenating (the
  frontend does; anything new must too).
- **Window convention** is 1-based `doy`, `cum index = doy − 1`, stated in
  `calendar.window_convention` inside the artifact itself. An off-by-one
  produced |t| 5.60 vs the true 7.25 — both plausible. Trust the artifact's own
  field, and cross-check one window by hand.
- **Never reuse a squash-merged branch** — this handoff's own PR is on a fresh
  branch because rebasing the merged one replays its commits into conflicts.
- Model routing per CLAUDE.md: Opus `builder`/`reviewer`/`designer` types for
  build/review/design; Sonnet only for mechanical non-code census; design
  choices stay in the main loop (frontend-design skill + DESIGN_DOCTRINE).
- Spawned builders start with ONLY their prompt + CLAUDE.md: acceptance gates
  inline, reference renders as committed files, commissioner reviews the visual
  artifact and holds first-pass self-merge of flagship UI.

## §6 Open operator decisions (flag, don't assume)

1. **Public gating**: page + artifacts ship PUBLIC (no forecast/no ranking;
   methodology was already public; "stock seasonality" is the incumbent's search
   moat). Reversal = one-line `site_access.yml` + Caddyfile change. The operator
   has not vetoed; the window is still open.
2. **Screener**: deliberately unbuilt until it has its own selection accounting
   + survivorship handling. Do not ship a ranking casually.
3. **QUBT-class dead years**: liquidity/identity filter design open.
