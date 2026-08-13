# Reference Integrity Gate — V1.1

**Program:** Mastermind Product Design System & Experience Convergence (governance layer).
**V1.1 (additive):** §13 revision continuity closure + rule L10 — a `REVISE` may not evaporate
between cycles. V1's §6 rationale quarantine and §3 fresh-SHA/stale-receipt rules are unchanged.
**Companions:** `research/DESIGN_MIGRATION_FACTORY_V1.md` (the migration process this gate
precedes), `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` (visual/composition law),
`docs/DESIGN_DOCTRINE.md` (content law), `docs/product_experience/PAGE_EVIDENCE_HARNESS.md`
(evidence capture), `research/REFERENCE_INTEGRITY_EXECUTIVE_OS_INTEGRATION.md` (runtime
integration contract).
**Enforcement:** `scripts/check_reference_integrity.py` (registered in
`config/house_law_checks.yml`), artifact home `research/reference_integrity/<reference-id>/`,
founding regression fixture `research/reference_integrity/prophet-board-5514-original/`.
**Status:** Binding product-design law once merged. No production surface rides this PR.

---

## §0 The failure mode this gate exists to stop

The Design Migration Factory validates **implementation against a reference**. It is good at
that. It has no stage that validates whether a **new reference deserves to become law**. The
first Prophet Board reference mockup (PR #5514, original head
`668e5954876f078755537605942c644fcbbb8a1d`) proved the resulting failure mode is real:

> A redesign can be mechanically correct, design-system compliant, semantically consistent,
> responsive, bilingual, fully tested — and still make the actual product substantially worse.

The defect is **reference laundering**:

> A bad product decision becomes a reference. The reference becomes law. Builders faithfully
> reproduce it. Reviewers compare against it rather than against production. CI says
> compliant. The product regression is institutionalized.

RIG makes that path impossible by default. It inserts a stage **before** the factory:

```
Reference creation (THIS GATE):
  production truth → capability/user-job audit → proposed reference
    → independent product + taste review → design-authority verdict → approval receipt

Migration (existing factory, unchanged):
  approved reference → implementation → conformance verification
```

The two systems never blend. A migration builder compares against the approved reference
(factory §0.1 stands). A reference critic compares against **production**, never against the
proposal's own rationale.

---

## §1 Core law — the preservation presumption

> **Prior user value is presumptively preserved. Novelty carries the burden of proof.**

A redesign may absolutely remove bad product behavior. But every meaningful current
capability must receive an explicit disposition. **There is no implicit deletion.**

| Disposition | Meaning | Mandatory fields (checker-enforced) |
|---|---|---|
| `RETAIN` | capability survives, same tier | `target` (where it lives in the proposal) |
| `IMPROVE` | capability survives, made better | `target`, `rationale` |
| `RELOCATE` | capability moves | `destination` (exact), `reachability` (proof the user can still reach it appropriately) |
| `REMOVE` | capability is deliberately deleted | `rationale` (explicit product reason), `user_job_impact`, `superiority_case` (why removal beats retention/improvement), `approval_ref` (receipt) |
| `BLOCKED_DATA` | desired UX known; data contract/infrastructure insufficient | `dependency` (the insufficient contract, named), `escalation` (where the dependency was escalated — program/owner/issue), `interim` (what the UI does meanwhile, stated) |

**`BLOCKED_DATA` never silently converts into `REMOVE`.** If only 25% of rows have chart
enrichment, the legal output is `BLOCKED_DATA — chart enrichment incomplete`, escalated as a
data-dependency — never "therefore redesign the flagship card without a chart." A `REMOVE`
whose stated reason is data availability/coverage **is** a mis-filed `BLOCKED_DATA` and the
checker fails it by heuristic (§8 rule L6; the false-positive surface is documented there —
by law, a removal motivated by data insufficiency is definitionally `BLOCKED_DATA`, so a
match is not noise).

This law is the reference-creation analog of the factory packet's §2.6 module-disposition
table. They are different altitudes and never merge: the packet disposes **modules during
migration against an approved reference**; RIG disposes **capabilities during reference
creation against production truth**.

## §2 Scope classification — where RIG applies

**Full RIG** (complete artifact set, §3–§7):
first-of-archetype reference · flagship redesign · replacement of an existing customer-facing
page · major component redesign used across multiple pages · canonical reference replacement
· material information-hierarchy change · removal or relocation of an existing user
capability.

