# Cell F — D5 adversarial review amendments

**Status:** NORMATIVE AMENDMENT to `CELL_F_D5_EVIDENCE_TRANSLATION_AND_TRAJECTORY_CONTRACT_2026-08-22.md`  
**Linear:** MAS-122  
**PR:** #6275  
**Historical construction parent:** `3049b6f9785e7a08f03d746e0ca909cc425fdbde` — **not** the final/current reconciliation base

This file closes precision defects found by Sol's adversarial read of the frozen Cell F contract. It does **not** reopen the core architecture. Where this amendment conflicts with the base contract, this amendment wins.

---

## A1 — Correct archaeology and carrier provenance

The earlier wording calling `3049b6f9785e7a08f03d746e0ca909cc425fdbde` the “final reconciled main base” was wrong and is superseded.

The exact historical receipt is:

- deep semantic/code/owner census: `f6a16bc24b62b3655d2662dba2018d6e83ee2e18`;
- first post-census main: `9f373fd9553603192f495260b2100c16c177023b`, differing from the deeper census pin only by `data/marketing/outbox/activity.jsonl`;
- **original Cell F construction parent:** `3049b6f9785e7a08f03d746e0ca909cc425fdbde`; the first Cell F commit `e97947669b2e4eb8577a39aeb8515a4fb7423fe2` is directly parented to it;
- the historical delta `9f373f… → 3049b6…` is three commits touching only `data/marketing/press_wire/cursors.json` and `data/marketing/press_wire/seen_ring.jsonl`;
- prior closeout later reconciled the carrier against then-current main `d87abb9def7766aaba23819f0cc652dcd11a3aff`, producing subject head `4380c7de87a403113fd4ddf8de374702c6407cd6` and green exact-head CI/fences;
- this 2026-08-23 continuation re-pins and reconciles again to current main before its new exact-head validation. The final current-main SHA for this continuation belongs in the return/PR receipt; it must not be retroactively mislabeled as the old `3049b6…` construction parent.

Thus `3049b6…` remains useful **historical provenance**, but it is not the final merge-base/current-main receipt for #6275.

---

## A2 — `explanation_facts[]` is part of the family envelope

The family-envelope summary in base §6 omitted a field that base §11 correctly defined. The omission is editorial, but the closed shape must be unambiguous.

The normative family envelope is:

```text
family_projection_id
evidence_family_id
family_contract_version
owner_ref
subject_binding
semantic_head_ids[]
method_version
point_in_time
applicability
coverage
freshness
rights
identity_state
quality
source_refs[]
evidence_roots[]
observations[]
explanation_facts[]
trajectory
correction
calibration
fusion_bindings[]
authority
```

`explanation_facts[]` remains exactly as base §11 defines it: deterministic, source-bound render facts that point back to observation/source/root IDs. It is never a free-running LLM summary and never gains score/rank/authority semantics.

---

## A3 — Do not represent an unbuilt specialist family as a malformed coverage state

Base §16.1 used this illustrative shorthand for Theme:

```text
coverage/state: ACCRUING / NOT_COMPUTED
```

That shorthand is **rejected** because `ACCRUING` and `NOT_COMPUTED` are typed absence/readiness reasons, not legal `coverage.state` values. The legal coverage enum remains only:

```text
COVERED | PARTIAL | NOT_COVERED | UNKNOWN
```

More importantly, the correct current Theme behavior is stronger:

> Until the GMI owner actually publishes the canonical ThemeState contract and a lawful D5 adapter exists, **no `theme.theme_state` family envelope is emitted at all**.

D5 does not manufacture a source-family placeholder merely to make a UI section complete. Product/adapter readiness may separately disclose “Theme adapter not built / accruing,” but that is control/readiness metadata, not episode evidence and does not belong inside `evidence_families[]`.

Once a Theme adapter exists, source outages or per-episode missing observations use the normal D5 axes and typed observation absence reasons. They still never fall back to legacy Context Vector `theme_score`, `theme_heat_rank`, or `foresight_stage` as current canonical Theme truth.

This also establishes the general rule:

- **unimplemented adapter or unbuilt specialist contract** → family absent from the D5 evidence envelope;
- **implemented adapter, family applicable but source/object absent or degraded** → family may be present with lawful applicability/coverage/freshness/rights/identity states and `ABSENT` observations carrying typed reasons;
- **implemented adapter, family genuinely not applicable** → family may be present with `applicability.state=NOT_APPLICABLE` when that negative applicability itself is a source/contract-grounded fact.

Absence of a family from the envelope never means zero, neutral, not-applicable, or no-signal.

---

