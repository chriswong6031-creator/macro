---
key: F02-POLICY-GEO-OWNER-MAP
question: >
  Which module is the canonical owner of each F02 capability (policy lifecycle,
  country/EM risk, political desk, qualitative event bus, sanctions display), and
  which modules are explicitly NOT owners?
answer: >
  Policy lifecycle is owned by engine/policy_intent_desk.py (append-only intent
  ledger) plus engine/transmission_chains.py (deterministic chain schema/eval);
  country/EM risk is owned by engine/intl_risk.py (risk-leg leaf) plus
  engine/international_macro_dashboard.py (REGIONS, build_country_view,
  validate_view); the political desk is owned by engine/whitehouse_brain.py plus
  engine/whitehouse_feed.py; the qualitative event bus is owned by engine/qbus.py
  (event identity/join) plus engine/china_news_intel.py (China-scoped producer)
  and engine/news_vector.py (generic wire producer). Sanctions display is NOT yet
  a landed owner: engine/sanctions_map.py does not exist on this branch's base and
  is in flight, unmerged, on sibling branch claude/mo-a-a1-a-f02-1. Row
  dispositions: MO-PAID-006's country dossier upgrades
  international_macro_dashboard.py; MO-PAID-023's second-country political desk
  mirrors the whitehouse_brain.py/whitehouse_feed.py contract; MO-PAID-034's
  non-China event pipeline joins through qbus.py using news_vector.py as the
  producer pattern. No module listed as NOT OWNER for a capability may be
  upgraded to own it without a fresh decision.
rationale: >
  Owner-by-existing-module (rather than minting a new F02 truth plane) is
  required by the lane do_not_redo, which forbids a second event database,
  country master, sanctions truth store, geospatial object store, or
  map-specific identity plane. All three landed F02 registry programs
  (qualitative-intelligence, international-risk-intelligence,
  policy-transmission-intelligence) are already registered
  authority_class: context_only at config/mastermind_programs.yml:2054,:2273,:2306
  respectively, so routing new capability growth through those same owners keeps
  authority scoping intact instead of creating an unscoped fourth plane. The
  sanctions leaf is cited as in-flight rather than landed because
  engine/sanctions_map.py was verified absent from this branch's base at write
  time (wc -l: no such file) while confirmed present on sibling branch
  claude/mo-a-a1-a-f02-1 (head b7e7ff33d8fd1931e52f4300fc2db3a6c404c8ee) — citing
  it as landed would have been a false verification claim.
alternatives:
  - option: "Mint a new F02 policy/geo truth plane owning events, countries and sanctions"
    why_not: "Forbidden verbatim by the lane do_not_redo; would create a second event database, country master and sanctions truth store."
  - option: "Leave ownership unresolved until a first vertical is chosen"
    why_not: "MO-PAID-006/023/034 are blocked ON the ambiguity; every child would re-litigate the same fork."
  - option: "Cite engine/sanctions_map.py as a landed owner on the strength of the packet's own drafting note"
    why_not: "Empirically false against this branch's base (file absent); would record an unverifiable claim in a durable decision record."
evidence:
  - "engine/policy_intent_desk.py:196,343,409 (515 lines) — append-only policy intent ledger"
  - "engine/transmission_chains.py:190,256,619 (1466 lines)"
  - "engine/intl_risk.py:486,632 (744 lines)"
  - "engine/international_macro_dashboard.py:96,933,1129 (1158 lines)"
  - "engine/whitehouse_brain.py:199,223,274 (567 lines); engine/whitehouse_feed.py:165,244 (247 lines)"
  - "engine/qbus.py:176,246,563 (627 lines); engine/china_news_intel.py:184,346 (1067); engine/news_vector.py:180,266 (701)"
  - "engine/sanctions_map.py absent at this branch's base (wc -l: no such file); present on branch claude/mo-a-a1-a-f02-1 (commits aa2a3a6, 366b6b1, b7e7ff3; head b7e7ff33d8fd1931e52f4300fc2db3a6c404c8ee)"
  - "config/mastermind_programs.yml:2054,2273,2306 (program keys); roots at :2082,:2299,:2332"
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv rows MO-PAID-006/023/034/048/049/050"
affects:
  - "WS:MARKET-OS"
  - "engine/policy_intent_desk.py"
  - "engine/transmission_chains.py"
  - "engine/intl_risk.py"
  - "engine/international_macro_dashboard.py"
  - "engine/whitehouse_brain.py"
  - "engine/qbus.py"
confidence: high
reversibility: costly
decided_by: "coo-fable"
decided_at: 2026-09-05
---

# F02 policy/geo owner map

See `research/market_intelligence_productization/MARKET_ONTOLOGY_F02_OWNER_SOURCE_RIGHTS_MAP_2026-09-05.md` for the full owner table (§2), row dispositions (§3), rights docket (§4) and printed nulls (§5). Summary:

- **Policy lifecycle:** `engine/policy_intent_desk.py` + `engine/transmission_chains.py`, registered under `policy-transmission-intelligence` (`context_only`).
- **Country/EM risk:** `engine/intl_risk.py` + `engine/international_macro_dashboard.py`, registered under `international-risk-intelligence` (`context_only`).
- **Political desk:** `engine/whitehouse_brain.py` + `engine/whitehouse_feed.py` (gated, provider-disclosed, degrade-never-raise).
- **Qualitative event bus:** `engine/qbus.py` (event identity/join) + `engine/china_news_intel.py` + `engine/news_vector.py` (producers), registered under `qualitative-intelligence` (`context_only`).
- **Sanctions display:** IN FLIGHT on unmerged sibling branch `claude/mo-a-a1-a-f02-1` — not a landed owner as of this decision. Do not start a second sanctions truth store while it is unmerged or after it lands.

Row dispositions: `MO-PAID-006` upgrades `engine/international_macro_dashboard.py`; `MO-PAID-023` mirrors the `whitehouse_brain.py`/`whitehouse_feed.py` contract for a second country; `MO-PAID-034` joins non-China events through `engine/qbus.py` using `engine/news_vector.py` as the producer pattern, following `engine/china_news_intel.py` as reference. `MO-PAID-048/049/050` remain `PENDING_RIGHTS` behind the Chairman/commercial licensing gate — no build or spend authority exists for them now.

Binding under `DNR` / lane `do_not_redo`: no second event database, country master, sanctions truth store, geospatial object store, or map-specific identity plane; no LLM-created sanctions, military, shipping, or causal-relationship facts.
