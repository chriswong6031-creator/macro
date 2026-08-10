# Government Revenue Foresight — Claude implementation handoff

**Checkpoint:** 2026-08-06

**Implementation through:** Wave 9C (award-event persistence recovery shipped 2026-08-06)

**Next build:** Wave 9D exact issuer expansion — after a nightly `daily.yml` collect has actually
persisted the event triad in production and `projection_state_absent` has cleared

**Canonical implementation checkpoint:** this file

**Canonical product and architecture specification:** `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md`

This is the resume document for Claude. Read it before changing Government Revenue code. The masterplan remains the authority for the product thesis, clean-room HigherGov/GovTribe forensics, contracts, source strategy, UI model, and long-range architecture. This handoff records what actually shipped, what production currently says, and the ordered work still required to make the lobe investment-useful.

## Executive verdict

The product shell is no longer the bottleneck. MastermindX already has a strong, evidence-native Government Revenue workbench: award and action context, opportunities, dossiers, subawards, IDV and budget foundations, saved research workflows, a ticker-first Candidate Radar, receipt drawers, explicit coverage states, point-in-time contracts, and fail-closed authority rules.

The remaining program is an **event-to-issuer-to-investment-signal build**, not another dashboard redesign:

1. make the forward award-event spine persist and activate reliably;
2. expand exact, reviewed public-company attribution beyond PLTR;
3. emit evidence-bound candidate hypotheses from real post-baseline changes;
4. cross-check those already-selected candidates against Neural Web context;
5. annotate Prophet only after selection, without changing its decisions;
6. grade every candidate prospectively before requesting any authority; and
7. add budget, vehicle, SBIR, recompete, earnings, and displacement rails only with source-native lineage.

A zero-candidate product is currently the honest result. Identity coverage, attractive UI, large award values, and ticker search provenance are not catalysts. Do not manufacture activity to make the screen look alive.

## Start here

Read these in order:

1. `CLAUDE.md`
2. `AGENTS.md`
3. `research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md` — this checkpoint
4. `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md` — product and architecture authority
5. `research/GOVERNMENT_REVENUE_WAVE9_DEFENSE_CATALYST_CANDIDATE_LEDGER_2026-08-03.md` — candidate doctrine and Wave 9 contract
6. `research/GOVERNMENT_REVENUE_WAVE8_HANDOFF_2026-08-02.md` — IDV and DoD budget foundation
7. `docs/ACTIVE_BUILD_MAP.md` and `research/DO_NOT_REBUILD.md` — coordination fences; verify their freshness against GitHub

Before editing, fetch `origin/main`, inspect open PRs, and create a fresh `codex/` worktree from the fetched remote head. The shared main checkout may be dirty or detached. Never clean it, switch it, or use the shared stash stack.

## What is already shipped — do not rebuild

### Core evidence and product surfaces

- Bounded official USAspending award and action collection with receipts, source-health metadata, and bitemporal/PIT semantics.
- Government Revenue workspace and premium three-pane UI at `/government_revenue.html`.
- Award Tape, opportunity views, company/award workspaces, saved filters, local alert inbox, JSON/CSV exports, and a browser-local Research Briefcase.
- Exact prime-award dossiers with content-addressed canonical/public twins and generation-bound APIs.
- Exact-recipient graph, resolution, and absolute-dollar coverage contracts that fail closed.
- Official USAspending subaward evidence rail with explicit complete, verified-zero, high-count-only, run-cap-only, and not-selected states.
- Responsive subaward UI, server-side search, cursor paging, and receipt inspection.
- IDV relationship foundation and dossier contracts.
- DoD budget-line and budget-edge schema foundations, but not an activated production graph.
- Ticker-first Defense Catalyst Candidate Radar, candidate queue/status contracts, mapping backlog, empty-state projection, and UI.
- Candidate governance that keeps Government Revenue display/context-only.
- API, asset, template, projection, raw-data, and edge-budget fences.
- Scheduled collection/build workflow in `.github/workflows/government-revenue-live.yml`.

