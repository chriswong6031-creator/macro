# Factor Intelligence × Neural Web Integration — FABLE ADJUDICATION

**Date:** 2026-07-06
**Adjudicates:** `research/factor_intelligence/NEURAL_WEB_INTEGRATION_DOCKET_FOR_FABLE.md` (Codex draft, same date)
**Verification:** 9-lane codebase census + Opus red-team, run 2026-07-06 against origin/main @ 68ab0ddb
**Constraint honored:** no locked gate moves. PREREGISTRATION.md (locked at PR #1357 merge) and the masterplan kill list are binding throughout.

---

## §A Verified verdict on the docket

The docket's diagnosis is **CONFIRMED, and understated**. The verified facts:

1. **The integration failure is present-tense, not a risk.** Committed `data/neuralweb/world_state.json` lacks BOTH `factor_weather` and `options_weather` keys — the artifact predates the code merges (#1415 factor, #1486 options). Even after tonight's nightly, `_compose_factor_weather()`'s panel block will be null forever under the current topology, because:
2. **Nightly jobs do NOT share tree state.** Every daily.yml job does a fresh `actions/checkout@v4` + `git pull origin main`. `engine` (builds world_state) and `factor_panel` (has the panel) are PARALLEL jobs (both need only upstream, neither needs the other). The panel is gitignored, is NOT in the R2 publish dir list, and never leaves the factor_panel job's tree. The docket's "one-run stale" Option A is physically incoherent — the next engine run's fresh checkout still can't see the factor job's uncommitted writes.
3. **The same cross-job hole silently breaks the factor_attention reflex lane.** `factor_contradictions.py` (factor_panel job) writes `data/reflexes/factor_attention/firings.jsonl` runner-local; the cortex job's commit step `git add data/reflexes/factor_attention/ || true` runs in a DIFFERENT tree where the path never exists — the soft-fail masks it. Firings can never persist; grades can never accrue; A2 earn-in is structurally impossible today.
4. **Pair G is dormant anyway** (panel <60 dates in any tree; `config/reflexes.yml:555`), and `data/neuralweb/factor_contradictions.jsonl` is explicitly gitignored — the proposed cortex `list_factor_contradictions` tool would read a file that is absent in the cortex job's tree. The docket did not notice this.
5. **The docket's biggest miss is the operator's actual ask:** a LONG-TERM pool of factor state vs signal accuracy/behavior/returns. `factor_intelligence_state.json` as proposed is an overwritten snapshot — zero accrued history. The panel already computes every needed coordinate; the gap is persistence, not math.
6. Docket factual errors, minor: `_compose_factor_weather()` returns 10 keys not 7; factors.html uses the `help()`/`t()` macro pattern not `data-tip-*`; committee per-ticker content is 100% JS-rendered from `stockdata/<TICKER>.json` (no Jinja loop); scorecard claims (payout sole FDR survivor, SUE collapse, composite untradeable) all CONFIRMED.

---

## §B Rulings on the eight §12 review questions

**RUL-NW1 (who commits the state artifact).** The Option A/B binary is REJECTED as posed — A is two-run stale AND still requires a factor-job push to exist at all. RULING: the **factor_panel job itself builds and commits the factor-namespace artifacts** via a narrow, path-allowlisted commit/push step. This is Option B, granted as a scoped sole-advancer. The allowlist is EXACTLY:
- `data/neuralweb/factor_intelligence_state.json`
- `site/neuralwebdata/factor_intelligence_state.json` (site mirror)
- `data/factordata/factor_state_history.jsonl`
- `data/factordata/fire_coordinates.jsonl`
- `data/neuralweb/factor_contradictions.jsonl` (un-gitignored by this ruling)
- `data/reflexes/factor_attention/firings.jsonl`

Nothing else — never `world_state.json`, never any Article-2 path. The step uses the standard 5-attempt rebase-loop sentinel. The nightly-sole-advancer law is preserved in spirit: factor_panel IS a nightly job; `factor_ops.yml` (dispatch) remains contents:read, no-push. Grades/probation stay cortex-job-committed (single writer per file: firings=factor job, grades=cortex job).

**RUL-NW2 (world_state canonical source).** YES. `_compose_factor_weather()` reads `data/neuralweb/factor_intelligence_state.json` as canonical (present in every fresh checkout, one-run stale — acceptable for a slow de-escalation lobe), with the direct panel read demoted to fallback-when-absent. The lobe gains a `factor_state_as_of` field so staleness is visible. Single-function-PR discipline per masterplan §6.3.

**RUL-NW3 (cortex tools).** THREE in v1: `read_factor_state`, `list_factor_contradictions`, `explain_factor_context`. `query_factor_attention` is FOLDED into `read_factor_state` (the state artifact carries the attention track record). All three read COMMITTED artifacts only (state JSON, contradictions ledger, fire-coordinates tape) — never the runner-local panel, which is absent in the cortex job's tree. Per-ticker context for current board names rides the state artifact's `latest_board_coordinates` block. Tool outputs are capped and marked `is_context_only: true` (options-tools RO-7 precedent). The stale `READ (7)` system-prompt text is corrected in the same PR; the deliberation protocol gains "read factor state" and "list factor contradictions" steps.

**RUL-NW4 (Ask-the-Brain).** Immediately, same wave — read-only, display-only. Factor trigger-term classifier branch added to `_classify_question()`; factor tools added to `_ASK_READ_TOOLS`. A string guard bans directional verbs (buy/sell/hold/add/trim and zh equivalents) in the factor-context answer path — kill-list #6 (no folk regime priors) applies to customer-facing text verbatim.

**RUL-NW5 (Lane 2 probation).** Already ruled by masterplan §5.3: cortex selections from `factor_contradictions.jsonl` accrue to CORTEX probation via the existing `_tool_flag_attention`. No separate `factor_cortex_selection` record. Closed.

**RUL-NW6 (shadow-ledger floor before A3).** Minimum **25 episode-clustered would-have-fired events spanning ≥3 calendar months** (EI R6 convention), graded at the relevant hypothesis's own falsifier, THEN an explicit Fable ruling before any clamp wiring. Note the honest timeline: family BH is withheld until H4/H5 floors (~mid-2027) unless a family split is pre-registered before data is seen, so no GATE-PASSED can exist before then. Lane E therefore ships as a THIN dark scaffold that refuses to run without a GATE-PASSED verdict artifact.

**RUL-NW7 (factors.html role).** Both: it stays the expert research surface AND gains a compact NW-integration status panel (top, after the header panel). Chip vocabulary: `DISPLAY / SHADOW / ACCRUING / GATE-PASSED / NULL / DORMANT / PRE-FDR INTERIM / BH-WITHHELD` — the last one is mandatory (red-team finding: without it, an interim H1/H2 read could be mistaken for actionable before the family BH runs). The CI-sensitive validation word never appears.

**RUL-NW8 (where H status surfaces).** The state artifact is the single source; **factors.html + admin render it now. The committee per-ticker predictive lane is DEFERRED to P4** (masterplan §5.5 already schedules it; building a rich predictive surface that renders `PRE-FDR INTERIM/NULL` for a year is scope theater). Admin gets the operationally-useful card today: freshness, panel health, dormancy, hypothesis/authority status, and the alert list from docket §9.2.

---

## §C Additional Fable rulings (beyond the docket's questions)

**RUL-NW9 (allowed_actions is inert).** The state artifact's `allowed_actions` block is DESCRIPTIVE self-documentation only. It carries a sibling field `"authority_source": "constitution.grant_authority + prereg gates; this block is a mirror, never a switch"`. A static guard (`scripts/check_factor_boundaries.py`) fails CI if any code outside the state builder and render/admin surfaces reads `allowed_actions`. Authority is granted only by graded probation via `constitution.grant_authority` — a boolean in JSON must never become a behavior wire.

**RUL-NW10 (the long-term pool — chartered).** This is the program's real deliverable, missing from the docket. Three committed, append-only, factor-job-advanced accrual artifacts:
1. **`data/factordata/factor_state_history.jsonl`** — one digest row per trading day: style_regime (+pending/hold_days), factor_leader (+IC), ETF ratios, panel health (n_dates, n_tickers, latest_date), Pair G count, cross-sectional alibi stats (median, Q80), DNA class distribution snapshot. The "factor weather tape."
2. **`data/factordata/fire_coordinates.jsonl`** — for each current board buy-lane fire (all tiers the gate emits): (ticker, date, tier, dna_class, style_regime, alibi_share_20d, twin_bleed_flag, twin_rel_20d, alpha_z_house, top-3 Block-A contrib streams, factor_model:v1). PIT by construction (panel row at fire date). This is a STANDALONE artifact keyed (ticker, date) that JOINs to replay/board-ledger outcomes at study time — kill-list #7 (no replay edits) is respected; it also makes the study-time join durable even if the runner-local panel is ever wiped.
3. **`data/neuralweb/factor_contradictions.jsonl`** — un-gitignored, committed (the durable Pair G ledger; 0–20 rows/day).
All three are display/analysis-only until the kernel-FDR 2026-10 sweep; any code conditioning behavior on the pooled history before that verdict is a premature A5 promotion and is banned. Idempotence: same-day re-runs must not duplicate rows (reuse the (as_of, ticker) / (as_of) key discipline from factor_contradictions.py).

**RUL-NW11 (registration + guards).** Every new committed artifact gets a `config/synapse.yml` entry (producer = the factor job script); every new workflow step gets its `config/dag.yml` entry; `scripts/check_factor_boundaries.py` additionally asserts factor modules never write Article-2 paths (`alert_triage`, `board_ordering`, `top_setups`, `attention_queue`, `push_floor`). Freshness/dormancy alerting lives in the admin card (a CI check on the committed world_state.json artifact would be red until the next nightly by construction — wrong layer; unit tests assert the built payload carries the key even when null-filled).

**RUL-NW12 (severity clamp logging).** `factor_contradictions.py::_record()` silently downgrades `severity='tension'` to `'note'` with no log line (warning fires only for invalid values). Add a debug-level log for the tension→note clamp pre-H2. Cosmetic; no gate logic moves.

**RUL-NW13 (prereg status line).** PREREGISTRATION.md line 5 still reads "DRAFT — pending Fable merge" although the lock clause activated at PR #1357's merge. Administrative correction to "LOCKED at merge (PR #1357)" — explicitly NOT a gate edit; §0 vocabulary, thresholds, and all gates are untouched.

**RUL-NW14 (ops tail).** `register_h45` is legal from today (ISO-W28). Dispatch `gh workflow run factor_ops.yml -f action=register_h45` after the build wave and inspect the run log — the log doubles as the probe for whether W27's register_h123 rows persisted on the runner (machine_registry.jsonl has never been committed; the factor_ops→cortex-job commit relay is suspect under the same cross-job hole). Findings go to the admin card's hypothesis block as honest `not-visible-in-tree` status rather than fabricated certainty.

---

## §D Amended build lanes (supersedes docket §13)

| PR | Lane | Contents | Depends on |
|---|---|---|---|
| **PR-1** | A-core: state artifact + pool + build-order repair | `scripts/build_factor_intelligence_state.py` (writes state JSON + site mirror + history append + fire-coordinates append); un-gitignore contradictions ledger; daily.yml factor_panel job gains build step + narrow allowlisted commit/push; synapse.yml + dag.yml entries; tests (no-panel honest gaps, synthetic-panel digest, same-day idempotence) | — |
| **PR-2** | A-worldstate | `_compose_factor_weather()` reads state artifact as canonical, panel fallback, `factor_state_as_of` stamp; tests | PR-1 |
| **PR-3** | B: cortex + Ask-the-Brain | 3 read tools + dispatcher + schemas + protocol text fix; ask_brain classifier branch + `_ASK_READ_TOOLS` + directional-verb guard; tests | PR-1 |
| **PR-4** | C+D-admin: surfaces | factors.html.j2 status panel (help()/t() macros, chips incl. BH-WITHHELD, bilingual, no CI-sensitive word); `build_factors_page` context; admin/neural_web.py Factor Intelligence section + app.js renderer + §9.2 alerts; tests + render check | PR-1 |
| **PR-5** | E-scaffold + guards | `scripts/build_factor_deescalation_shadow.py` dark scaffold (refuses without GATE-PASSED verdict artifact; docket §11 row schema pre-committed); `scripts/check_factor_boundaries.py` static guard wired into CI following existing check-script conventions; tests | PR-1 |
| **PR-6** | Docs | This adjudication + docket committed; masterplan §11 status-log append; prereg status-line fix (RUL-NW13) | PR-1..5 |

Committee per-ticker factor lane: NOT in this wave (RUL-NW8, deferred to P4). Kernel_style.py shadow table: NOT in this wave (P3 deliverable, masterplan §5.1). validate_factor_h1-5 harnesses: NOT in this wave (P3, awaits replay artifact).

**Model routing:** Sonnet builds every PR (agentType `builder`); Opus reviews every PR (agentType `reviewer`) with PIT/constitution focus on PR-1 and PR-3; Fable (main loop) merges.

---

---

## §E Shipped status (appended at wave close, 2026-07-06)

All lanes shipped same-day: PR-1 = #1583, PR-2 = #1589 (Opus review caught a circular-staleness freeze — the state builder reusing `_compose_factor_weather` after it became artifact-canonical would have frozen the factor-weather tape one day after go-live; fixed with `prefer_artifact=False` on the builder path), PR-3 = #1595, PR-4 = #1593, PR-5 = #1598, PR-6 = this docs PR. `register_h45` dispatched and registered (H4/H5, come-back 2026-08-03). Open follow-ups: (a) verify machine_registry.jsonl rows written by factor_ops dispatch actually persist to main after tonight's nightly (same cross-job visibility class as the firings bug PR-1 fixed) — if lost, re-dispatch is idempotent and a persistence fix is needed — **RESOLVED, see §E.1**; (b) key-allowlist on the world_state artifact read (defense-in-depth, non-blocking review note); (c) committee per-ticker lane at P4; (d) kernel_style.py shadow table at P3.

### §E.1 Follow-up (a) resolution — registrations LOST, persistence fixed (2026-07-06)

**Verdict: all five dispatch registrations were lost.** The 2026-07-06 nightly (run 28772063146, success) ran after the W27 `register_h123` dispatch, yet `data/neuralweb/machine_registry.jsonl` has **no git history at all** — the rows never reached any commit. RUL-NW14's suspicion was correct: the factor_ops→cortex-job commit relay was the same cross-job hole PR-1 (#1583) fixed for firings. Root cause: every workflow job starts from a fresh `actions/checkout` (`git clean -ffdx`), so registry rows written in the factor_ops runner workspace were wiped before the cortex job's `git add data/neuralweb/machine_registry.jsonl` could ever see them. The W28 `register_h45` rows (run 28777488996, ids `…-571a9f`/`…-8840eb`) sat on a doomed workspace too. Because the metabolism weekly budget is counted from the registry file itself, the lost file also means the "W28: 2 of 3 consumed" state never existed on main.

**Fix (this PR): registration moved inside the nightly cortex job** — the option that keeps the nightly-sole-advancer law (FIX-1) intact; the factor_ops register actions are removed (a narrow factor_ops push was rejected: FIX-1 explicitly forbids dispatch-workflow pushes). The cortex job now runs `register_factor_hypotheses --only h1,h2,h3 --defer-on-budget` then `--only h4,h5 --defer-on-budget` before cortex deliberation (operator batches claim budget ahead of cortex-proposed hypotheses), in the same tree its commit lane stages; `data/trial_ledger.jsonl` added to that lane so the per-registration declared-budget row persists too. The script's FIX-7 pre-flight now counts only *pending* keys (a finished batch on an exhausted week is a no-op, not a false "deferred"), and `--defer-on-budget` turns a budget abort into exit 0 so the step retries nightly.

**Expected timeline:** h1–h3 register at the next nightly (still W28; ids re-minted with the actual registration date — the lost W27 ids are gone; `registered_at` is server-side and cannot be backdated); h4–h5 defer nightly until the 2026-07-13 (W29) nightly. Come-back dates shift accordingly (~2026-08-04 / ~2026-08-10). Verify after each: `git show origin/main:data/neuralweb/machine_registry.jsonl`.

*Adjudicated and chartered 2026-07-06. — Fable*