**Lightweight RIG** (§3 manifest + evidence + attestations + one independent review):
follower page using an already-approved archetype reference · local visual cleanup with **no
capability or hierarchy change**. The manifest attests `no_capability_change: true` and
`no_hierarchy_change: true` and cites the approved archetype reference it follows. Either
attestation false → Full RIG.

**Not RIG** (no artifact): pure bug fix · copy typo · invisible engine work · mechanical
token rebind with byte-equivalent/visual-equivalent output. These touch none of the
mechanical anchors (§8), so no ceremony attaches. Do not manufacture artifacts for them.

## §3 The artifact set

One directory per reference: `research/reference_integrity/<reference-id>/` (kebab-case,
stable). Committed screenshots live at `mockups/refs/reference_integrity/<reference-id>/`
(house rule: committed files, never prose — factory §8.10's two-namespace convention gains
this third namespace for integrity evidence). Machine-readable YAML; every schema carries a
`schema:` id.

| File | Schema | Content |
|---|---|---|
| `manifest.yml` | `mastermind.rig_manifest.v1` | reference id, surface (route/registry row/archetype), scope class, **status**, author identity, proposed-reference files with `frozen_sha`, file map |
| `baseline.yml` | `mastermind.rig_baseline.v1` | §4 production baseline + §5 capability ledger |
| `proposal.yml` | `mastermind.rig_proposal.v1` | proposed artifact pointer + `frozen_sha`, §5 dispositions, §6 user-task matrix, §7 authority delta + information-economics audit |
| `reviews/product_regression.yml` | `mastermind.rig_review.v1` | Reviewer A receipt (§6), two-pass |
| `reviews/visual_taste.yml` | `mastermind.rig_review.v1` | Reviewer B receipt (§6), two-pass |
| `verdict.yml` | `mastermind.rig_verdict.v1` | §7 design-authority verdict packet |
| `approval.yml` | `mastermind.rig_approval.v1` | §7 approval receipt — exists **only** when status is `approved` |
| `continuity.yml` | `mastermind.rig_continuity.v1` | §13 revision continuity closure — required **only** when the cycle follows a non-approving predecessor verdict |

**Status lifecycle** (`manifest.yml: status`): `draft → in_review → {approved | revise |
rejected}`, plus `superseded` (a later reference replaced this one; its manifest names the
successor). Until `approved`, the reference is **provisional** (§8 consequences). Blank
templates for every file: `research/reference_integrity/templates/`.

**Receipts bind to bytes.** Review receipts and the approval receipt carry the
`artifact_sha` they judged. If `proposal.yml`'s `frozen_sha` moves (the proposal was
revised), existing receipts are stale: status must drop back to `in_review` and the checker
fails an `approved` status whose receipts don't match the frozen artifact
(`stale-review-receipt`). Nobody approves v1 receipts and ships a v3 artifact.

## §4 Production Baseline Manifest — design memory

Before design begins on an existing surface, capture the product being replaced
(`baseline.yml`):

- route/surface; source template/component/builder paths; **source commit SHA**;
- production screenshots, committed: dark + light × EN (+ ZH where the surface is bilingual)
  × desktop + mobile — captured per the evidence harness's state-application rules
  (`docs/product_experience/PAGE_EVIDENCE_HARNESS.md` §2; the harness itself stays off CI).
  Missing axes are recorded as honest `gaps` with reasons, never silently absent;
- current primary user job (one sentence); current core interactions; current information
  hierarchy (ordered);
- **design lineage**: prior operator/design rulings (`DNR:` keys, packet sections, memory
  files), known intentionally-rejected variants where discoverable, and component comments
  that explain why current decisions exist.

This is design memory. An AI worker must not redesign a mature component while ignorant of
why it looks the way it does (§9 lineage law).

## §5 Capability Ledger — the mechanical backbone of "no implicit deletion"

`baseline.yml: capabilities` — a stable inventory, each entry `{id, user_job, evidence
(file:line), importance: core|supporting|peripheral}`. IDs are dotted-kebab
(`card.chart_hero`), unique, and stable across revisions.