### Clean-room and ownership fences

- The competitor study is complete enough to guide jobs-to-be-done. Do not use competitor credentials, scrape authenticated pages, copy code, reproduce proprietary data, or pixel-clone either product.
- Preserve the superior MastermindX model: public/licensed evidence, visible provenance, freshness, coverage, uncertainty, and authority.
- Consume central company registry, SEC/13D/13G, earnings transcripts, filings, market data, Neural Web, and Prophet services when their owning lanes expose stable contracts. Do not fork local shadow versions inside Government Revenue.
- Keep Government Revenue sector-specific. Shared issuer identity, evidence envelopes, event transport, and evaluation should become platform services rather than duplicated lobe internals.

## Production checkpoint on 2026-08-06

The production health endpoint returned a serving commit that is a descendant of the Wave 9B merge. Recheck every value live before relying on this snapshot.

| Surface | Current truth | Interpretation |
|---|---|---|
| Aggregate workspace | Serves successfully; 30 workspace companies; freshness `partial` | Product is usable for bounded research, not fully current |
| Awards/actions | Award detail and actions were about five days old against a four-day SLA | Stale; do not present as live catalyst evidence |
| Opportunities | Unavailable; zero records and no `observed_at` | SAM lifecycle rail is not active in production |
| Award-event spine | Unavailable with `projection_state_absent` | No trustworthy before/after event emission yet |
| Candidate ledger | `grcq1-2e008e5fe4635fa30b6a3772`; zero candidates | Correct fail-closed result |
| Mapping coverage | 21-company backlog; one reviewed issuer ticker (`PLTR`) | Attribution breadth is the immediate constraint after P0 recovery |
| PLTR graph | `recipient-graph:reviewed:2026-08-03:pltr-v1`; two exact legal entities and two identifiers | First reviewed issuer path is shipped, not a broad defense universe |
| Remaining mapping states | 20 `mapping_needed`; one `partial_identifier_coverage` | Never substitute fuzzy name matching |
| IDV baseline | 24 selected/count-verified IDVs, 15 complete-detail parents, 452 relationship observations, 26 receipts | Useful vehicle context; zero exact bridges into the prime dossier at checkpoint |
| DoD budget | Contracts/foundation only; production rail unavailable | No budget-to-issuer beneficiary claims yet |
| Subawards | Bounded rail and UI shipped | Subrecipient evidence is not issuer attribution or federal obligation |
| Authority | All Government Revenue candidate authority flags false | Context/display only; no ranking, sizing, gating, or signal origination |

Exact PLTR reviewed UEIs at the checkpoint are `FSY4LVSBGWB7` and `HNN4F9JZWDY8`. Treat them as reviewed graph inputs with evidence, not universal aliases to be propagated without temporal ownership checks.

## Immediate incident: award-event persistence is P0

`data/government_revenue/ingest_status.json` records a fresh 2026-08-06 collection that reached the official source but failed during persistence:

- 1,936 awards seen;
- 34,208 actions seen and 34,181 actions previously accrued;
- 19 award queries stopped at the configured safety cap with `hasNext=true`;
- two award queries reached explicit source exhaustion;
- event spine remained baseline/unactivated with zero eligible event rows;
- `run_state` became `failed` and `last_successful_observed_at` remained null; and
- the persistence error is stored as `ledger_write_failed`.

### Root cause — CONFIRMED 2026-08-06, and it was not the leading hypothesis

The Parquet-schema hypothesis recorded above is **refuted**. Nothing ever reached `to_parquet`. The
failure is a **pandas 3.0 migration break**:

```
File "collectors/usaspending_awards.py", line 1341, in _ensure_snapshot_hashes
    out.loc[missing, "snapshot_content_sha256"] = [ ... ]
File "pandas/core/internals/blocks.py", line 1118, in setitem
    nb = self.coerce_to_target_dtype(value, raise_on_upcast=True)
TypeError: Invalid value '['814c439cdeb3deed...', ...]' for dtype 'float64'
```

