---
key: CHINA-COVERAGE-EXCEPTION-LEDGER
question: >
  P1-R2 (DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION) made a malformed
  announcementId a typed, counted exclusion, but left two questions unanswered
  because they were outside its commission: HOW LONG is an exclusion true for,
  and OVER WHOM does it suppress absence authority? Its inherited defaults —
  per-run and plane-global — fail in opposite directions depending only on where
  the malformed row sits (DSC:CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-
  FORGETFULNESS): a row already in the accrued store blacks the whole China
  visit plane out permanently, while a row stopped at the store boundary is
  forgotten once it ages out of CNInfo's 3-day re-pull window and the affected
  company then renders a false clean "no visits observed". What durable shape
  makes a malformed institutional-visit observation remain truthfully remembered
  until deterministically reconciled, while limiting negative-authority
  suppression to the companies whose evidence is actually incomplete?
answer: >
  Add ONE owner-native coverage-exception ledger to the existing P1 visit plane —
  data/china_visits/coverage_exceptions.parquet — keyed on a VERSIONED
  observation fingerprint over exact immutable source metadata EXCLUDING
  announcementId and collection-time noise (_FINGERPRINT_VERSION "obsfp1" over
  exchange, sec_code, org_id, title, publish_ts, announcement_type_raw,
  adjunct_url, adjunct_type, category). The ledger is a coverage-exception
  evidence store, never an identity store: the fingerprint is firewalled by an
  in-code guard (write_visits() REFUSES the whole append if any row's
  announcement_id is a fingerprint) and may never populate announcement_id,
  become a DataOS/GMI alias or canonical filing identity, or be consumed by
  scoring/ranking/Prophet. Exceptions are harvested from BOTH boundaries with no
  new network call — from china_filings' excluded rows (LAST_KEY_INTEGRITY gains
  `excluded_rows`) and from china_visits' own typed candidate exclusions — and
  are filtered to P1 relevance (category == institutional_visit, or a blank title
  where the category is UNKNOWABLE rather than merely "other"), so a malformed
  NON-visit filing never poisons P1. Repeated re-pulls upsert ONE durable row
  (last_seen_utc / observed_count), never N. Recovery is deterministic ONLY:
  exactly one well-keyed candidate matching the frozen fingerprint resolves the
  exception and records the REAL announcementId; zero or two-or-more leave it
  open; never fuzzy-match; a resolved row is kept forever, never rewritten away.
  Suppression is SCOPED: an open exception with a known sec_code blocks clean
  negative authority for THAT COMPANY only, an exception whose company identity
  is unresolvable degrades the whole visit plane (scope cannot honestly be
  bounded), and unaffected companies keep normal measured_no_event semantics.
  Positive evidence always remains visible; where a company has both visit rows
  and an open exception the dossier renders the rows AND declines to assert
  completeness. The product state is a structured `coverage_exception` projection
  behind the EXISTING house taxonomy (state "not_yet_available"), not a new
  top-level enum.
rationale: >
  The load-bearing insight is that an exclusion which is only COUNTED is not
  REMEMBERED. Its truth has to outlive both the process that observed it and the
  upstream window that re-supplied it, or the instrument silently changes meaning
  as time passes — which is how a repair for a silent drop produced two new
  silent lies. A durable ledger is the minimum structure that can carry the
  sentence "we observed source evidence relevant to this company but could not
  canonically admit it" across nights, and a deterministic fingerprint is the
  minimum structure that can retire that sentence honestly when CNInfo later
  supplies the real key. Scoping is what makes the memory usable rather than
  merely safe: a plane-global refusal is the conservative reading, but it is the
  SAME failure as the latch under a new name — it converts one company's missing
  evidence into a claim about all ~5,400 A-shares, which is both less true and
  strictly less useful than saying nothing about one name. Per-company
  suppression is therefore the honest maximum, and plane-global suppression is
  reserved for exactly the case where scope genuinely cannot be bounded (no
  usable sec_code, or an unreadable ledger). This is what permits the deliberate
  reversal of P1-R2's requirement that malformed-key conditions must never
  advance clean last_success_utc: with the ledger carrying the suppression per
  company, a globally-clean run MAY advance last_success_utc and MAY stamp
  coverage_start — and it MUST, because freezing them is precisely the latch that
  prevents the plane from ever starting. The fingerprint is versioned in its own
  value ("obsfp1:<sha256>") so a future change to the recovery tuple degrades to
  a visible non-match rather than a silent re-key, and it excludes sec_name
  because company names change (ST prefixes, renames) and a mutable field in a
  dedup key breaks the very deduplication requirement 6 exists to guarantee.
  Reusing "not_yet_available" rather than minting a state is required twice over:
  Sol's commission forbids minting an arbitrary top-level enum to avoid designing
  the product state, and engine/china_intel_hub.py's _visit_block() routes on
  literal state strings, so an unrecognized state falls through to
  measured_no_event — the exact silent conversion this whole line of work exists
  to prevent (the same hazard recorded in DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION).