`proposal.yml: dispositions` — **every baseline capability id receives exactly one
disposition** (§1 table). The checker fails if: a baseline id is missing from the proposal
ledger · a disposition names an unknown id (dangling) · ids duplicate · the enum is invalid
· any disposition's mandatory fields (§1) are absent · a `REMOVE` is data-motivated (§1).

## §6 What the reviews judge

**User-Task Regression Matrix** (`proposal.yml: user_tasks`). References are judged against
what the user can do, not merely whether components conform. For every primary/high-frequency
user task: production vs proposal, with a verdict `BETTER | EQUIVALENT | WORSE | UNKNOWN`.
The questions each row answers: can the user still answer the same question; faster or
slower; more reading; more clicks; did glance-tier information become drill-down; did visual
information become prose; did useful context disappear; did the UI become more authoritative
than the underlying system warrants; would a reasonable user prefer production for this task.
No fake precision — no stopwatch numbers unless real ones exist. **Any `WORSE` on a
`critical: true` task is review-blocking until explicitly adjudicated in the verdict packet.**

**Authority Delta** (`proposal.yml: authority_delta`). A redesign can accidentally make
stronger claims than the old interface. Each row: production claim vs proposal claim,
direction (`stronger|equal|weaker`), and whether the engine/evidence warrants the stronger
wording. Canonical examples: "relevant zone" → "do not enter above $101.10"; informational
management state → exact trading command; relative priority → implied probability; internal
horizon → implied required holding period. **New authority requires justification**; an
unwarranted `stronger` row is review-blocking.

**Information-Economics Audit** (`proposal.yml: information_economics`). Does the proposal:
replace charts with paragraphs; replace compact visual state with explanation; increase
words/card; increase glance time; introduce redundant explanations; repeat what is already
communicated visually; turn a dashboard into a report — or a report into unexplained widgets?
For dense trading/terminal surfaces **visual compression is a product capability**; "more
information" is not automatically better.

**Independent dual review.** A new reference cannot approve itself. Two independent
reviewers, neither of which authored the artifact (model routing: independent Opus
`reviewer`-class agents; the factory §1 red-team role):

- **Reviewer A — Product Regression Critic.** Mission: find anything the current product
  lets the user understand or do that became harder, slower, missing, misleading, or more
  authoritative. Focus: capability preservation · user tasks · information loss ·
  interaction regression · data-dependency-driven degradation · authority inflation · scope
  creep. Verdict: `PASS | PASS_WITH_CONDITIONS | BLOCK`; every finding gets an id
  (`PRC-nnn`) and severity (`blocker|major|minor`).
- **Reviewer B — Visual / Taste Critic.** Mission: judge the artifact **as a product, not a
  compliance exercise**. Focus: hierarchy · scanning · density · clarity · personality ·
  brand identity · restraint · contrast · light/dark quality · mobile quality · visual
  information compression · whether the result actually feels better than production.
  Same verdict/finding grammar (`VTC-nnn`).

Prompt templates: `research/reference_integrity/templates/CRITIC_A_PRODUCT_REGRESSION.md`,
`.../CRITIC_B_VISUAL_TASTE.md`.

**Rationale quarantine (binding).** For their **first pass** the critics receive ONLY: the
user/business job, the production-before artifact, the proposed-after artifact, and the
capability/task manifest. They do **not** receive the builder/designer's rationale — a
sophisticated worker can make almost any local decision sound reasonable ("chart coverage is
incomplete → remove chart"; "lifecycle is hue-neutral → remove almost all color"; each
locally rational, jointly a worse product). The critic first judges the **result**. After
first-pass findings are frozen (`first_pass.frozen_at`), the rationale, constraints, and
data limitations are revealed and a second-pass amendment is allowed
(`second_pass.amendments`: per-finding `upheld | downgraded | withdrawn` with notes). Both
passes are recorded; the receipt attests the ordering
(`quarantine.rationale_received_after_first_pass: true`).

## §7 Design-authority verdict packet + approval receipt

The design authority (factory §1: Fable main loop / CEO-designated authority — **never the
Chairman as a required gate**; the purpose is autonomous quality control) is never sent
"60/60 checks passing, looks good." The verdict packet (`verdict.yml`) forces the
comparison — all eight answers required, non-empty:

1. What materially improved?
2. What materially worsened?
3. What disappeared?
4. What user behavior became harder?
5. What stronger claims does the proposal now make?
6. Which decisions are caused by product intent vs implementation/data convenience?
7. Would production still be preferable for any important task?
8. What is the strongest argument **against** approval?