`data/government_revenue/award_snapshots.parquet` was committed at #4182; `snapshot_content_sha256`
joined `SNAPSHOT_COLUMNS` later at #4216. So `reindex(columns=SNAPSHOT_COLUMNS)` materializes that
column as an all-NaN **float64**, and the backfill of 1,936 hashes writes strings into it. pandas 2.x
upcast silently (FutureWarning only); **pandas 3.0 raises**. The bug was latent from #4216 and became
fatal the night the runner crossed the 2→3 boundary — `requirements.txt` pins only `pandas>=2.2`, and
41 workflows share one mutable venv keyed solely by physical runner name
(`$HOME/.cache/mm-venv-$RUNNER_NAME`, installed with no `--upgrade` and no ceiling), so one job's
unbounded resolve upgrades pandas for every other workflow on that runner.

Reproduced byte-exactly from the committed artifact: same leading hash `814c439cdeb3deed…`, same
`for dtype 'float64'` tail.

**Why the incident review was misdirected:** `_safe_error` truncated the exception's *suffix*, which
is precisely where `for dtype 'float64'` lives. The head that survived was 800 characters of receipt
hashes — which reads exactly like a list-valued cell hitting a Parquet boundary. Truncate exception
text from the middle, never from the tail.

A **second instance of the same hazard** in the same file was found by census and fixed in the same
PR: `_ensure_award_keys` at line 1032 does `out.at[idx, "award_key"] = "<string>"` after
`merge_awards` hands it a `reindex(columns=AWARD_COLUMNS)` frame — `TypeError: Invalid value
'generated:CONT_AWD_N0001' for dtype 'float64'`.

The cure already existed in-house: `engine/china_standout_track.py` and `engine/board_ledger.py` each
carry a `_coerce_object_cols()` helper naming this exact pandas-3 TypeError. The collector simply
never got it. **Grep for `_coerce_object_cols` before writing a third spelling.**

Required safety behavior:

- never overwrite unreadable accrued history;
- never partially advance one member of the event triad;
- preserve last-good production artifacts on collection or persistence failure;
- distinguish a valid bounded partial collection from persistence failure;
- never mark first-baseline rows as forward events; and
- never infer an event from the legacy merged award table.

The intended event triad is:

- `data/government_revenue/award_event_snapshots.parquet`
- `data/government_revenue/award_action_versions.parquet`
- `data/government_revenue/award_event_projection_state.json`

Those production artifacts were absent at this checkpoint.

## Remaining build waves

Wave numbers continue the shipped Wave 9A/9B candidate work. Keep PRs narrow. A wave may require several PRs, but no PR should silently combine new authority, new data semantics, and major UI work.

### Wave 9C — forward event-spine recovery and activation — **SHIPPED 2026-08-06**

Delivered in the recovery PR (`collectors/usaspending_awards.py`, `tests/test_usaspending_awards.py`
only — no engine, UI, mapping, Neural Web, Prophet, or budget scope):

- both pandas-3 assignment sites repaired with the in-house `_coerce_object_cols` idiom, over a
  `_NUMERIC_LEDGER_COLS` complement verified against the real on-disk parquet dtypes so no legacy
  numeric column changes type;
- the two event ledgers pinned to a **declared** Parquet schema (`_normalize_event_ledger`) instead
  of one inferred from whichever rows a run happened to fetch;
- `persist()` restructured to stage **and verify every artifact** — including re-reading the staged
  event pair and recomputing its projection-generation binding — before a single `os.replace`, so an
  interrupted or malformed write leaves every live artifact byte-identical;
- `_safe_error` now keeps the head *and* the diagnostic tail with an explicit elision marker.

Verified end-to-end against the live USAspending API into a scratch root (the repo's ledgers were
never written — nightly remains the sole forward-ledger advancer): the triad materializes, its
generation binding matches the on-disk pair, no `.tmp` leaks, and the baseline emits **zero**
eligible events. A second run over the same accrued root added **+0 snapshot rows and +0
action-version rows** with an unchanged `projection_generation_id`, proving the declared schema
round-trips without fabricating source revisions. Both pandas majors green (3.0.3 and 2.3.3).

