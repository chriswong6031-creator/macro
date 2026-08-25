# DEFENSE D6-B — FMS Implementation Handoff (paste-ready; NOT YET AUTHORIZED)

Status at freeze (2026-08-25): **D6-B implementation is NOT authorized.** This handoff
becomes executable only when Sol authorizes D6-B. Authority chain: D6-A accepted /
PROVEN_LIVE (macro #6385 comment 5404403124); D6-B0 architecture frozen in
`DEFENSE_D6B_FMS_SOURCE_AND_STAGE_ARCHITECTURE_FREEZE_2026-08-25.md` (the FREEZE — every
§ reference below points there). D5 remains BUILT_NOT_PROVEN (D5P deferred, nonblocking).
D6-C+ and D7+ unauthorized.

## §0 Acceptance gates (inline; the wave is NOT DONE unless…)

FREEZE §0 gates 1–10 verbatim, plus: fresh end-to-end happy path with zero manual
workarounds; the FMS mode proven in production on both canaries; anonymous boundary
proven (API + site twin 401/locked, no leak); all twelve §16 kill tests wired
merge-binding and failing under mutation; page ≤ 303,104 bytes with FMS shell delta
≤ 8,192 bytes; closing handoff with receipts. No child-agent self-merge of flagship UI;
the commissioning session owns commit → push → PR → CI → same-day squash-merge → live
verification.

## What is already decided (do NOT re-decide)

| Decision | Answer | FREEZE |
|---|---|---|
| Current source | State PM-Bureau surface `state.gov/arms-sales-congressional-notifications` (+ `/releases/bureau-of-political-military-affairs/YYYY/MM/slug/`) | §3.1 |
| Historical source | DSCA Major Arms Sales landing widget (Dec 2024→Feb 2026) + Major Arms Sales Library (pre-Dec-2024; CN-number-named PDFs incl. CNVn versions) | §3.2 |
| Source cutover | Cases notified before 2026-02-26 → DSCA archive; on/after → State. Enforced by surface-of-observation + transmittal dedup, never by parse-time date assumption | §3.3 |
| Transport | State: CLI HTTP (proven 200, byte-deterministic), D6-A fetch discipline. DSCA/media.defense.gov: CLI 403 → browser transport per standing law, or defer backfill (Sol, U2) | §3.4 |
| Stable identity | `fms:transmittal:<yy-nn>`; fallback `fms:urlpath:<sha256(path)[:24]>` with frozen collision/correction/supersession properties; country+system never an ID | §6 |
| Stage semantics | Six-stage namespace; v1 emits ONLY `congressional_notification`; advancement needs a named new official evidence class; time never advances | §4 |
| Amount semantics | `estimated_notification_value` only; never award/backlog/revenue/obligation/cash; null when unstated; verbatim `source_caveat` when present (State posts: absent) | §5 |
| Clocks | 4 clocks with per-clock evidence; State-era `official_notification_date` = null unless FR join (U3) | §7 |
| Correction semantics | same URL+bytes = receipted no-op; same identity+changed bytes = append version, preserve predecessor, new known_at; retraction visible when detectable; D6-A receipt field conventions | §8 |
| Canonical owner | GovRev-owned FMS source plane + `government_fms_case.v1`-class read model (D6-A pattern). NO `government_procurement_event.v2` rows, no new event store | §9, DEC:FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL |
| Exact consumer | Ninth bounded mode `data-mode="fms"` on `government_revenue.html`; existing publication lane + entitled API (`/api/government-revenue/fms-cases`, `/fms-case/{case_key}`); site twin `site/government-revenue-data/fms-cases.json` | §13 |
| Card content | The seven five-second answers, glance-tier, bilingual | §13.4 |
| Failure states | Frozen token table (reuse `current/partial/stale/source_unavailable/conflicted/corrected` + programLink states; new `rights_blocked/empty_valid/identity_unresolved/stage_not_observed`) | §14 |
| Canaries | A: DSCA 26-13 Saudi PAC-3 MSE ($9.0B, LMT). B: State 26-27 Sweden M142 HIMARS ($930M, LMT). Hostile: 26-13 stays `congressional_notification` | §15, reference composition JSON |
| Kill tests | T1–T12, merge-binding | §16 |

## Owned files (expected shape; builder may refine within the freeze)

- `collectors/fms_notifications.py` (+ `_live` split if mirroring dod_budget) — State
  listing/article acquisition, R2 immutable store + readback, deterministic parse,
  append-only case observations. NO OCR; no LLM numeric origination; unknown layout
  fails closed.
- `data/government_revenue/fms_*.jsonl|json` — receipts + case observations + read
  model (append-only; sparse-worktree law: opt into `data/` before touching).
- `engine/government_revenue/fms_cases.py` + `contracts/government_revenue/government_fms_case.v1.schema.json`.
- `scripts/build_government_revenue.py` — compose read model + site twin (respect
  RAW_HTML_BUDGET_BYTES enforcement at :1053).
- `app/government_revenue.py` — two routes inside the existing entitled router.
- `templates/government_revenue.html.j2` + `templates/government-revenue-dossiers.js`
  (binary-flagged: `grep -a`) + site twin — FMS mode shell (≤ 8,192 B delta).
- `tests/test_fms_notifications*.py` — T1–T12 + parser/correction/idempotence battery,
  wired into a `.github/ci/legacy-jobs.yml` pack (re-run pack validation; never trust a
  stale pack index).
- AgentOS: WS wave entry, closing handoff, any new DEC/DSC.

## Order law (mirror D6-A)

1. Design-spec-first for the mode shell (design lane: opus `designer`/main loop; the
   Sonnet `builder` implements the pinned spec).
2. Collector + parser against the two receipted canaries; survey-prove the parse on
   the full current State listing (all ~55 items) before production write.
3. Acquisition through a dispatch-only lane (no schedule until Sol sets cadence; the
   State surface posts event-driven, several times weekly at census).
4. Read model + API + mode; kill tests; opus adversarial review with repairs.
5. Carrier PR chain → merge → publication lane → production proof (D6-A §0 standard).

## Traps (from the B0 census — read before coding)

- Browser vs CLI fetches of the same State URL return different bytes; receipts are
  transport-scoped; canonical production transport is CLI (FREEZE §2 R5/R5c).
- State posts are edited IN PLACE (`article:modified_time` five months after posting on
  canary B's sibling evidence) — your append-only plane is the only version history.
- State posts omit: transmittal-certification PDF, certification-delivery sentence,
  the "highest estimated" caveat, and any machine `datePublished` (only
  `article:modified_time` was present). Do not assume DSCA-era fields exist.
- DSCA Library filenames carry correction versions (`…CN.PDF`/`CNV2`/`CNV3`) — same
  transmittal, multiple documents; versions, not new cases.
- The listing paginates `/page/N/` (10/page); item type label "FOREIGN MILITARY SALES:
  CONGRESSIONAL NOTIFICATION"; non-FMS PM releases share the /releases/ namespace —
  filter by the listing, not by URL shape alone.
- Transmittal label grammar differs by era: DSCA "Transmittal No. 26-13" vs State
  "Transmittal #26-27" vs FR "[Transmittal No. 26-74]" — parse all three forms.
- `government-revenue-live` shares one concurrency group — never cancel its runs
  (hook-enforced).
- Contractor name forms drift ("Lockheed-Martin Corporation, Dallas TX" vs "Lockheed
  Martin, Grand Prairie, Texas") — verbatim capture, `not_reviewed`, no ticker minting.

## Unresolveds routed to Sol at authorization time

U1 SAMM C5.7 receipt (only if review-period context is to be displayed); U2 historical
backfill depth; U3 FR join in v1 (State-era notification dates stay null without it);
U4 Feb-06→Feb-26 boundary-window completeness sweep; U5 ZH glance vocabulary (design
lane). FREEZE §17.
