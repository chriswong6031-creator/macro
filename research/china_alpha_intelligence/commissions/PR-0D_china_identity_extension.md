# PR-0D — China exact identity extension (builder commission)

**Program:** `WS:CHINA-ALPHA-INTELLIGENCE` wave `pr0d` · **Route:** build (Sonnet `builder`)
**Authority:** `research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md` §5 + §13 PR-0D + §0-ter.6 boundary; `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE`; `DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL` (boundary it must NOT cross).
**Coordination gate:** before touching any identity surface, read the current `WS:STOCK-IDENTITY` record + its latest handoff and name in your PR body which of its waves you interlock with. If that workstream has an in-flight PR on the same files, coordinate in its lane — never race it.
**Spawn note:** paste this file as the commission; SECTION labels below are the routed-spawn contract.

ROUTE: build

MISSION: Extend the canonical Data OS identity master so China (and HK where
the same gap binds) listings/securities/issuers resolve exactly, and the GMI
bridge resolves real China company nodes or returns typed refusals — closing
the named gap that leaves ~75% of GMI China company nodes unresolved. No new
identity plane; the CANONICAL master is extended in place.

WHY: Exact identity is the program's spine (masterplan §5): every China
family (visits, funds, events, procurement, projects) keys on canonical
listing/issuer identity, and unresolved identity stays typed-unresolved by
law. The GMI→Data OS bridge (#5894) is merged but US-heavy; China/HK return
unresolved/not-in-master. PR-0D is the wave the c0 adjudication and this
masterplan assigned to extend the canonical master.

SCOPE:
- Extend the canonical Data OS master (the spine `engine/stock_identity/`
  family — locate the exact writer/reader seam from the current
  `WS:STOCK-IDENTITY` record before editing) with China listing identity:
  A-share/H-share listings, venue + ticker + ISIN where published, issuer
  linkage, and the USCC + LEI keys where obtainable from primary sources.
- Canonical key law (CN-B #5947, adopted; Sol precision ruling 2026-08-19):
  USCC and LEI are EXTERNAL deterministic identity evidence — resolution
  keys INTO the canonical Data OS issuer/security/listing identity — and
  are NEVER replacements for Mastermind's own canonical IDs. The Data OS
  master keeps minting its canonical identifiers; USCC/LEI/exchange
  ticker/venue/ISIN attach to them as deterministic external keys and
  aliases. Vendor entity IDs (Qichacha/Tianyancha/Wind/equivalent) may be
  stored ONLY as alias/evidence fields, never as canonical identity, and no
  vendor API may be called — the resolver NO-BUY stands (masterplan §8.2).
  Primary sources only: exchange pages, CNInfo, HKEX, GLEIF, official
  registries.
- Parent/control facts, where this wave records them at all, are dated
  `(legal_person, role, counterparty, source, as_of, known_at)` tuples from
  primary documents; HKSCC is a nominee, never a parent. If parent/control
  is out of reach this wave, leave it typed-absent — do not approximate.
- GMI bridge: China company nodes resolve through the extended master or
  return TYPED refusals (unresolved reason codes), never silent drops or
  fuzzy matches. Measure and report the before/after resolution rate on the
  GMI China node population.
- Earnings identity seam: the issuer layer is CIK-locked at three named
  sites (`engine/company_intelligence/identity.py:40,50-58,158`;
  `engine/company_intelligence/events.py:292`). This wave may PREPARE the
  master so a future Earnings-owner wave can mint non-CIK `company_id`s, but
  it does NOT edit those sites, does NOT mint China events, and does NOT
  touch `EVENT_STATES` or any `engine/company_intelligence/` event surface.

OUT OF SCOPE (the §0-ter.6 boundary, binding): NO Earnings event-adapter
work — CN issuer admission into event truth is a later Earnings-owner wave
post-E2 under `DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL`. No
`china_corporate_event.v1` on any path. No `china_company_master` or any
second identity plane (`DNR`-class boundary, masterplan §15.5). No vendor
resolver purchase or API call (#5947 NO-BUY). No edits to
`engine/company_intelligence/` (authority_changed blast radius + another
owner's territory). No scoring, ranking, or Prophet contact. No `data/`
bytes committed from your session (nightly advances `data/`; sparse-tree
law: never `git add` a `data/` diff).

FROZEN SPEC: masterplan §5 (identity law), §13 PR-0D block, §0-ter.6
boundary, CN-B #5947 key law, and the current `WS:STOCK-IDENTITY` seam you
name in the PR body. If the spine's actual writer seam contradicts this
commission, STOP and return the conflict — do not improvise a second plane.

OWNED FILES: the Data OS master extension seam (named exactly in your PR
body after reading `WS:STOCK-IDENTITY`), the GMI bridge resolution path
(`engine/theme_graph/identity.py` family), new/extended tests. Nothing
under `engine/company_intelligence/`.

TESTS: (1) resolution: a fixture set of hostile China identities (A/H
dual-listing, renamed issuer, SOE subsidiary, unresolved name) resolves
exactly or refuses typed; (2) bridge: GMI China node resolution rate
measured before/after on fixtures, refusals typed; (3) no-regression: US
resolution paths byte-identical on fixtures; (4) alias law: a vendor ID in
an alias field never satisfies canonical-key lookup. Targeted tests only —
no full suite in a sparse tree.

NOT DONE UNLESS: all four tests green; resolution-rate delta reported with
receipts; zero `engine/company_intelligence/` edits in the diff; no vendor
API calls anywhere; `python3 scripts/agentos.py validate` exit 0; ship loop
owned to merged; WS wave `pr0d` flipped to **`BUILT_NOT_PROVEN`** — NOT
`done` — in the same PR.

COMPLETION LAW (masterplan §0-bis, binding): `pr0d` flips to `done` ONLY
after the first real production run that exercises the extended master
(nightly GMI bridge resolution or the first consuming collector run)
demonstrates the improved China resolution on real nodes, receipt (run id +
measured rate) recorded in the WS record by the follow-up verification
session.

RETURN: STATUS / RESULT (resolution-rate before/after, seam named, boundary
attestations) / EVIDENCE (test outputs, PR number) / GAPS / DEVIATIONS.