**Still open after this PR:** production only shows the triad once a **nightly `daily.yml` collect**
runs the fixed collector. `government-revenue-live.yml` does not collect — it only folds an
already-committed triad (`collectors/usaspending_awards.py` appears there solely as a push
path-filter). Until that nightly runs, `/api/government-revenue/latest` keeps reporting
`"availability":"projection_state_absent"`.

**Wave 9C follow-ups — found during the recovery, deliberately NOT fixed in that PR.** Each is real
and reproducible; none is a crash. Do not let them disappear into the next wave's scope.

1. **A silently dead explicit-null branch.** `awards.parquet` has no
   `current_award_amount_observed_at` / `potential_award_amount_observed_at` column, so
   `merge_awards` evaluates `new[observed_column].notna()` against an all-NaN float64 placeholder.
   The branch that clears a value on an explicit source null therefore never fires for any accrued
   row. Behavioural gap, not a crash — and exactly the shape of defect that hid the pandas-3 break:
   a canonical column the accrued store never grew.
2. **`merge_awards` writes an Arrow `null`-typed column.** `program_acronym` is all-None in
   `awards.parquet`, so it infers no type. `_normalize_event_ledger` removes this class from the two
   event ledgers; the three legacy ledgers still have it, and their dtypes were deliberately left
   alone so existing readers keep working.
3. **The next pandas trap in the same file.** `append_snapshot_versions`
   (`collectors/usaspending_awards.py`, the `pd.concat` around line 1365) raises a pandas-2
   `FutureWarning`: concatenation "will no longer exclude empty or all-NA columns when determining
   result dtypes." Pre-existing, and the same all-NA-column family that caused this incident.
4. **`scripts/check_government_revenue_projection.py` fails from a bare shell.** With an empty
   `PYTHONPATH`, `from scripts import build_government_revenue` resolves `scripts` to a *different
   worktree* on this machine. `env PYTHONPATH="$PWD" python3 scripts/check_government_revenue_projection.py`
   works. Environment pollution rather than a repo defect, but it will mislead anyone running the
   guard outside pytest.
5. **The systemic gap: no suite reads a committed production artifact.** Every Government Revenue
   test builds `tmp_path` frames from the *current* column lists, so no test could ever see an
   accrued ledger that predates a column — which is why this bug was invisible for two release
   cycles. The two new regression tests write a legacy-shaped parquet and read it back, closing the
   specific case; the general gap is open.

**Original wave contract, retained for reference:**

**Goal:** establish the first receipt-bound baseline, then emit only genuine changes observed after it.

Build:

- reproduce and fix `ledger_write_failed` with a regression fixture that exercises the real problematic shape;
- normalize every persisted event cell to a deterministic Parquet-safe type;
- atomically write and validate the complete event triad;
- represent coverage as bounded partial when queries hit a declared safety cap;
- store source exhaustion, truncation, page counts, receipt bindings, and last-good clocks separately;
- activate baseline only after the full configured bounded universe completes the required receipt-bound conditions;
- carry omitted fields forward only under the existing presence-manifest rules; explicit JSON null remains distinct from omission;
- project additions, obligation changes, ceiling changes, period changes, and action corrections/retractions only from exact source versions; and
- keep Candidate Radar empty until a real post-baseline eligible event exists.

Acceptance gates:

- full traceback captured before the fix and a regression fails on old behavior;
- all three artifacts exist, validate, and share the expected generation/state binding;
- interrupted or malformed writes leave last-good artifacts byte-identical;
- first baseline emits zero candidates;
- a synthetic second observation proves each supported transition and rejects receipt-only churn;
- current production API no longer says `projection_state_absent` after a successful live run; and
- zero fabricated candidates is accepted as success.

