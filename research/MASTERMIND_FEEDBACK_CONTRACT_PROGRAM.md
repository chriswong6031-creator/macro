# Mastermind → Neural Web Feedback Contract — Fable Program

Status: ACTIVE (rulings frozen 2026-07-06; W1/W2/W-M building)
Adjudicator: Fable (main loop). Source docket: Codex `fable_exit/02_MASTERMIND_BOOK_FILLS_FEEDBACK_CONTRACT_HANDOFF.md` (2026-07-07, freeze-spec only).
Related: `research/NW_MASTERMIND_BRIDGE_PROGRAM.md` (forward bridge), Mastermind `research/MASTERMIND_CONTROL_PLANE_MASTERPLAN.md` (MW3 feedback artifact v1, R2), Codex doc 08 (privacy-boundary audit — separate program; minimal enforcement piece ships here).

## §0 Verdict on the Codex docket

The docket's *direction* is right (the reverse loop is the missing frontier; measurement-first; counts-only public; freeze-before-data). Its *architecture* is wrong in five load-bearing places, established by census of both repos on 2026-07-06:

1. **The four proposed schemas already exist under other names.** `decision_event.v1` ≈ DecisionPacket + `packet_accepted/packet_rejected` run-events + `packet_rejections.jsonl` (stable `packet_id`/`rejection_id`, SHA-16). `fill_event.v1` ≈ per-book `fills.jsonl` (`{date, ticker, side, shares, price, value, from_pending}`). `outcome_event.v1` ≈ `data/brain/outcome_ledger.jsonl` (thesis-joined realized outcomes with decision-time lens snapshot). `held_book_snapshot.v1` ≈ `account.json` + `positions_ledger.json` + per-book `latest.json`. Building parallel writers would duplicate a live, tested control plane. **REJECT-REDUNDANT.**
2. **The public summary already ships.** `bridge/nw_feedback.py` → `site/mastermind/nw_feedback.json` (`mastermind_nw_feedback.v1`), counts-only, live secret-redaction, committed to this repo twice daily by `export_macro_snapshot.py`. The docket designs it from scratch. The real gaps: nothing on the Macro side consumes it; it lacks decision/outcome/context-audit counts; no Macro CI guard protects its counts-only invariant.
3. **The privacy premise is half-moot.** All seven books are PAPER (`paper_account.py`, $1M paper NAV, `/api/provenance` PAPER banner) and `mastermind_snapshot.json` already publishes held tickers, weights, and `opened_at` publicly by design. The genuinely private surface is the operator's real-money action ledger (`data/operator/`, gitignored) — out of scope here (FB-R15). The docket's leak-vector analysis is still correct and actionable (see §0.3).
4. **The slippage metrics are fiction for this system.** Paper fills execute at last close / next open. No spread, no participation, no venue. `fill_slippage_by_context`, `arrival_mid_slippage_bps`, `spread_paid_bps`, `participation_band` are unmeasurable. Registered as **BLOCKED**, printed honestly, not faked (FB-R9).
5. **`context_seen_rate` has no substrate.** The NW reader's `audit_row()` lands only in gitignored per-session brain runlogs. Needs a persistent sidecar at the source (W-M).

What the docket got right and this program keeps: measurement-before-behavior; counts-only public; `state: absent` over fabricated zeros; freeze IDs/fields/metrics/bars now; authority `context_only` at birth with a shrink/de-escalate-only ceiling; `site/feeds/` and public R2 forbidden for feedback.

### §0.3 Confirmed leak gaps (fixed by W1)

- `data/private/` is **not** in `.gitignore` — nightly blanket `git add data/ site/ reports/` (daily.yml:1146) would stage the docket's own proposed private path on first write. The docket proposed the path without the rail.
- No CI guard scans committed public artifacts for private fields or host paths.
- `data/governance/operator_grading.json` commits a local absolute `ledger_path` today (producer: `engine/operator_grading.py`).

## §1 Rulings (FB-R1..R15, binding)

Answers to the docket's ten freeze questions, plus five structural rulings.