Verdict: `APPROVE_REFERENCE | APPROVE_WITH_CONDITIONS | REVISE | REJECT`, plus
`preserved_strengths` (what the proposal got right — recorded so a BLOCK is never a
strawman) and `conditions` where applicable.

**A critic BLOCK cannot disappear silently.** Every blocker-severity finding that survives
the critic's own second pass must appear in `verdict.yml: blocking_findings` with a
resolution: `upheld_revise` (drives `REVISE`/`REJECT`) · `resolved_by_change` (the proposal
was amended — receipts re-run against the new `frozen_sha`) · `overridden` (the authority
overrides: justification + authority identity, citing the finding id — permanent record,
copied into the approval receipt).

**Approval receipt** (`approval.yml`): exists only when status is `approved`; carries the
approving verdict, authority identity/role, both reviewer identities/roles, the author
identity (must differ from both reviewers), any overrides with finding ids, and the
`artifact_sha` approved. **A migration may treat a reference as canonical only if the
reference carries a valid approval receipt.** Otherwise the reference is provisional: no
registry row may mark a surface compliant based on it, and no migration may claim reference
conformance as final acceptance (factory §0.1/§0.8 amendment).

## §8 Mechanical enforcement — what CI actually checks

CI cannot judge taste and does not pretend to. **CI enforces that the product/taste judgment
happened, in the right order, independently, and left auditable receipts.**
`scripts/check_reference_integrity.py` (registered in `config/house_law_checks.yml`; wired
through the existing house-law check path, no new CI topology) validates:

- **L1 artifact completeness** — every `research/reference_integrity/<id>/` carries the §3
  file set for its scope class; schemas/enums valid; verdict-packet answers all present
  (including strongest-argument-against); baseline evidence screenshots exist on disk with
  honest gaps.
- **L2 ledger integrity** — §5 rules (coverage, no duplicates, no dangling, enum, mandatory
  per-disposition fields).
- **L3 blocked-data honesty** — `BLOCKED_DATA` carries dependency + escalation + interim;
  data-motivated `REMOVE` fails (§1 heuristic L6).
- **L4 regression explicitness** — task matrix present with valid verdicts; a `WORSE` on a
  critical task is unresolved unless adjudicated in the verdict packet.
- **L5 review independence + order** — both receipts present with distinct roles; reviewer
  identities differ from each other and from the author where identity is exposed;
  quarantine attestation + frozen first pass precede the second pass.
- **L6 approval integrity** — `approved` requires: approving verdict enum, approval receipt,
  zero unresolved blocking findings (critic-side and task-matrix-side), receipts'
  `artifact_sha` == proposal `frozen_sha` (`stale-review-receipt` otherwise).
- **L7 reference-namespace closure** — every non-specimen `mockups/design_system/*.html`
  is claimed by exactly one manifest's `reference_files`, except the closed pre-RIG list
  (`macro_reference.html`, `today_reference.html`, `utility_reference.html` — Wave-0
  references commissioned before this law; they remain **provisional** until their artifact
  sets are backfilled, which their first consuming packet owns).
- **L8 packet coupling** — every `research/migration_packets/MP-*.md` cites a
  `RIG-RECEIPT:` line naming an `approved` reference (there are no packets on main today,
  so this rule starts with zero debt and no grandfathering).
- **L9 registry coupling** — no page-registry row (overrides or compiled registry) carries
  `design_system.compliant: true` for a route whose RIG reference is missing or not
  `approved` (starts with zero debt: no compliant rows exist today).
- **L10 revision continuity closure** — §13. A cycle following a non-approving verdict
  accounts for every unresolved predecessor blocker and every authority condition by id,
  with exactly one successor disposition each. Armed at **every** status, `draft` included,
  so it fails before the critics are ever dispatched.

Failures print `::error` annotations at line start (house annotation law) and name a stable
finding code per rule; `tests/test_check_reference_integrity.py` mutation-tests every rule
(§10) so the gate cannot pass vacuously.

## §9 Design lineage law — protecting accumulated taste from AI amnesia

Before redesigning a flagship/mature component, the designer retrieves and cites in
`baseline.yml: design_lineage`: the current implementation; production screenshots;
historical operator rulings; comments explaining non-obvious design decisions; prior
failed/rejected experiments where available. **Prior decisions are presumptively preserved,
not blindly binding** — they may be overturned, but explicitly (a disposition, an authority
delta row, or a verdict-packet answer — never by omission).

