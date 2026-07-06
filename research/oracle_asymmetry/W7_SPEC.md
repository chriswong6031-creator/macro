# OTA W7 — Qualitative Fusion — Build Spec (pre-registered)

**Program:** Oracle Turn Asymmetry ([masterplan](../ORACLE_TURN_ASYMMETRY_MASTERPLAN_BY_FABLE.md) §W7). Authored by Fable 2026-07-06. The doctrine (masterplan §W7 + Part IV.2): **you don't backtest what you can't reconstruct point-in-time — you forward-test it under counting rules.** W7 builds the machinery: qualitative factors register as FILTERS on Turn Desk armed windows, get stamped PIT at window open, and earn or lose credibility purely on the forward ledger. No LLM originates any stamp; every filter is a deterministic predicate over committed PIT artifacts or operator-authored rows.

## 1. The filter registry — `data/oracle/qual_filters/registry.jsonl` (committed governance)
One JSON row per registered filter: `{id, lane: "Q1"|"Q2"|"Q3", description_en, description_zh, source_artifact (committed path), predicate (small declarative spec: field path + op + value, or "tape_touch" for Q3), registered_at, registered_by, status: "accruing"|"retired", fdr_family: "ota_qual", notes}`.
- **Lane law:** Q1 = archival-PIT text features — REQUIRES the source artifact to be as-of-t computed (registration must name the artifact's PIT law; a current-model recompute over old text is Q2, not Q1). Q2 = forward-only context filters (e.g. regime/radar states at window open). Q3 = operator tape (a `tape_touch` predicate: an operator_tape row whose nodes include the armed node, pit_stamp within ±3 sessions of window open, direction matching).
- **Proposal budget (metabolism law):** max 5 active filters per quarter; adding a 6th requires retiring one (retire = status flip, never delete; retired filters keep their accrued record). Registration is append-only.
- **Seed filters (registered in this PR, my Tier-0 lane):** F-Q2-RISKOFF: world_state/market-state verdict NOT risk-off at window open (source: the committed world_state or market state artifact — builder confirms exact path/field). F-Q2-HIGHVIX: vix_pctile ≥ 0.6 at window open (panel). F-Q3-TAPE: operator tape touch on the armed node (source: data/oracle/operator_tape.jsonl). Three seeds, all deterministic, all display-only.

## 2. Stamping + accrual (nightly, single-writer)
Extend the Turn Desk nightly step (or an adjacent step at END — builder picks the lawful seam): when a `window_open` row is written to `data/oracle/turn_desk_ledger.jsonl`, ALSO write a stamp row per active filter to `data/oracle/qual_filter_stamps.jsonl` (single-writer, keep-first key `window_key::filter_id`): `{window_key, filter_id, value: true|false|null, stamped_asof}` — evaluated strictly from artifacts as they exist that night (PIT by construction; null when the source is missing, never fabricated). At window maturity (the ledger's existing h=21 grading), a small accrual report artifact `data/oracle/qual_filter_accrual.json` recomputes per-filter conditional stats: windows n, member-fire WR21 with filter true vs false, Wilson LBs — DESCRIPTIVE, display-only, "validated" banned. When any filter reaches n≥15 true-stamped matured windows, the report prints "re-evaluation eligible (registration ota_qual family)" — evaluation is a Fable/operator event, never automatic.

## 3. Surface (minimal)
The Turn Desk panel gains one additive line per armed window listing true-stamped filters (bilingual, data-tip law) + a one-line accrual note ("qualitative filters accruing; n per filter"). No ranking, no gating, no scores.

## 4. Tests
Registry validation (lane law fields, budget enforcement at 5, retire-to-add); stamp idempotency (rerun same night = no dup rows); null-honesty (missing source artifact → value null, loud log, never false); Q3 tape-touch predicate (±3 sessions, node match, schema_note skipped); accrual math on a synthetic ledger+stamps fixture; template smoke.

## 5. Prohibitions
No LLM anywhere in the stamp/eval path; no retro-stamping of pre-existing windows (accrual starts at go-live — the whole point); no filter may gate/rank/score anything; frozen thresholds only via registration rows; all local CI guards before commit.

## Amendment log
- (none)