- **FB-R1 (tickers).** No Macro-side raw mirror exists in v1, so "can Macro-private see tickers" is moot. Paper-book tickers remain public via `mastermind_snapshot.json` (standing, unchanged). **No feedback artifact may add a new ticker-bearing public surface**; feedback artifacts are counts-only. Real-money operator data never crosses into any Macro path, private or public.
- **FB-R2 (sole writer).** Mastermind is sole writer of all reverse-feedback artifacts (`site/mastermind/nw_feedback*.json`). Macro readers are read-only; no Macro engine module may write under `site/mastermind/` (guard-enforced).
- **FB-R3 (append-only).** Raw substrates keep their existing conventions: `fills.jsonl` / `outcome_ledger.jsonl` / `run_events.jsonl` / new `nw_context_audit.jsonl` are append-only; state files (`account.json`, `latest.json`) remain snapshots. No rewrites of history.
- **FB-R4 (IDs).** Adopt the existing ID landscape verbatim: `packet_id` = SHA-256[:16] of `book|asof|submitted_at|run_id`; `rejection_id`; `thesis_id`; `run_id`. **No new ID namespace.** The known join gap (fills carry no thesis/packet ref) is fixed at the source with additive optional fields, forward-only (W-M stretch).
- **FB-R5 (book_id).** Public at book granularity — already public in the snapshot and `nw_feedback.v1` `books[]`. Not private.
- **FB-R6 (retention).** Raw stays in the Mastermind repo (local-only, no remote) indefinitely. No Macro raw mirror in v1 ⇒ no retention question. If a future mirror is ever proposed: gitignore + guard proof first (W1 pre-builds both), 90-day rolling cap, separate ruling.
- **FB-R7 (Macro storage).** Macro stores only: the committed counts artifacts Mastermind pushes, plus its own derived counts-only summary. No event-level storage on the Macro side.
- **FB-R8 (public fields).** Allowed: schema, generated_at/asof, window_days, state (present|stale|absent), and counts — thesis counts, run counts, gate failures by severity/guard, packet accept/reject counts, outcome-band counts, lock/stale counts, context-audit counts (n_runs context present/stale/absent), and counts-only metric-family aggregates. Forbidden in feedback artifacts: tickers, position/fill/decision/rejection IDs, shares, notional, avg_cost, NAV/PnL dollars, account/broker/venue, raw prose from LLM packets, absolute host paths, sub-day timestamps beyond generated_at.
- **FB-R9 (first metric families).** Frozen in §3. Measurable at birth: `context_engagement`, `decision_flow`, `outcome_mix`. Registered-BLOCKED (printed, not computed): `fill_slippage_by_context` (no execution model), `warning_outcome_delta` (needs ≥60 context-audit sessions + warning taxonomy).
- **FB-R10 (gauntlet).** Any behavior change (de-escalation or shrink-only, the ceiling) requires: ≥60 sessions of context-audit accrual, the preregistered `warning_outcome_delta` printed with sign stability across two non-overlapping eras, a Fable-tier promotion ruling, and a governance-ledger event on the Mastermind side. Nothing at birth: `authority_for_macro: context_only`, all authority booleans false.
- **FB-R11 (derive, don't duplicate).** No new writers at decision/fill/outcome seams. The exporter (`bridge/nw_feedback.py` v2) derives all feedback counts from existing ledgers. The only new raw substrate permitted is the `nw_context_audit.jsonl` sidecar, because `context_seen_rate` has no persistent substrate today.
- **FB-R12 (transport).** Counts cross the boundary only via the existing `export_macro_snapshot.py` push into `site/mastermind/`. `site/feeds/` (public R2 machine plane) and `publish_r2.py` dirs are forbidden for feedback artifacts. `data/private/` is reserved + gitignored as a defensive rail but has **no writer** in v1.
- **FB-R13 (rail first).** The privacy rail (gitignore + CI guard + host-path scrub) merges before or with any new feedback field. The guard self-tests with known-bad fixtures.
- **FB-R14 (absence).** Missing/old source degrades to `state: absent` / `state: stale` — never fabricated zeros. Matches the NW reader's 4-day staleness convention.
- **FB-R15 (scope).** The operator real-money surface (`data/operator/` action ledger) is outside this contract. Its public face remains the existing counts-only `operator_exposure_summary.json`. Doc 08's full `privacy_classes.yml` taxonomy is a separate future program; this program ships only the enforcement pieces it needs (the guard).

## §2 v1 architecture

```text
Mastermind (private, local-only repo; sole writer)
  run_events.jsonl ─┐
  packet ledgers    ├─ bridge/nw_feedback.py v2 (derive + redact, counts only)
  outcome_ledger    │        │
  nw_context_audit ─┘        ▼
                    site/mastermind/nw_feedback.json   (mastermind_nw_feedback.v2)
                             │  existing export_macro_snapshot.py push (2×/day)
                             ▼
Macro (public repo)
  engine/neuralweb/mastermind_feedback.py  (read-only, v1/v2-tolerant, staleness-gated)
                             ▼
  data/governance/mastermind_feedback_summary.json  (neuralweb.mastermind_feedback_summary.v1,
                             counts-only, state present|stale|absent, guard-scanned)
Rails: .gitignore data/private/ ; scripts/check_private_boundary.py in CI
```

No raw event ever leaves the Mastermind repo. The strongest change vs the docket: **zero data movement of private raw material, ever** — metrics are computed where the data lives.

### §2.1 Canonical `mastermind_nw_feedback.v2` shape (FROZEN 2026-07-06)

Frozen after review round 1 caught the producer and consumer implementing *different imagined* v2 shapes (the recurring imagined-schema failure class). The exporter's real emitted shape is canonical; both sides' tests pin it:

```json
"decision_flow": {
  "by_book": [{"book_id": "flagship", "packet_accepted": 1, "packet_rejected": 1}],
  "rejection_error_classes": {"falsifiers": 1, "expected_failure_mode": 1}
},
"outcome_mix":  {"state": "ok|absent", "n_resolved": 3, "by_outcome": {"1": 2, "0": 1}},
"context_audit": {"state": "ok|accruing", "n_present": 1, "n_stale": 1, "n_absent": 1,
                   "n_runs_total": 3, "context_seen_rate": 0.333},
"metric_families": {"live": ["..."], "blocked": [{"name": "...", "reason": "..."}]}
```

Rules: every label key (`rejection_error_classes`, `by_outcome`, `book_id`) is sanitized at the producer (`_sanitize_key`) AND re-validated at the reader (`^[a-z0-9_]{1,40}$`), capped (≤10 producer / ≤12 reader); `state` is always present in `outcome_mix`/`context_audit` (no shape-switching between populated and absent forms); `context_seen_rate` clamped [0,1] at the reader; absence forms carry zero-event counts honestly under an explicit non-`ok` state, never fabricated zeros under `ok` (FB-R14). Additive-only evolution from here; any v3 field lands in this section before code.

## §3 Preregistered metric families (frozen before outcomes are seen)

| Family | Definition (counts-only) | Status at birth |
|---|---|---|
| `context_engagement` | Per window: n_runs with nw_context present / stale / absent (from `nw_context_audit.jsonl`); `context_seen_rate` = present / total | LIVE (W-M) |
| `decision_flow` | Per book, per window: packet_accepted, packet_rejected counts (from run_events); rejection top-error class counts (sanitized labels only) | LIVE (W-M) |
| `outcome_mix` | Per window: resolved-outcome counts by band from `outcome_ledger.jsonl` (`outcome` field), n_resolved, n_open | LIVE (W-M) |
| `warning_interaction` | Warning-present × operator/brain action cross-counts; requires a frozen warning taxonomy (contradictions / risk flags in the forward context) | REGISTERED — needs taxonomy ruling before compute |
| `warning_outcome_delta` | Outcome mix conditioned on warning-followed vs warning-ignored | BLOCKED until ≥60 context-audit sessions (FB-R10) |
| `fill_slippage_by_context` | — | BLOCKED — no execution model exists (paper fills at close/open). Do not fake. |

Promotion bar: none of these carry authority. They are audit/learning substrate only (FB-R10 governs any future use).

## §4 Waves

- **W1 (Macro PR-A):** privacy rail. `.gitignore` += `data/private/`; `scripts/check_private_boundary.py` (+ `--selftest`, known-bad fixtures) wired into ci.yml; `engine/operator_grading.py` stops emitting absolute `ledger_path` (basename + `ledger_present` bool), artifact regenerated; this program doc.
- **W2 (Macro PR-B):** reader. `engine/neuralweb/mastermind_feedback.py` + `data/governance/mastermind_feedback_summary.json` + synapse.yml registration + daily.yml non-fatal step + tests (poisoned-fixture leak test mandatory).
- **W-M (Mastermind, local merge):** `bridge/nw_feedback.py` v2 additive counts (schema bump to `mastermind_nw_feedback.v2`), persistent `data/brain/nw_context_audit.jsonl` sidecar written at the flagship seam, optional additive `thesis_id`/`packet_id` on new fills rows, tests in worktree only; local merge to master + uvicorn restart per control-plane safe pattern.
- **W3:** haiku leak sweep over committed public artifacts (report feeds W1 guard scoping); memory + Obsidian-visible program doc.

## §5 Acceptance checklist (v1)

- [ ] `git check-ignore data/private/probe` passes in CI (guard self-test).
- [ ] Guard fails on fixtures containing: ticker key in a feedback artifact, absolute `/Users/` path, `$`-amount, fill/position/decision id keys.
- [ ] `operator_grading.json` carries no absolute host path; producer fixed at source.
- [ ] `mastermind_feedback_summary.json` is counts-only under poisoned input (fields stripped or artifact refused, test-proven).
- [ ] Missing `nw_feedback.json` ⇒ `state: absent`; `generated_at` older than 4 days ⇒ `state: stale`.
- [ ] `nw_feedback.v2` adds only counts; secret-redaction guard retained; v1 readers unbroken.
- [ ] No feedback path under `site/feeds/` or in `publish_r2.py` dirs.
- [ ] Authority block absent-or-context-only everywhere; no authority booleans set true.

## Status log

- 2026-07-06 — Census (2 lanes) + adjudication; rulings FB-R1..R15 frozen; W1/W2/W-M dispatched.
- 2026-07-06 — Review round 1 (opus, all three lanes): PR-A guard coverage broadened to glob-based full scans + e2e traversal test; PR-B FIX-FIRST (dag.yml gate red; v2 label-passthrough leak; imagined-schema mismatch vs exporter); W-M hardening (by_outcome sanitize+cap, key-axis redaction backstop, real sidecar seam test). §2.1 canonical v2 shape frozen in response. Every lane's review caught ≥1 real defect — scorecard holds.