**2026-08-10 anti-backfill incident and append-only correction.** The repaired
canonical builder derives exactly eight historical snapshot-rail rows, all first
knowable before the already frozen empty projection. The 2026-08-09 review bound
them one-for-one in `candidate_historical_suppressions.v1.json` for non-issuance.
That intended boundary did not reach production first: PR #5207 merged the schema
prerequisite ahead of the recovery, activating #5193's blanket empty-ledger escape.
Workflow run `31354784751` appended all eight rows and published them in commit
`5fc18d5aac892ac61bcfdcc7ae1638c028c66781`.

Those rows are now part of the append-only audit record and must not be deleted,
retimed, rewritten, treated as prospective calls, or silently relabelled as if the
issuance never happened. The operator-reviewed
`candidate_issuance_corrections.v1.json` binds the exact eight ledger-row hashes and
official source identities from that commit and quarantines only those rows from
active candidate, Prophet, grading, ranking, sizing, gating, signal, candidate-add,
and escalation surfaces. Any missing, extra, changed, or newly historical identity
still hard-fails and requires a separate exact reviewed correction. Only a genuinely
forward observation with a new exact source identity may become active after this
boundary; neither the suppression nor the correction carries Neural Web or trading
authority.

Primary code:

- `collectors/usaspending_awards.py`
- `engine/government_revenue/award_events.py`
- `engine/government_revenue/candidates.py`
- `scripts/build_government_revenue.py`
- `.github/workflows/government-revenue-live.yml`
- `tests/test_usaspending_awards.py`
- `tests/test_government_revenue_award_spine.py`

### Wave 9D — reviewed issuer graph expansion

**Goal:** turn the one-issuer proof into a useful defense-company universe without fuzzy attribution.

Start with the highest-confidence direct seeds in the existing mapping backlog, expected to include `LMT`, `LHX`, `AVAV`, and `VSAT` when official identifiers and issuer evidence support them. Recheck the backlog at build time; this list is prioritization, not preapproval.

Build:

- resolve issuer → legal entity → UEI/CAGE/USAspending recipient with reviewed evidence;
- use SEC exhibits/subsidiary lists, issuer disclosures, official entity records, and USAspending identity evidence;
- attach valid-from, valid-to, known-at, evidence hash, reviewer, and review status to every edge;
- support parent/subsidiary ownership without collapsing distinct legal recipients;
- maintain explicit unresolved, ambiguous, stale, and partial-coverage states;
- calculate award-dollar coverage independently from entity-count coverage; and
- surface why each company is or is not candidate-eligible.

Acceptance gates:

- no mapping derives from `discovery_query_ticker`, fuzzy name similarity, web-search snippets, or an LLM assertion;
- every active edge is reviewable from immutable evidence;
- PIT tests prevent current ownership from leaking backward;
- a company can have exact partial coverage without being mislabeled complete;
- mapping changes cannot create an investment candidate without an eligible event; and
- candidate contract IDs remain stable under irrelevant graph ordering changes.

### Wave 9E — Neural Web shadow cross-check packets

**Goal:** enrich an already-selected Government Revenue candidate with independent context without creating a fused super-score.

Candidate selection must complete before Neural Web is called. The packet should contain named, separately inspectable legs such as:

- technical trend and relative strength;
- volatility/liquidity and regime fit;
- geopolitical and budget-theme relevance;
- filings/transcript corroboration;
- ownership/13D/13G changes when available;
- alternative-data or supply-chain context; and
- contradiction, staleness, and missing-data flags.

Acceptance gates:

- the candidate set and ordering are byte-identical with Neural Web disabled, unavailable, delayed, or contradictory;
- no unnamed composite score hides the contributing legs;
- each leg has source time, known-at, freshness, status, and provenance;
- contradictory evidence remains visible rather than averaged away; and
- the UI labels the packet `shadow context`, not signal confirmation.

### Wave 9F — Prophet post-selection annotation

**Goal:** let Prophet consume Government Revenue evidence as annotation only.

