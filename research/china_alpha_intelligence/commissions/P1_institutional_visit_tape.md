# P1 — Institutional Visit Tape + dossier (builder commission)

**Program:** `WS:CHINA-ALPHA-INTELLIGENCE` wave `p1` · **Route:** build (Sonnet `builder`)
**Gate:** spawns only AFTER the RIGHTS-0 verdict names a lawful visit source.
**Authority:** `research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md` §6 F1 + §13 P1; FABLE-B first-PR acceptance; `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE`.
**Spawn note:** paste this file as the commission; fill the SOURCE slot from RIGHTS-0 before spawning.

ROUTE: build

MISSION: Build the China institutional visit tape end-to-end at display tier:
collector (source per RIGHTS-0 verdict: __SOURCE__) → owner-native PIT store →
actor identity resolution (typed unresolved allowed) → dossier display →
failure states → prospective outcome accrual hooks. NO score of any kind.

WHY: Institutional Discovery is the program's first vertical (masterplan §14
milestone 1): observing the professional discovery funnel
(SEARCH → THESIS → REVISION → ALLOCATION) before consensus is the strongest
short-term China information edge. The repo has NO visit data today (verified
2026-08-19: greps for 调研/diaoyan/inst_visit across engine/scripts/config
returned zero collector hits).

SCOPE:
- **Collector**: new `collectors/china_visits.py`, registered in
  `scripts/collect.py`'s asia group (pattern at scripts/collect.py:230-250),
  running ONLY in `.github/workflows/asia-close.yml` (daily.yml excludes the
  asia group and resets stray china writes — daily.yml:372, 632-634). Respect
  the render budget: metadata-first two-stage ingestion (masterplan §10) — the
  visit-event metadata row (who/when/company/type/published_at) establishes
  the information clock; body/detail hydration is a separate later stage, not
  this PR.
- **Store**: new owner-native plane `data/china_visits/` (visits remain in the
  visit source plane — masterplan §4.1; this is the lawful new-store case: no
  existing owner). Append-only, dated, dedup on a stable natural key; every
  row carries `source_published_at` AND `system_recorded_at` (PIT truth = what
  was knowable when). No backfill claims presented as prospective history.
- **Actor identity**: resolve visiting-institution names to the manager-complex
  ontology draft (`research/alpha_intelligence/censuses/B0/B0_MANAGER_COMPLEX_DRAFT.md`)
  where deterministic; otherwise typed `unresolved` — NEVER fuzzy-guess
  (masterplan §5 exact-identity law; vendor IDs are aliases, not authority).
  Company-side identity: canonical listing identity only; unresolved stays
  typed unresolved.
- **Dossier**: extend `engine/china_intel_hub.py` `_dossier()` (L608-610,
  assembled L1299-1315) with a visit-tape block: recent visits, visitor
  classes, first-visit flags — descriptive only, plain-word glance tier per
  the design doctrine. Read DESIGN_DOCTRINE.md + invoke the frontend-design
  skill before touching the user-facing surface.
- **Failure states**: the ten-state taxonomy (masterplan §9.3): measured
  no-event / no coverage / not yet available / stale / source failure /
  rights suppressed / identity unresolved / not applicable / low extraction
  confidence / contradicted — visit block must render honest nulls (never
  zero-as-missing).
- **Prospective accrual**: stamp rows so a FUTURE P1B state
  (abnormal/new/independent visitor metrics) can accrue outcomes
  prospectively — no metrics, no score in this PR.

OUT OF SCOPE: NO "visit = bullish" anything — no score, no rank input, no
Prophet contact, no board/serving change (serving firewall: masterplan §11.4).
No universal Evidence Mesh dependency (boring baseline: owner-native store +
direct readers — P1 explicitly does not block on mesh runtime). No fund/
analyst/Q&A work (later verticals). No LLM extraction in this PR (metadata
stage only). No second identity plane.

FROZEN SPEC: masterplan §6 F1 + §13 P1 + this file. Store schema field names
follow the plane conventions in `collectors/china_irm.py` (nearest sibling:
keyless nightly, cursor shard, parquet store).

OWNED FILES: `collectors/china_visits.py`, `scripts/collect.py` (registration
lines only), `engine/china_intel_hub.py` (dossier block only),
`scripts/build_china_intel_hub.py` if the block needs plumbing, new tests.

TESTS: collector unit tests on fixture payloads (dedup, PIT stamps, refusal
paths); dossier render test with visit block + each failure state; identity
resolution test incl. typed-unresolved; no full-suite in a sparse tree.

NOT DONE UNLESS (FABLE-B acceptance, verbatim): a REAL company's CURRENT visit
event flows source → PIT truth → actor identity → dossier → failure states →
prospective outcome accrual, demonstrated with receipts in the PR body
(fixture-driven locally; live proof at the first asia-close run post-merge,
named as deferred-prospective with the verification command). Zero score
fields anywhere in the diff. Ship loop owned to merged + WS wave `p1` flipped
done in the same PR. Continuation handoff (FABLE-B): state coverage on Prophet
candidates, PIT/history class, independent user value, research eligibility,
unresolved rights/identity, next vertical.

RETURN: STATUS / RESULT / EVIDENCE (PR number, fixture receipts, dossier
screenshot or rendered-block excerpt) / GAPS / DEVIATIONS.