alternatives:
  - option: Keep P1-R2's per-run, plane-global exclusion-health semantics and
      simply document the limitation.
    why_not: >
      Measured, not theorized: the two failure modes are mutually exclusive per
      row and jointly exhaustive — a malformed visit observation either sits in
      the accrued store (latch) or is stopped at the boundary (forgetfulness),
      and there is no third place for it to be. So the semantics could not be
      right for ANY malformed visit row. Reproduced over five simulated nights
      each against the merged bytes of c11b16500c15 (see evidence).
  - option: Suppress negative authority plane-globally whenever any exception is
      open — the conservative reading.
    why_not: >
      Reproduces the latch under a new name. One unresolved row for one company
      would refuse measured_no_event for every A-share indefinitely, which is
      less true than the scoped answer (we DO know the other names' evidence is
      complete) and strictly less useful. Kept only for the genuinely unbounded
      case: an exception with no usable company identifier, or an unreadable
      ledger.
  - option: Mint a fallback/composite canonical announcementId for the malformed
      row so it can be tracked in filings.parquet directly.
    why_not: >
      Forbidden by both commissions as a new identity system, and re-rejected
      here for the same reason recorded in DEC:CHINA-KEY-INTEGRITY-TYPED-
      EXCLUSION: a synthetic key is a second unauditable identity plane under the
      first, and a later genuine CNInfo id could collide with or duplicate its
      coverage with no way to reconcile. The fingerprint in this record is NOT
      that: it keys a quarantine/coverage-exception evidence row only, is
      firewalled in code from ever reaching announcement_id, and is deliberately
      derived from fields that EXCLUDE the natural key.
  - option: Append the malformed row keyless to filings.parquet so it is at least
      visible.
    why_not: >
      Unchanged from P1-R2: a keyless row cannot dedup against itself across the
      3-day re-pull, so one upstream defect grows the canonical store by a row
      per night forever. The ledger solves exactly this with an explicit upsert
      on the fingerprint (one durable row, observed_count incrementing).
  - option: Mint a new top-level health/dossier state (e.g. "coverage_incomplete").
    why_not: >
      Sol's commission explicitly forbids minting an arbitrary new top-level enum
      merely to avoid designing the product state, and the hub routes on literal
      state strings — an unrecognized state falls through to measured_no_event,
      the exact silent conversion being repaired. A structured coverage_exception
      projection behind the existing "not_yet_available" state carries strictly
      more information and cannot fall through.
  - option: Use the schema's supersedes/superseded_by fields to retire
      DEC:CHINA-KEY-INTEGRITY-TYPED-EXCLUSION.
    why_not: >
      Those fields mark a whole decision dead, and only its TEMPORAL/SCOPE
      semantics changed. Its shared-predicate law, no-synthetic-ID law,
      strict-unreadable-store ABORT and explicit mechanical accounting are all
      retained verbatim and still binding — Sol's commission says to amend only
      the affected semantics. Recorded instead as an "AMENDED BY P1-R3" section
      appended to that record's body, the same body-only convention already used
      for the repaired DSC.
  - option: Put the ledger in a new module and/or a new top-level data family.
    why_not: >
      Commission requires ONE owner-native ledger under the existing
      data/china_visits/ plane and forbids a generalized quarantine framework or
      generic event store. Keeping it inside collectors/china_visits.py also
      avoids a new import edge in a module the market-critical Asia lane imports.
  - option: Reconcile by fuzzy/heuristic matching (fuzzy title, nearby timestamp).
    why_not: >
      Forbidden by the commission and independently wrong: a wrong match writes a
      REAL announcementId onto the wrong observation and closes the coverage
      exception with a lie, which is worse than leaving it open forever. Exact
      fingerprint equality with an explicit ambiguity branch (2+ matches stay
      open) is the only shape that cannot mis-resolve.