Build a narrow, versioned envelope containing candidate ID, issuer identity, procurement event, evidence references, known-at timestamp, freshness, coverage, contradictions, and the Neural Web shadow packet. The adapter must run after Prophet selection.

Acceptance gates:

- candidate membership, rank, confidence, size, gates, and execution decision are byte-identical with the adapter on/off;
- timeouts and malformed Government Revenue packets fail open to Prophet's preexisting decision;
- Prophet cannot call Government Revenue to source a candidate;
- authority remains `display/context`; and
- every rendered annotation traces to the exact candidate/evidence generation.

### Wave 9G — prospective grader and first preregistered family

**Goal:** determine whether the lobe has predictive value rather than merely persuasive narratives.

Preregister one narrow family first. Recommended starting family: exact-issuer, receipt-bound positive funded-action acceleration, optionally separated from ceiling-only changes. Do not combine multiple catalyst families until each can be graded independently.

Build:

- immutable issuance log with candidate payload hash and `known_at`;
- fixed forward horizons aligned to the event's economic thesis;
- market/sector-relative returns, hit rate, calibration, coverage, drawdown, and abstention metrics;
- earnings-window and subsequent-filings outcome labels where available;
- counterfactual cohorts and naive baselines;
- corrections/retractions policy fixed before observation; and
- versioned preregistration documents and no-leakage tests.

Acceptance gates:

- grader reads only information available at issuance;
- missing prices, mappings, or source outages produce explicit ungraded/abstained states;
- no threshold tuning on the held-forward window;
- negative and null outcomes are preserved;
- evaluation separates identity coverage, event coverage, and market outcome; and
- authority remains unchanged regardless of attractive early results.

### Wave 10 — official catalyst and progression rails

Build these as separate evidence lanes, not one mega-wave:

1. **IDV child bridge:** exact source-native parent/child relationships into prime-award dossiers; distinguish vehicle membership, task orders, and count-only coverage.
2. **DoD budget graph:** immutable PDF/page/hash receipts; request, authorization, appropriation, and execution remain separate; PE/line/program identifiers precede any reviewed company edge.
3. **SBIR progression:** append-only SBIR.gov Phase I/II observations and exact award/company identity; progression is evidence, not proof of production conversion.
4. **SAM lifecycle:** first-seen opportunity observations, amendments, archive state, and exact notice → award linkage after a complete baseline.
5. **Recompete outcome:** expected expiry → solicitation → award chain, incumbent/challenger identity, and displacement/share-gain labels.

The SAM key currently appears constrained to a low daily quota shared with nightly radar. The scheduled workflow's nominal 30-minute cadence does not mean 30-minute upstream polling: quota gating restricts scheduled SAM collection to approximately 00–01 UTC, while manual dispatch can bypass the time gate. Do not claim intraday SAM freshness without a managed/higher-tier key and production evidence.

Acceptance gates for every new rail:

- source-native identity and immutable receipts;
- explicit collection universe and omission states;
- separate source, effective, observed, and known-at time;
- first baseline cannot synthesize history;
- no semantic-similarity-only issuer/program joins;
- source failure cannot erase last-good evidence; and
- candidate impact remains off until the family is preregistered and prospectively gradeable.

### Wave 11 — earnings and revenue translation

**Goal:** connect procurement evidence to investable questions without equating federal values with accounting revenue.

Integrate the central company-intelligence/document engines when their contracts are stable:

- filings, earnings transcripts, guidance, backlog, funded backlog, bookings, and segment revenue;
- award velocity and modification velocity by issuer and program;
- book-to-bill proxy with a plainly named methodology and limitations;
- contract concentration and agency/program exposure;
- funded obligation versus ceiling-versus-announcement reconciliation;
- program funding changes that precede disclosed revenue;
- earnings-window catalyst calendar and post-event reconciliation; and
- management-language change, corroboration, and contradiction.

Acceptance gates:

