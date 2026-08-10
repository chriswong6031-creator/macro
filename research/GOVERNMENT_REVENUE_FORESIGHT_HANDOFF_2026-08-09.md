# Government Revenue Foresight — session handoff, 2026-08-09 ~11:05Z

Successor to `research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md` (the Codex handoff; still the wave-spec reference for 10/11/12/13). This document is the operational state as of the 2026-08-08→09 orchestration session. Everything below was verified at write time and is timestamped; **re-census before acting — the fleet moves hourly.**

## §0 First moves, in order

1. **Census, don't trust this snapshot.** `gh pr list --state open --limit 100` and check membership of the queue below by number — NEVER with a small `--limit` (a truncated listing mis-reported two PRs as merged this session; memory: `list-limit-pagination-fakes-merges-in-monitors`). Then `gh run list --workflow ci.yml --branch main --limit 2` for main health.
2. **If main is green and PRs merged:** run the reconciliation pass — for any queue PR whose packs concluded red against a since-healed base, rebase its branch (worktree map in §6) onto `origin/main` and push; the armed `merge-on-green` label persists and the sweeper merges on green. Do NOT rebase while main is still red or the runner queue is saturated (each push queues 4 pack jobs; check `gh run list --workflow ci.yml --limit 30 --json status` — 19 queued at last look).
3. **If the marketing / intl-collectors reds still pin main:** they have sibling owners (#5087 marketing fixtures, #5036 pack-hardening — #5036 was fully green at last look). Check for their merges before considering any heal of your own; memory law: `check-for-a-sibling-heal-pr-before-fixing-a-pack-red`.
4. **After the wave merges: verify the first pipeline cycle** (§4 checklist). The 30-minute live lane (`government-revenue-live.yml`) or the nightly regenerates the workspace/queue; the first cycle whose checkout includes #5009+#5086+#5085(+#5090) is the lobe's first possible candidate emission, ever.
5. **Then ship the session record** — the full narrative draft exists only in the dead session's scratchpad; §2–§5 here carry the load-bearing content. If a longer record is wanted, reconstruct from the PR bodies (each is self-documenting).

## §1 The queue (12 open + 1 merged at write time, all armed `merge-on-green`)

| PR | Branch | What it is |
|---|---|---|
| #5009 | `claude/govrev-9d-publish-8fb51e` | **Wave 9D published**: `recipient-graph:reviewed:2026-08-08:defense19-v1` — 19 issuers / 101 entities / 203 identifiers, operator approval of 2026-08-08 quoted in `research/government_revenue/RECIPIENT_GRAPH_REVIEW_2026-08-08_defense19.md`. Live-probe test re-pinned to the empirically-verified truth (500 events visible, zero eligible) |
| #5086 | `claude/govrev-enum-heal-8fb51e` | **THE structural fix**: event schema admits `issuer_legal_entity` — the only terminal edge the curator writes; every issuer impact had been workspace-rejected since #4255. Plus rejected-count CI guard + attribution-grade cap ordering + truncation disclosure |
| #5085 | `claude/govrev-families-8fb51e` | Snapshot-rail families admitted (`reported_obligation_balance_changed`; contained-ceiling from `award_value_changed`) with amount-class-correct labels; projected first candidates: 8, all HII |
| #5090 | `claude/govrev-actionid-8fb51e` | Action-rail identity under named basis `award_level_recipient_at_collection` (precedence never union; basis on every impact/candidate). Fixed a generation-binding brick the diagnosis missed. Proof: 20 action-rail candidates |
| #5038 | `claude/govrev-grader-heals-8fb51e` | Grader integrity (16 audit findings: NaN endpoints abstain, paired-N + independence floors, log-side immutability, `mapping_missing`) + prereg amendments inside the proven-empty-ledger window + **the GRV_FA1 action-rail fence** (`family_rail_mismatch` abstention — must be merged before first issuance; it is in this same wave, so ordering is safe) |
| #5040 | `claude/govrev-ledger-identity-8fb51e` | Ledger identity survives graph edits: dedupe `(candidate_id, known_at)`, order-stable graph digest. Prerequisite for defense20 |
| #5021 | `claude/govrev-9ef-8fb51e` | Waves 9E+9F: shadow packets (11 legs, byte-identical with NW absent) + Prophet post-selection annotation (fail-open, import-boundary test) + `research/GOVERNMENT_REVENUE_PROPHET_INTEGRATION_RULING_2026-08-08.md` |
| #5014 | `claude/govrev-idv-bridge-8fb51e` | Wave 10 rail 1: exact IDV child bridge — honest zero with population math printed |
| #5012 | `claude/govrev-sbir-8fb51e` | Wave 10 rail 3: SBIR collector (10 req/10 min pacing, PII never persisted, synapse-registered) |
| #5013 | `claude/govrev-audit-8fb51e` | Prophet discloses a dead award-event rail instead of only acting on it |
| #5034 | `claude/heal-datafed-packs-8fb51e` | ETHA crypto check by measured \|t\|-rank (37/37 windows) replacing #5032's \|beta\| band |
| #4950 | `claude/govrev-nonadd-8fb51e` | Amount-semantics guard (never merged despite an earlier mis-report; re-armed) |
| #4951 | — | BWXT discovery repair — **MERGED 08-09**; next collect gathers BWXT recipients → enables defense20 |

Known interaction: if #5009 merges before #5086 and a pipeline cycle runs in the gap, the committed workspace briefly carries `rejected: 9`, and #5086's own guard may red against it — self-heals one cycle after #5086 merges; rerun its packs then rather than diagnosing a new defect.

## §2 Why the lobe printed zero forever — the three structural blockers

Adversarial review with positive controls (control run: enum widened + identity attached → **20 candidates, all HII** — machinery proven end-to-end):

1. **The enum (since #4255):** `government_procurement_event.v2` forbade `issuer_legal_entity`, the only relationship the graph contract permits to carry `parent_company_id`. Every reviewed ownership path's terminal edge failed validation; every impact was silently dropped at `workspace._validated_award_events`, for every graph including PLTR's. Shipped dark because fixtures used a curator-impossible edge shape AND bypassed the workspace. → #5086.
2. **Rail disjunction:** the action rail (produces all previously-admitted candidate families) had 0/35,140 recipient UEIs; the snapshot rail (166/166 UEIs) produced only unadmitted families. → #5090 + #5085.
3. **The cap:** `MAX_WORKSPACE_EVENTS=500` let reviewed events survive only on a `known_at` tiebreak; 30 mapped events were already truncated behind 610 unmapped. → #5086.

Memory: `govrev-lobe-never-emitted-structural-enum`. The generalized lesson: **a fixture that is contract-legal but producer-impossible validates the wrong world** — fixtures must use the shapes real producers emit and flow through the real validation path.

## §3 Rulings in force (do not re-litigate)

- **Integration ruling** (committed with #5021): the lobe owns the WHY as named legs (incl. PIT market-context legs at candidate `known_at`); Prophet keeps sole pick authority (annotation only, byte-identical on/off); the grader + Wave 12 gauntlet is the only promotion path. No fused super-score anywhere. Memory: `govrev-prophet-integration-ruling`.
- **Named-basis identity** (#5090): award-level recipient identity attaches to action rows only as a distinct, provenance-named field with a collection-time clock — never by widening transaction-asserted identity. Precedence, never union.
- **GRV_FA1 rail fence** (#5038): the registered family is action-rail only; snapshot-rail obligation candidates abstain `family_rail_mismatch`. A snapshot-rail family is a future deliberate preregistration, not a ride-along.
- **Ledger identity** (#5040): issuance dedupe on `(candidate_id, known_at)`; anti-backfill applies to first-seen candidate_ids only. `observation_id` deliberately excludes `identity_basis` (basis is descriptive, never a stratum).
- **Live-probe philosophy**: the landed snapshot-tripwire design stands — truth-moving PRs re-pin the live probes in the same change (as #5009 does). Availability/source-health use the builder's own derivations; era pins are deliberate human tripwires.

## §4 First-candidate verification checklist (after the wave + one pipeline cycle)

Read the committed artifacts on origin/main (`data/government_revenue/`): `coverage.award_events.rejected == 0`; truncation counters present and reviewed-truncation zero; `exact_candidate_availability` follows the engine derivation (`available` iff candidates exist); expected first set on the order of 8 snapshot-rail + 20 action-rail candidates, **all HII initially** (the 8-per-entity top-value sample concentrates recent modifications; breadth accrues nightly); ledger's first rows appear under post-#5040 identity; grader admits only action-rail rows into GRV_FA1 (snapshot rows abstain `family_rail_mismatch`); candidate radar site page renders the candidates with the authority block intact. Zero after all of that concludes something new — investigate, do not force.

## §5 Roadmap + gated items

- **Defense20 (BWXT)**: after a post-#4951 collect lands BWXT recipients → run `scripts/propose_government_revenue_recipient_graph.py` for BWXT → review worksheet → publish via `scripts/curate_government_revenue_recipient_graph.py` citing the 2026-08-08 operator approval precedent (fresh operator ack preferred). #5040 must be merged first (it is in the wave). GE stays unmapped (`no_exact_match` — correct negative control).
- **Wave 10 rails 2/4/5** (DoD budget receipts; SAM lifecycle — quota-gated ~00–01 UTC, never claim intraday freshness; recompete outcome) — specs in the account handoff.
- **Wave 11** (earnings/revenue translation), **Wave 12** (gauntlet + narrow authority proposal — only after the grader accrues prospective evidence).
- **Designer-lane surface pass** (queued as a session task): SBIR/IDV/shadow-context surfaces, `shadow context / 影子背景` labels are schema `const`s awaiting UI, `semanticLabel` lacks `delta_*` entries, workspace fact-grid `slice(0,4)`.
- Small follow-ups: `ceiling_changed` direction is sign-blind (possible_positive even for cuts); IDV prime-cut widening decision (452 enumerated children vs collect budget); HK ffill mirror fix (chip session was started by the operator — check for its PR before re-doing).

## §6 Worktree/branch map (rebases happen in these; never touch another fleet's checkouts)

All under `Macro Dashboard/.claude/worktrees/`: `agent-a08fd69211e86c6b5`→#5009 · `govrev-enum-8fb51e`→#5086 · `govrev-families-8fb51e`→#5085 · `govrev-actionid-8fb51e`→#5090 · `govrev-grader-8fb51e`→#5038 · `govrev-ledger-8fb51e`→#5040 · `agent-a1286dc6e1cce7bb3`→#5021 · `agent-a6830edb30eae2b75`→#5014 · `agent-a1fe68f9f113afa1b`→#5012 · `agent-aade77e5a389a451a`→#5013 · `heal-datafed-8fb51e`→#5034 · `govrev-nonadd-8fb51e`→#4950. A stale-worktree warning: several are behind main; always `git fetch origin main` and rebase rather than trusting checked-out file state (memory: `stale-worktree-diagnoses-a-fixed-bug`).

## §7.5 Addendum ~23:30Z — the first emission wedged on the ledger's own anti-backfill gate (healed)

§0.4's "first possible candidate emission" happened at #5086's merge (17:35Z) and immediately wedged BOTH lanes for six hours: the post-merge `government-revenue-live` rebuilds (17:42Z, 17:55Z push; 21:44Z dispatch) all died in `project_candidate_artifacts` with `new candidate observation is not forward of the prior frozen generated_at clock` on the 8 first candidates, so `data/government_revenue/latest.json` stayed at the pre-#5086 generation (`coverage.award_events.rejected: 9`), which #5086's own render guard rejects — freezing every site render (first red: render run 31333981567, 20:19Z). Mechanism: the 8 first candidates carry `known_at = 2026-08-08T11:58:31Z` (immutable first-seen event clock) while every pre-#5086 zero-candidate generation kept advancing the frozen state clock (17:19Z at wedge time) — so the Wave9A anti-backfill gate saw never-issued hypotheses with historical clocks, i.e. a "backfill", forever: first-seen evidence clocks never move forward, and no collect can unwedge it. Heal (this session): the gate now records first issuance into an **empty** ledger — a ledger with zero issued rows has no issuance history to backfill, and the frozen clock only proves prior generations issued nothing (their own committed workspace says why: `rejected: 9`) — with a `::notice` annotation, each row keeping its honest evidence `known_at` beside the issuing run's `generated_at`; the gate arms permanently once any row exists. The grader already treats the shape correctly (`covers()` refuses silently re-cut entries; `min_distinct_known_at_months` counts same-clock rows as correlated), and entry = first session strictly after 08-08 = Monday 08-10, so all 8 grade fully prospectively. **Trap for the next admission repair:** once the ledger is non-empty, a future contract-widening fix that surfaces never-issued candidates with historical clocks will re-wedge exactly like this — that case needs its own adjudicated escape (e.g. plumbed proof that the prior generation's admission was broken), not a quiet weakening of the gate.

## §7 Traps this program hit twice or more (read before debugging anything)

`list-limit` truncation faking merges · sibling-heal-first (three sessions raced duplicate heals of the same reds this session — #5031/#5032/#5034) · live probes pinning snapshots = scheduled reds on every data advance (re-pin in the truth-moving PR) · gh quota is one shared bucket (90s+ poll floors, one watcher per endpoint) · harness worktree-add can time out (pre-create worktrees with a 600s Bash timeout, then spawn) · box contention makes local pytest bimodal (packs queue behind 5+ parallel runs) · "check passes because it cannot see" — every major defect this program found wore that shape; demand positive controls.