evidence:
  - "scratchpad/probe_p1r2_defects.py (session 24e6d425, 2026-08-22) run against
    `git show c11b16500c15:collectors/china_{filings,visits}.py` exec'd into
    sys.modules — LATCH: nights 1-5 all upstream_degraded, coverage_start=None,
    last_success_utc=None. FORGETFULNESS: nights 2-5 status ok, coverage_start
    stamped, candidate_accounting {eligible:1, represented_downstream:1,
    typed_exclusions:0}, zero rows and zero on-disk trace for the excluded company"
  - "collectors/china_visits.py refresh() — typed_exclusions computed over the
    accrued candidate set (filings[filings['category']==_CATEGORY]), the latch"
  - "collectors/china_filings.py _NIGHTLY_LOOKBACK_DAYS == 3 — the re-pull window
    the forgotten observation ages out of"
  - "engine/china_intel_hub.py _visit_block() — literal state-string routing.
    Measured first-hand via scratchpad/probe_p1r2_hub_half.py against the same
    merged commit: fed the exact end state the forgetfulness probe leaves
    behind, the affected company returns state 'measured_no_event' with detail
    'no institutional-visit filing observed for this name since coverage
    start' — a clean measured absence asserted about a company whose visit
    filing was in fact observed"
  - "DSC:CHINA-VISITS-KEY-EXCLUSION-LATCH-AND-AGING-FORGETFULNESS — the
    repair-induced lifecycle defect this decision answers"
  - "Measured 2026-08-22 on origin/main:data/china_filings/filings.parquet:
    54,078 rows, 0 malformed keys ever — both branches are unreachable in
    production today, so this ships proven by hostile fixtures and mutation
    tests, not by a naturally occurring malformed row"
affects: ["WS:CHINA-ALPHA-INTELLIGENCE", "collectors/china_visits.py",
          "collectors/china_filings.py", "engine/china_intel_hub.py",
          "templates/china_intel.html.j2", "data/china_visits/"]
confidence: high
reversibility: costly
decided_by: session
decided_at: 2026-08-22
---

## Grounds

Commissioned by Sol (AI CEO) 2026-08-22 as P1-R3 "durable scoped key-exclusion
recovery", after accepting #6229's implementation with no rollback. The
commission explicitly lifts P1-R2's prohibition on editing
`engine/china_intel_hub.py`: "The P1-R2 prohibition against editing
engine/china_intel_hub.py does not survive when that prohibition itself prevents
correct per-company semantics."

Reversibility is `costly` rather than `easy` because the ledger is a persisted
store with an accruing history: the code is revertible in one commit, but a
populated `coverage_exceptions.parquet` and the reconciliations recorded in it
are not reconstructible from anything else once discarded. The fingerprint law is
versioned specifically so the recovery tuple can change later without a
destructive migration.

## What would reopen this

A malformed key that is NOT a coverage question — e.g. CNInfo starting to emit
malformed ids at a rate where per-observation exceptions become a data-quality
firehose rather than a rare exception — would need a different structure than a
row-per-observation ledger. So would any requirement to reconcile an exception
against a source OTHER than a later well-keyed CNInfo filing (the frozen recovery
tuple assumes the same publisher re-publishes the same immutable metadata). And
if a future plane needs the excluded observation to carry PRODUCT weight rather
than only suppress absence authority, that is a genuinely new decision: this
record deliberately keeps the exception invisible to scoring, ranking, and
Prophet.
