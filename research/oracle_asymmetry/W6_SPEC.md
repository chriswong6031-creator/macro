# OTA W6 — Rotation Turn Desk — Build Spec (pre-registered design)

**Program:** Oracle Turn Asymmetry ([masterplan](../ORACLE_TURN_ASYMMETRY_MASTERPLAN_BY_FABLE.md) §W6). Authored by Fable 2026-07-06 from the wf_ec771ef4 scouts, under the **CONFIRMED — DISPLAY-WITH-EDGE** verdict ([#1533](https://github.com/chriswong6031-creator/macro/pull/1533)) and the forward promotion rule pre-registered in `W2_FORMAL_PREREG.md` §5. DISPLAY-ONLY under hard law: the desk feeds no score, gate, or ordering; enabling any such consumption is a constitutional authority event.

## 1. What the desk shows (one panel, bilingual)
Per armed sector, nightly: (a) **armed state** — A15 fired within the last 10 sessions (window open, sessions remaining); (b) **member fires inside the window** — today's T1–T3 cascade fires in that sector with tier, provisional flag (T3 repaint ~23.8% — badge required), freshness, and the board's entry/stop context; (c) **the class-stamped base rates** — IN-window member fires WR21 65.2% vs 53.6% outside, holdout Δ+10.7pp CI [+3.8, +17.9] (#1533), printed WITH: `display-with-edge` stamp, modern-track window (≥2022-06-30), 31-window evidence base, growth/cyclical tilt (defensive sectors were negative), "not a forecast" line; (d) **the promotion clock** — accrued new windows vs the ≥15 re-evaluation trigger. If no sector is armed: the panel says so (quiet state is a state).

## 2. Producer (oracle_nightly step 15 — additive at END)
`scripts/oracle_nightly.py` gains `_step_turn_desk()` after step 14, loud-error pattern, failures list entry. It:
1. **Armed windows:** recompute A15 entry dates on the latest panel via `engine/oracle/compounds.get_entry_dates` (same grammar code as step 11) — do NOT trust `live_ledger.jsonl` for A15 (scout finding: no A15 rows accrue there today; logged as an ops finding, see §6). Window = fire→+10 sessions, merged per node.
2. **Member fires:** read `site/factordata/us_standouts.json` (buy+watch rows, `signal.tier_cascade ∈ {T1,T2,T3}`, top-level `sector` field → node via the GICS map) and `site/factordata/signal_gate.json` for universe-wide cascade verdicts. **Staleness honesty:** these are built by `build_site`; the desk payload carries BOTH `asof` (panel) and `member_fires_asof` (us_standouts `as_of`) — printed on the panel when they differ.
3. **Artifact:** `site/basketdata/oracle_turn_desk.json` (`schema: oracle_turn_desk.v1`; fields: asof, member_fires_asof, armed[] {node, name_en/zh, fire_dates, window_end, sessions_remaining, member_fires[] {ticker, tier, provisional, fresh_bars, label}}, base_rates {…, confidence_class: "display_with_edge", lineage: "#1533 W2_FORMAL_RESULTS"}, promotion_clock {windows_accrued, windows_required: 15}, disclaimers). Envelope: `stamp_if_changed(payload, prev, artifact_id="oracle-turn-desk")` — five sibling keys, never a wrapper. **Banned-implication keys law:** no field name containing forecast/predicted/target/expected_return.
4. **Forward ledger:** `data/oracle/turn_desk_ledger.jsonl` (nightly = sole advancer; keep-first). Row kinds: `window_open` (key `node::a15::fire_date`), `member_fire` (key `window_key::ticker::fire_date`), and maturity updates at h=21 grading `fwd_ret_21` ABSOLUTE from `massive_stock_day` closes (single-source law — never yahoo for grades). `pit_stamp` = panel asof; `registered_at` = UTC wall clock. This ledger is the accrual instrument for the registered §5 promotion rule — no peeking logic in code; the desk only displays counts.

## 3. Surface (templates/subsector_rotation.html.j2 — additive)
New `<section class="td-section">` inserted after the existing `.tm-section` (no existing HTML modified). All strings through the page's `t(en, zh)` macro; tooltips via `data-tip-en`/`data-tip-zh` ONLY (check_title_i18n law: no CJK or t() in `title=`). Copy constraints: the word "validated" MUST NOT appear (CI: `scripts/check_validated_claims.py`); descriptive/base-rate language only; the §W2 caveats block is not optional.

## 4. Wiring & CI tripwires (each verified locally before commit)
- `config/synapse.yml`: new `oracle-turn-desk` entry (tier `display`, producer oracle_nightly, cadence daily-engine, schema oracle_turn_desk.v1, consumers: subsector_rotation.html). Ledger registered too if registry law requires ledgers (check existing forward_ledger precedent — mirror it).
- `tests/test_signal_bus_doc.py`: bump the hardcoded artifact-count assertion (read the CURRENT count from the file — main churns; do not assume 110) + regenerate `docs/SIGNAL_BUS.md` via `python -m scripts.gen_signal_bus_doc` (byte-freshness gate).
- `config/dag.yml`: declare step 15 in the oracle nightly lane (lane law: undeclared drift reds CI) — run `python -m scripts.check_dag_conformance --selftest` and the real check.
- Run locally before commit: `check_synapse_registry.py`, `check_title_i18n.py`, `check_validated_claims.py`, `check_dag_conformance.py`, targeted pytest (signal-bus, synapse, new desk tests).
- Contract: `engine/oracle/contract.py` is NOT extended (desk is its own artifact); `oracle_state.json` untouched.

## 5. Tests
Synthetic fixtures: armed-window recompute + merge (incl. no-fires → quiet payload); member-fire join (sector map, buyable-tier filter, provisional flag carried); staleness dual-asof honesty; ledger keep-first (re-run same night = no dup rows); maturity grading from a crafted massive series (next-bar, absolute); banned-key guard on the payload; template render smoke (section present, no title= violations).

## 6. Ops finding to file (not this PR's code)
Step-11 live accrual shows zero A15 rows despite A15 in the committed registry — either a registry-vintage issue on the runner or a status filter gap. File one row into `data/oracle/hypothesis_inbox.jsonl`-adjacent review flow via the report (a note in the PR + masterplan status log) for the Oracle program to verify after tonight's nightly. Do not fix step 11 in this PR (out of scope).

## 7. Prohibitions
No score/gate/ordering consumption of the desk artifact anywhere; no oracle_state.json changes; no nav chrome changes (the panel lives on the existing page); no new nightly steps other than 15; no LLM anything; render-budget: step 15 must be O(seconds) (reads existing artifacts + one get_entry_dates call).

## Amendment log
- (none)