## A4 — Rights are two questions: may Mastermind use it, and may a consumer render it?

Base §8.1 `rights.state` and base §9.1 per-source `render_policy` remain compatible, but their relationship is now explicit:

- `rights.state ∈ {ALLOWED, DERIVED_ONLY, BLOCKED, UNKNOWN}` answers whether the family/source may be used by the D5 projection under the owner's rights profile;
- each `source_ref.render_policy ∈ {INTERNAL_ONLY, DERIVED_ONLY, DISPLAY_SAFE}` answers what a downstream product may render from that referenced object;
- `rights.state=ALLOWED` **does not** imply raw/source text is display-safe;
- `render_policy=DERIVED_ONLY` permits only owner-approved derived/structured facts, never source text or an opaque body copy;
- `render_policy=INTERNAL_ONLY` means a product consumer may use only already-allowed D5-derived facts and must not expose the referenced object/body;
- `rights.state=BLOCKED` means the prohibited observation is `ABSENT` with `RIGHTS_BLOCKED`; D5 does not carry the blocked value and rely on the UI to hide it.

This preserves one enforcement boundary: rights are enforced before serialization, then display policy further narrows what a product can render.

---

## A5 — Semantic heads are controlled adapter vocabulary, not free text

Base §3.2 calls semantic heads controlled grouping IDs. To prevent free-text drift, the normative rule is:

- every emitted `semantic_head_id` must be declared by the exact `adapter_set_version` / D5 contract version in force;
- unknown heads fail validation rather than being accepted as arbitrary strings;
- adding or renaming a head is a D5 contract/adapter-set version change;
- a head still carries zero score, weight, vote, independence, Fusion registration, or authority.

This keeps semantic grouping stable enough for product/research consumers without turning it into a second ontology or rank registry.

---

## A6 — Correction enrichment creates a new projection receipt; it never mutates the old one

Base §5 says `projection_id` is content-addressed and base §13 permits a later rebuild to add correction references. The combined consequence is now explicit:

- the original D5 projection remains immutable and addressable by its original `projection_id`;
- adding `later_correction_ref_ids[]` produces a **new** content-addressed D5 projection receipt linked to the same canonical candidate episode/decision cut;
- the new projection may expose “what is known now” audit links, while `decision_version_ref_ids[]` and decision-time observations remain byte/semantically unchanged;
- no mutable “latest D5 truth” registry is created by Cell F. A consumer that wants the most recently assembled correction-aware projection resolves that through its existing artifact/publication plane, not a D5 lifecycle store.

This closes the last route by which correction enrichment could accidentally become a hidden rewrite mechanism.

---

## A7 — Candidate-level compositions and deterministic E1 baseline

The family-level examples in the base contract are necessary but insufficient as an implementation acceptance oracle. The normative research companion is now:

`research/prophet_v4/flagship_cells/CELL_F_D5_CANDIDATE_REFERENCE_COMPOSITIONS_AND_E1_BASELINE_2026-08-23.md`

It contains eight candidate-level research compositions covering genuine independent confluence, common-ancestor fake confluence, favorable evidence plus fragility/crowding, missing/not-covered/unbuilt families, corrections/reversals, rights blocking, measured neutral, and strong intelligence with deterministic entry unavailable.

Every one is explicitly labeled:

> **REFERENCE COMPOSITION ONLY — not a canonical `prophet.candidate_episode/v1` instance until B1 exists.**

The same document freezes the deterministic E1 recommendation: D5 itself ranks nothing; only decision-admissible owner-native observations explicitly bound to accepted Conditional Fusion members/versions can become E1 inputs. Missing/not-covered/unbuilt/rights-blocked/stale evidence abstains rather than becoming a zero vote; measured neutral is eligible only when positively measured under the member contract; rank remains inside the B4 availability lane; learned E3–E5 challengers remain shadow-only until E6 separately promotes them.

---

## Review disposition

After A1–A7, no semantic blocker remains inside Cell F itself. The runtime blocker remains the upstream canonical V4 candidate episode B1 documented in `DSC-PROPHET-D5-BLOCKED-ON-CANONICAL-CANDIDATE-EPISODE-B1`.

The first implementation vertical remains:

> owner-issued canonical V4 candidate episode → mature Earnings `event_workspace.v1` → thin allowlisted `earnings.event` adapter → `prophet.intelligence_vector/v1` → one existing read-only Prophet Lab consumer → tests/proof → stop.

No Context Vector widening, universal history migration, specialist fan-out, Fusion edits, rank authority, or deterministic `ENTRY_OPEN` mutation is authorized by this amendment.