- obligation, outlay, ceiling, bookings, backlog, funded backlog, and GAAP revenue are never conflated;
- one-to-many program/company allocation is visible and never forced to sum without support;
- document claims carry filing/transcript page or passage provenance;
- estimates are labeled as estimates with reproducible inputs;
- PIT joins use the document publication/acceptance time; and
- Government Revenue cannot silently replace the central issuer or earnings authority.

### Wave 12 — validated confluence and authority proposal

Only after prospective evidence exists, test whether Government Revenue adds incremental value to Prophet/Neural Web beyond the existing baseline.

Required gauntlet:

- data availability and coverage thresholds;
- calibration and ranking lift against named baselines;
- regime and sector stability;
- source-outage and stale-data behavior;
- leakage and survivorship audit;
- capacity/liquidity and realistic timestamping;
- contradiction and retraction handling;
- shadow canary and kill switch; and
- independent approval through the Mastermind authority process.

An LLM, UI change, or strong backtest cannot promote authority. The first authority proposal should be narrow: one preregistered event family, a bounded issuer universe, explicit abstention, and rollback. Do not request blanket Government Revenue signal-origination authority.

### Wave 13 — breadth and commercial parity

After the investor-edge loop is validated, expand product breadth:

- grants, OTAs with source-native lineage, DIBBS, procurement forecasts, and GAO protests;
- state/local/education procurement if licensed sources justify it;
- bid/no-bid and capture workflows, teaming maps, incumbent intelligence, and pipeline collaboration;
- evidence-aware semantic search/RAG, MCP tools, alerts, exports, and APIs;
- user/account sync and team workspaces; and
- sector-lobe interoperability for biopharma, shipping/import-export, and future niches.

Investor foresight comes before CRM parity. Do not spend a wave reproducing every HigherGov/GovTribe capture-management feature while the forward event grader is still empty.

## Frontend and UX direction

Preserve the current premium operator-cockpit direction. The UI should feel like a billion-dollar intelligence SaaS product, but beauty must clarify state rather than obscure it.

- Keep ticker/company visibility primary: users should immediately see who is emitting, why, when, and with what evidence.
- Separate `Candidates`, `Watch`, `Mapping needed`, `Stale`, and `Unavailable`; do not bury them in one empty table.
- Use progressive disclosure: concise candidate cards → evidence packet → source receipt/lineage.
- Keep funded dollars, ceiling, action delta, confidence, coverage, and freshness visually distinct.
- Show counterevidence and abstention beside the thesis.
- Make unavailable and partial states designed states, not broken-looking placeholders.
- Keep responsive behavior native; no desktop table squeezed into mobile.
- Use motion only for changed state, new evidence, and graph traversal—not decoration.
- Prefer one coherent cross-lobe shell and shared design tokens when BioCatalyst and future shipping lobes converge; preserve sector-native workflows inside each lobe.
- Do not add a fused `AI score`. Users need inspectable catalyst families and named confluence legs.

Before a major new frontend surface, inspect the live page at desktop and mobile widths. Reuse the existing workbench, candidate, dossier, drawer, and data-sync contracts rather than introducing a parallel application shell.

## Claude's recommended first PR

Branch purpose: `govrev-award-event-spine-recovery`.

Do only Wave 9C persistence diagnosis and the minimum safe fix:

1. fetch `origin/main` and create a clean worktree;
2. reproduce the 2026-08-06 `ledger_write_failed` path from committed fixtures/artifacts without mutating canonical data;
3. capture the complete traceback and identify the exact column/value/schema conflict;
4. add the smallest regression fixture that fails before the fix;
5. make event serialization deterministic and Parquet-safe;
6. prove atomic rollback and last-good preservation;
7. materialize/activate the triad only if baseline eligibility rules are actually satisfied;
8. rebuild candidates and confirm the first baseline emits zero;
9. run focused and broader Government Revenue tests;
10. ship through PR, squash merge, render/deploy, `/api/health`, latest API, candidate API, and live-page checks.

Do not combine issuer expansion, Neural Web, Prophet, DoD budget, or new UI work into that recovery PR.

## Likely validation commands