## §10 Founding regression fixture — original Prophet #5514

`research/reference_integrity/prophet-board-5514-original/` freezes the original Prophet
Board mockup **by SHA** (`668e5954876f078755537605942c644fcbbb8a1d` — never a mutable branch
head; the active revision branch is untouched) as the gate's founding case, with the
production baseline it should have been judged against. The recorded system verdict — reached
by this gate's own machinery, independently of the Chairman having to point out the defects —
is:

> **BLOCK THE REFERENCE, PRESERVE THE GOOD ARCHITECTURE, REVISE THE CARD.**

The fixture demonstrates the system holding both thoughts at once: the critic receipts and
verdict record the good changes (canonical plan-book Setups; Setups/Candidates separation;
lifecycle repair; Resolved treatment; count reconciliation; episode handling; table/filter
architecture) **and** the blocking regressions (chart hero removed; live price removed; live
change removed; Priority score removed; compact Zone abstraction removed; multi-line
`what_to_do_now` prose in dense cards; `age_days/horizon_days` promoted to visible "day X of
45" UI; compact glance UX replaced by execution-prescriptive Entry/T1/Void geometry;
Prophet's semantic color identity substantially removed; incomplete chart enrichment
converted into feature deletion instead of a `BLOCKED_DATA` escalation).
`tests/test_check_reference_integrity.py` asserts the checker independently derives the
mechanically-derivable findings from the fixture's honest ledgers and that the receipt-level
findings block approval — and the anti-vacuity suite (§11 of the handoff; the mutation
tests) proves each rule can fail.

## §11 Executive OS integration

Runtime dispatch (artifact_ready → critics → verdict as governed states) integrates with the
Executive OS **when its canonical review-job mechanism exists**; RIG invents no parallel
orchestrator and no second state store (Executive-OS law: `duplicate_control_planes` is a
standing prohibition). The integration contract — required events, states, reviewer inputs/
outputs, blocking conditions, verdict schema, and the exact integration points found on
current mains — is `research/REFERENCE_INTEGRITY_EXECUTIVE_OS_INTEGRATION.md`. Until that
runtime exists, the gate operates exactly as this document specifies: sessions dispatch the
two critics per §6 (model routing law), the design authority issues the §7 verdict, and CI
enforces the receipts.

## §12 What this gate must never become

- Not a Chairman-review gate — autonomous quality control is the purpose.
- Not a taste oracle in CI — CI checks that judgment happened and left receipts.
- Not ceremony for trivial changes — §2's Not-RIG class is real and stays real.
- Not a second design doctrine — content law is DESIGN_DOCTRINE, visual law is the master
  doc; RIG only governs whether a proposed reference may become canonical.
- Not a replacement for the migration factory — approved references flow into it unchanged.
- Not deniable — builder rationale never substitutes for product comparison (quarantine,
  §6), and incomplete data never silently redefines the UX (§1).
- Not forgetful — a finding the gate has already upheld cannot vanish between revisions
  because the next builder's rationale did not mention it (§13).

---

## §13 Revision continuity closure — a REVISE may not evaporate

**Added in V1.1. Purely additive: §3's fresh-SHA/stale-receipt rules and §6's rationale
quarantine are untouched.** Fresh critics still judge the new SHA against production and are
still expected to find *new* defects. Continuity runs beside them and stops *old* defects from
disappearing.

### §13.0 The hole, and the real failure that found it

V1 gates a cycle. It does not gate the **seam between cycles**. A `REVISE` verdict can carry
unresolved blockers and authority conditions, and nothing mechanical obliged the next revision
to account for them — so the next builder's own rationale became the de-facto scope of the fix.

Prophet r3 (`6ad6b51b`) proved it, and proved it while doing good work: it closed all four r2
blockers and every item its own A–E rationale discussed. It also **silently omitted** four items
r2 had already upheld and written into the authority's own conditions — card→detail navigation,
the degraded-freshness disclosure, the anonymous-gate copy contract, and whole-book
reachability. Two of those were, by then, in their **third** consecutive revision. Nothing
failed. The omission surfaced only because an independent r3 critic happened to re-find it, and
the r3 verdict's own strongest-argument-against had to be spent on it:

> The cycle fixed everything its rationale discussed and moved nothing that appeared on no list.

That is the V1 laundering failure one level up — not a bad decision laundered into law, but a
review loop converging on the subset of the critique that was written down as code-shaped
conditions, while the capability-shaped ones stayed invisible. **A gate that only works when the
next builder chooses to re-read the last verdict is not a gate.**

### §13.1 The law

> A reference cycle that follows a prior `REVISE` or `REJECT` must identify its predecessor
> artifact set and verdict, and mechanically account for **every** unresolved predecessor
> blocker and **every** design-authority condition, **by id**, before the revised proposal may
> enter review.

Every predecessor open item receives exactly one successor disposition. **There is no missing
state and no implicit state** — the same shape as §1's no-implicit-deletion law, applied to
findings instead of capabilities:

| disposition | meaning | mandatory fields |
|---|---|---|
| `RESOLVED_BY_CHANGE` | fixed in the new SHA | `evidence`, `changed_files` (≥1, in the new SHA) |
| `CARRIED_BLOCK` | still unresolved, and said so out loud | `note`; **cannot coexist with `approved`** |
| `OVERRIDDEN` | the authority overrides it, permanently on record | `authority`, `rationale`, `finding` |
| `SUPERSEDED` | a named later finding/ruling genuinely replaces it | `superseded_by`, `linkage` |

`CARRIED_BLOCK` is the load-bearing one. It is **legal** — a revision is allowed to not fix
something — but it must be *stated*, it blocks approval, and it makes the debt visible to the
next cycle instead of resetting the count to zero.

### §13.2 The artifact

`research/reference_integrity/<id>/continuity.yml`, schema `mastermind.rig_continuity.v1`,
added to the §3 file set. Blank template:
`research/reference_integrity/templates/CONTINUITY_TEMPLATE.yml`.

The obligation runs against the **nearest** declared predecessor
(`manifest.lineage.predecessors`, ordered oldest → nearest). A chain is closed link by link:
the nearer predecessor's own continuity closed the older one, so re-closing it here would
double-count and dilute into rubber-stamping. Provenance still lists the whole chain.

Escaping by *declaring a conveniently old ancestor* is closed separately: `undeclared-predecessor`
compares against **every** non-approved artifact set governing the same `surface.route`, not just
the nearest.

When the predecessor set is not in the checkout (its PR is still open), the successor carries
`source: snapshot` with a `source_ref` proving where the closure set came from. A snapshot with
no source is a finding.

### §13.3 Conditions must be citable

V1 wrote `verdict.yml: conditions` as bare strings, which cannot be carried forward by id. V1.1
accepts both the string form and `{id, text}`, and requires the id form **only once a successor
actually exists that must cite it** — forward-binding, never retroactive. A verdict nobody has
succeeded yet is never punished for legacy-form conditions. Cite conditions by minted id, never
by list position: positions shift on every append, and the house has already been burned by
row-number citations that mis-resolved.

### §13.4 It must fail before the critics run

`GROUP_CONTINUITY` is armed at **every** status, `draft` and `in_review` included — unlike the
completeness group, which waits for a terminal status. A successor that has dropped a prior item
is therefore rejected while it still has no receipts at all, so the fleet never spends two
independent Opus critics on a proposal that was already inadmissible. Continuity is an
**admission** gate; §6 remains the judgment gate.

### §13.5 The mandate is derived, not written by hand

`check_reference_integrity.py --mandate <reference-id>` reads the predecessor's `verdict.yml`
and prints the machine-complete closure set — every open item, `disposition: <REQUIRED>`, with
the predecessor's own note as context. A design worker receives **the whole list, from the
record**, rather than a human-written summary of it. That is the actual fix for the r3 failure:
the r3 builder was working from a partial, self-authored scope, and a partial summary of a
verdict is indistinguishable from a complete one until a critic re-finds the gap.

### §13.6 Anti-vacuity

`tests/test_check_reference_integrity.py` and `--selftest` reconstruct the **actual r2→r3
failure**: a successor that declares its predecessor and omits the card-link, staleness,
anon-gate-copy and reachability items must fire `continuity-item-missing` at status
`in_review`, with no critic receipts present. Every L10 code must be provably able to fire, per
§8's standing anti-vacuity requirement.
