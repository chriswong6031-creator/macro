# BioCatalyst — operator ruling, 2026-08-07

| Field | Value |
|---|---|
| Authorizing operator | Repository operator (chriswong6031-creator), in session, 2026-08-07 |
| Instruction given | "yes for both, do for me" — in response to `research/BIOCATALYST_OPERATOR_DECISIONS_2026-08-07.md` |
| Rulings | (1) enable ClinicalTrials.gov Record History ingest; (2) admit the sponsor→ticker candidate rows |
| Recorded by | Claude Fable 5, overnight autonomous session |
| Amended | 2026-08-08 — Ruling 3 added below, on the 20 rows Ruling 2 left queued |

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

*Amended 2026-08-08 by Ruling 3 below: four of those 20 — the `subsidiary_of_listed_issuer` group —
were then decided per-case and admitted to their listed parents. Sixteen remain queued. This
paragraph records what Ruling 2 itself ruled and is left as it stood.*

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

## Ruling 3 — the four subsidiary rows are ADMITTED to their listed parents

| Field | Value |
|---|---|
| Authorizing operator | Repository operator (chriswong6031-creator), in session, 2026-08-08 |
| Instruction given | "For the 20 queued, honestly i don't know lol. so lets just do ur recommendation B" |
| Scope | The four `subsidiary_of_listed_issuer` rows only. The other 16 stay queued. |

Ruling 2 left 20 rows queued because a blanket "yes" cannot answer a per-case question. The
operator was then shown those 20 **grouped by their ambiguity reason** and asked to decide group
by group. The answer was recommendation B: admit the narrowest group where the answer is a
modelling choice rather than a fact nobody has, and leave the rest queued. That group is the four
operating subsidiaries of issuers that are already inside the declared universe.

| `sponsor_name` (exact) | Parent ticker | Why this one is decidable |
|---|---|---|
| `Cepheid` | `DHR` | Wholly owned operating unit of a universe issuer. |
| `Genentech, Inc.` | `RHHBY` | Wholly owned operating unit; the parent's only universe line is an ADR. |
| `Janssen Research & Development, LLC` | `JNJ` | The issuer's own pharmaceutical R&D entity. |
| `Merck Sharp & Dohme LLC` | `MRK` | The US-listed issuer's own operating entity. |

Each of the four already carried exactly that parent in `candidate_tickers`, so this ruling picks
nothing new — it admits the single candidate the queue had already recorded.

### The modelling choice being made, and its consequence

**A subsidiary's trials are attributed to the PARENT issuer's ticker.** That is a choice, not a
discovered fact, and it is the substance of this ruling. Its consequence is direct and should
surprise nobody later: **a Genentech trial will surface under Roche (`RHHBY`)**, a Janssen trial
under `JNJ`, an MSD trial under `MRK`, and a Cepheid trial under `DHR`. The sponsor string on the
ClinicalTrials.gov record still says the subsidiary; the ticker this map returns is the parent.

Because those two are not the same thing, an admitted row now says which it is. Every admitted row
carries `issuer_relationship`:

- `direct_issuer` — the sponsor string **is** the listed issuer (all 29 Ruling 2 rows);
- `parent_of_subsidiary_sponsor` — the sponsor string is a **subsidiary** and the ticker is its
  **parent** (these four).

A downstream reader can therefore always tell "this trial's sponsor IS the issuer" from "this
trial's sponsor is a subsidiary OF the issuer" without re-deriving it from a name. Admission is
still not source verification: the four keep their `model_suggested_candidate` provenance and
their "Unverified against a live ClinicalTrials.gov record" note, because the operator authorized
the attribution, not a per-row check against a live record.

### Authority boundary, unchanged

This changes nothing about what the map may be used for. It remains **post-selection context
only**: BioCatalyst may explain a name AFTER Prophet selects it. The map may not originate, rank,
reorder, size or gate a candidate; it is wired to no scoring path, no Prophet path and no Neural
Web path; and admitting four more rows does not move it one step closer to any of those. The
attestation fence is unchanged too — all 33 admitted rows carry a named human authorizer and this
document bound by content digest, so a model still cannot promote its own suggestion.

### The remaining 16 stay queued, with their reasons

Recommendation B was deliberately narrow. These stay `ambiguous_queued`, untouched, and remain a
standing operator to-do:

| Ambiguity reason | Rows | Why a decision was not taken |
|---|---|---|
| `issuer_outside_declared_universe` | 8 | Admitting one needs the universe widened first, which is a separate reviewed act. |
| `renamed_entity` | 3 | A rename needs the interval boundary dated, not just a ticker picked. |
| `unlisted_or_private_entity` | 1 | There is no ticker to admit. |
| `foreign_listing_or_adr_ambiguity` | 1 | Which listing line the trials belong to is the open question. |
| `contract_research_organization_sponsor` | 1 | A CRO sponsors on behalf of an unnamed client; the issuer is not knowable from the string. |
| `multiple_matching_issuers` | 1 | Several issuers genuinely match; picking one would be a guess. |
| `joint_venture` | 1 | Two parents, and no basis in the record for splitting between them. |

---

## What still requires the operator after this ruling

1. **The 16 still-ambiguous sponsor rows** — each needs a per-case decision, or an explicit ruling
   to leave them permanently unresolved. (Ruling 3 resolved four of the original 20.)
2. **`BIOCATALYST_ENABLED` and `BIOCATALYST_CANARY_NCTS`** — the runtime and universe gates.
   Setting them is a production act on the host, not a repository change.
3. **`B1S2c`** — the arming decision and the fourteen-day soak, which no session can compress.