Adapt to changed files and current repo guidance; do not blindly treat this as exhaustive.

```bash
python3 -m pytest -q \
  tests/test_usaspending_awards.py \
  tests/test_government_revenue_award_spine.py \
  tests/test_government_revenue_candidates.py \
  tests/test_build_government_revenue.py \
  tests/test_government_revenue_api.py

python3 scripts/build_government_revenue.py --help
python3 scripts/check_template_site_sync.py
python3 scripts/check_government_revenue_projection.py
python3 -m pytest -q tests/test_dashboard_cold_load_budget.py
git diff --check
```

Also run every focused test named by the touched modules plus the existing Government Revenue projection, UI/asset, recipient graph, dossier, subaward, IDV, budget, Neural Web, and Prophet contract tests when their boundaries are affected. Never weaken a failing authority or projection test just to unblock the render.

## Definition of done for every wave

1. Start from freshly fetched `origin/main` in a dedicated clean worktree/`codex/` branch.
2. Preserve unrelated work and stage only explicit task paths.
3. Update the contract, fixtures, tests, and handoff/status documentation together.
4. Run focused tests, broad relevant tests, syntax/template/projection guards, and `git diff --check`.
5. Push and open a PR targeting `main`.
6. Wait for required checks and squash-merge the same day.
7. Verify the merge is on `origin/main`.
8. Wait for render/deploy workflows and the VPS poller.
9. Verify `https://mastermind-x.com/api/health` has advanced to the merge or a descendant.
10. Verify the changed API/artifact and the live UI at desktop and mobile widths.

If a wave cannot complete this loop, report the exact blocked step and preserve a reproducible next command. Local code or an open PR is not completion.

## Non-negotiable prohibitions

- Do not use or retain competitor credentials.
- Do not copy authenticated competitor UI, code, models, or proprietary records.
- Do not infer issuer identity from a search ticker or fuzzy company name.
- Do not let identity coverage alone create a candidate.
- Do not backfill current state as historical knowledge.
- Do not emit first-baseline rows as events.
- Do not call an IDV relationship a vehicle seat without source proof.
- Do not call SBIR phase movement production conversion without an exact production award chain.
- Do not allocate a DoD budget line to a company by semantic similarity.
- Do not equate obligations, ceilings, backlog, bookings, or revenue.
- Do not claim 30-minute SAM freshness from a 30-minute scheduler when quota gates prevent it.
- Do not hide missingness or contradiction inside a fused score.
- Do not let Government Revenue alter Prophet candidates, rank, confidence, sizing, gates, or execution before explicit authority approval.
- Do not let an LLM originate, escalate, or self-authorize a signal.
- Do not rebuild shared company, document, market, or signal infrastructure owned by another lane.

## Ready-to-paste resume prompt for Claude

> Continue the Government Revenue Foresight build from `research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md`. Treat that file as the canonical current implementation checkpoint and `research/GOVERNMENT_REVENUE_FORESIGHT_MASTERPLAN_FOR_FABLE.md` as product/architecture authority. Read repo `CLAUDE.md`, `AGENTS.md`, the Wave 9 candidate docket, active build map, and do-not-rebuild registry. Verify GitHub and production state before trusting the dated snapshot. Start with the narrow Wave 9C award-event persistence recovery PR: reproduce the Aug. 6 `ledger_write_failed` error, capture the full traceback, add a regression, preserve atomic/last-good semantics, and activate the receipt-bound event triad only if baseline gates genuinely pass. First baseline must emit zero candidates. Do not add mappings, Neural Web, Prophet, budget, or UI scope to the recovery PR. Complete the repo's full branch → test → PR → squash merge → deploy → production verification loop before moving to the next wave.

## End state

The target is not a procurement-data clone. It is a clean-room, evidence-native Government Revenue intelligence lobe that can show which listed defense companies have a real, newly observed, economically meaningful procurement change; explain the exact source and issuer chain; test independent confirming or contradicting context; measure forward usefulness; and only then earn a narrowly governed role in Prophet and Neural Web.
