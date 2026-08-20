# PR-0D — China exact identity extension (OWNER-ROUTED — not a spawn commission)

> **AUTHORITY CORRECTION (Sol adjudication 2026-08-20 —
> `DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK`): do NOT spawn a China-lane builder
> from this file.** Its original `WS:STOCK-IDENTITY` / `engine/stock_identity/`
> builder pointer was a mistaken seam. Canonical identity authority is the Data OS
> master (`lib/dataos/identity.py` + canonical builder
> `scripts/build_security_master.py` + `data/reference/` receipts), with GMI
> consuming it through the existing `gmi.identity_resolution/v1` projection (D2A
> #5894). Implementation is owned by the bounded child **D2B2-CN-HK** under
> `WS:PROPHET-US-V4-RECOVERY` / Data OS identity authority — frozen contract +
> spawn commission: `research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md`
> (China/HK slice only; the full D2B2 US/Canada backlog stays unauthorized).
> China wave `pr0d` is **OWNER_ROUTED_WAIT / consumer-verifier**: it adopts the
> owner result by reference at D2B2-CN-HK merge (BUILT_NOT_PROVEN) and flips to
> `done` only after a natural production nightly demonstrates real China/HK nodes
> flowing source → canonical master → GMI projection (run ID + measured CN/HK
> resolution delta recorded in the WS record). The text below is preserved as the
> China-lane requirement record; wherever it names a build seam, the D2B2-CN-HK
> frozen contract supersedes it.

**Program:** `WS:CHINA-ALPHA-INTELLIGENCE` wave `pr0d` · **Route:** owner-routed to `WS:PROPHET-US-V4-RECOVERY` child D2B2-CN-HK (see banner)
**Authority:** `research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md` §5 + §13 PR-0D + §0-ter.6 boundary; `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE`; `DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK`; `DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL` (boundary it must NOT cross).
**Coordination gate:** identity implementation coordinates inside the `WS:PROPHET-US-V4-RECOVERY` V4-D2 lane (D2A/D2B1/D2B1-R1 frozen contracts), never here.
**Spawn note (historical):** the SECTION block below was the original routed-spawn contract; it is superseded as a spawn vehicle by the D2B2-CN-HK commission.

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
- Extend the canonical Data OS master (the spine `lib/dataos/identity.py` via
  its canonical builder `scripts/build_security_master.py` — the exact seam is
  frozen in the D2B2-CN-HK contract, seam pointer corrected 2026-08-20 per
  `DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK`) with China listing identity:
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
boundary, CN-B #5947 key law, and the canonical Data OS seam
(`lib/dataos/identity.py` + `scripts/build_security_master.py`) as frozen in
`research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md`. If the
spine's actual writer seam contradicts this commission, STOP and return the
conflict — do not improvise a second plane. (This STOP clause fired
2026-08-20; the return produced the owner-route adjudication.)

OWNED FILES: the canonical Data OS master extension seam
(`scripts/build_security_master.py` + `lib/dataos/` + `data/reference/`
through the canonical builder only), the GMI bridge resolution path
(`engine/theme_graph/identity_resolution.py` family, D2A seam),
new/extended tests. Nothing under `engine/company_intelligence/`. All owned
by the D2B2-CN-HK child, not a China-lane builder.

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
