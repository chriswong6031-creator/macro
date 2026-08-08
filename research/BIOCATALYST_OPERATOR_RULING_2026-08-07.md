# BioCatalyst — operator ruling, 2026-08-07

| Field | Value |
|---|---|
| Authorizing operator | Repository operator (chriswong6031-creator), in session, 2026-08-07 |
| Instruction given | "yes for both, do for me" — in response to `research/BIOCATALYST_OPERATOR_DECISIONS_2026-08-07.md` |
| Rulings | (1) enable ClinicalTrials.gov Record History ingest; (2) admit the sponsor→ticker candidate rows |
| Recorded by | Claude Fable 5, overnight autonomous session |

This document exists so that two irreversible-ish acts carry a named authorizer, a date, and the
material facts that were on the table when the authorization was given. It is the evidence
trail; the config changes are the effect.

---

## Ruling 1 — ClinicalTrials.gov Record History ingest is ENABLED

`config/biocatalyst_sources.yml` → `clinicaltrials_gov_record_history`:
`rights_state: operator_review_required_before_enable` → operator-reviewed;
`production_ingest_allowed: false` → `true`.

### Material facts recorded at the time of the ruling

These were surfaced to the operator, and two of them were surfaced **after** the initial "yes"
because they were discovered while executing it. They are recorded here rather than buried.

1. **This is an undocumented internal endpoint, not the public API.**
   `base_url: https://clinicaltrials.gov/api/int/studies` with
   `interface_stability: undocumented_ui_backing_route` and
   `source_shape_canary_required: true`. The program's own handoff says *"never casually enable
   undocumented history transport."* This ruling is therefore **not casual**: it is named, dated,
   attributed, and carries a canary requirement that stays mandatory.
2. **Enabling the rights flag does NOT start collection.** Three gates exist and this ruling
   clears exactly one:
   - `production_ingest_allowed` — rights. **Cleared by this ruling.**
   - `production_enable_env: BIOCATALYST_ENABLED`, `default_enabled: false` — runtime. Still off.
   - `allowlist_config_env: BIOCATALYST_CANARY_NCTS`, `default_allowlist: []` — universe. Still
     empty, and the universe is `explicit_nct_allowlist` / `exact_b1_current_nct_set`.
   There is also **no installed worker or timer** for record-history collection.
3. **Distribution obligations attach to every surface that displays this data**, from the
   source's own `distribution_obligations`: attribute ClinicalTrials.gov; display the source
   processing date; keep projected data current; disclose content modifications; do not assert
   proprietary rights over the source database; do not use extracted email addresses for
   marketing; display the source submitter-responsibility note.

### What this ruling does and does not do

**Does:** clears the rights gate, which makes `trial_progression_termination`, `timing_slip` and
`enrollment_site_change` gate-eligible for clock activation.

**Does not:** start any collection, install any service or timer, publish anything, or open any
clock by itself. **A clock is NOT opened by this ruling.** Opening a clock over a source with no
collection path would record "accruing since 2026-08-07" while accruing nothing — the exact
fabrication this program exists to prevent. The clocks open only once a collection path exists
and is proven, and the activation receipt remains the authority, not any config file.

### Consequent obligations, now live

- The **source-shape canary** stays mandatory. An undocumented route can change without notice;
  the canary is the tripwire and must fail closed.
- The seven distribution obligations above bind any projection or UI surface built on this data.
- The universe stays `explicit_nct_allowlist`. This ruling does **not** authorize an unbounded
  crawl, and coverage remains earned by a recorded denominator, never by a query string.

---

## Ruling 2 — Sponsor→ticker candidate rows are ADMITTED

`config/biocatalyst_sponsor_ticker_map.yml`: the **29 `candidate_unreviewed` rows** are admitted
to `reviewed_admitted` under this operator's authorization, attributed and dated.

**The 20 `ambiguous_queued` rows stay queued.** A blanket "yes" cannot resolve a genuine
ambiguity — a subsidiary-versus-parent or joint-venture question needs a per-case answer, and
treating "admit the candidates" as "admit everything" would convert exactly the uncertainty the
queue exists to preserve into false confidence. Those 20 remain a standing operator to-do.

### What changes in the enforcement, and what does not

The test `test_committed_map_carries_no_admitted_row_so_a_model_cannot_self_promote` is **not
deleted**. It is strengthened: an admitted row must now carry an **operator attestation** —
named reviewer, timestamp, and a reference to this ruling. A model still cannot self-promote a
row, because it cannot manufacture an attestation that names a human authorizer and a ruling
document. The fence moves from "nothing may be admitted" to "nothing may be admitted without
attributed human authority", which is the stronger and more useful invariant.

### Authority boundary, unchanged

Admission unlocks `BC-P1` **post-selection context only**: after Prophet selects a name,
BioCatalyst may explain that name's trial and regulatory state. The map may not originate, rank,
reorder, size or gate a candidate, and it stays wired to nothing — not Prophet, not Neural Web,
not any scoring path. Effective intervals remain mandatory so a later ticker reuse or rename
cannot rewrite history.

---

## What still requires the operator after this ruling

1. **The 20 ambiguous sponsor rows** — each needs a per-case decision, or an explicit ruling to
   leave them permanently unresolved.
2. **`BIOCATALYST_ENABLED` and `BIOCATALYST_CANARY_NCTS`** — the runtime and universe gates.
   Setting them is a production act on the host, not a repository change.
3. **`B1S2c`** — the arming decision and the fourteen-day soak, which no session can compress.
