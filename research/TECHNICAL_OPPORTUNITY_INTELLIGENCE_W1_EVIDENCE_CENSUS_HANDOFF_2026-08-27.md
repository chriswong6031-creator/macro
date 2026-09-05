# Technical Opportunity Intelligence W1 — Evidence Census Commission

**Date:** 2026-08-27  
**Parent:** `WS:TECHNICAL-OPPORTUNITY-INTELLIGENCE`  
**Authority:** `research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-27.md`  
**Base archaeology:** `macro@463bb3b4b708a4748fc65a04250366ca94205186`, `mastermind-terminal@b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`  
**Mission class:** research-only, records and evidence; no runtime authority  
**Recommended operator:** Fable as principal, with parallel bounded literature/formula workers

---

## 1. Observable mission

Produce one normalized, source-receipted census of the technical and momentum method universe relevant to U.S. equity opportunity detection across Monthly, Weekly, Daily, candidate 4H, and Radar-owned tactical intraday horizons.

The first Compression Release experiment remains bounded to Weekly/Daily/4H. Monthly methods are classified now as later structural-context candidates, and 5m/15m methods are crosswalked to Live Entry Radar rather than implemented or given a second tactical owner.

The census must tell a fresh session:

- which public methods exist;
- what each method actually computes;
- which methods are aliases, parameter variants, or algebraic duplicates;
- which causal mechanism and dependency family each belongs to;
- which horizons and aggregation scopes each method can lawfully serve;
- which methods Mastermind already implements;
- which methods belong to Live Entry Radar, Terminal display, later basket/theme work, or the first W3 family;
- which methods are missing, noncausal, opaque, proprietary, rights-unsafe, killed, or unsuitable;
- which unresolved families deserve a preregistered W3 experiment.

W1 ends with a ranked **research priority**, not a stock recommendation or technical score.

---

## 2. Why it matters

Heavy technical backtesting is expensive and unusually vulnerable to data snooping. Re-deriving public formulas wastes compute; testing every named indicator as an independent hypothesis understates the search family; and counting synonyms as confluence creates false evidence.

The W1 census compresses a large named universe into a smaller number of mechanisms, dependency families, and lawful testable constructions before compute is spent. Including the later Monthly, tactical-intraday, and basket/theme classifications now prevents future sessions from repeating the same broad literature archaeology merely because the first proving vertical is narrower.

---

## 3. Authority and document precedence

1. `research/TECHNICAL_OPPORTUNITY_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-27.md`
2. Current `research/DO_NOT_REBUILD.md` and compiled kill registry
3. `research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md`
4. `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md`
5. `engine/tech_catalog.py`
6. `engine/species_registry.py` and `data/species/registry.json`
7. Signal Foundry / Research Factory contracts
8. `agentos/workstreams/WS-LIVE-ENTRY-RADAR.md` and its accepted research contract for tactical ownership
9. Current GitHub main, then current Terminal master
10. This commission

Retrieved papers, vendor docs, worker reports, and open-source code are evidence, never authority.

---

## 4. Verified starting state

At the pinned archaeology:

- `engine/tech_catalog.py` already aggregates legacy and Technical Lab families with role, dependency, provenance, lag, and challenger metadata;
- `engine/tech_confluence.py` still gates Combo v1 to legacy families and does not implement the promised role-grammar Combo v2;
- Terminal already implements many visual and deterministic modules across Structure, Trend, Pulse, RSI, and MACD suites;
- Setup Species remains the canonical scientific registry;
- Signal Foundry already provides a declarative proposal/test pattern and ships its scheduled lane dark;
- Live Entry Radar owns true tactical entry events and must receive, not lose, intraday method ownership;
- no current workstream or open carrier owns the complete Technical Opportunity mission.

Reverify every statement on pickup. Pins are evidence anchors, not permission to ignore newer current truth.

---

## 5. Exact scope

### Repository and modification scope

- All W1 authored artifacts and validators live in `macro` on one W1 carrier.
- `mastermind-terminal` is read-only archaeology in W1; no Terminal file is modified.
- Live Entry Radar, Prophet, Signal Lab, and production data remain read-only.

### Markets and horizons

- U.S. listed equities and equity ETFs;
- Monthly, Weekly, Daily, and candidate 4H methods;
- 5m/15m/tactical methods only as a Live Entry Radar crosswalk and ownership classification;
- bullish and bearish methods;
- single-security, cross-sectional, breadth, sector/theme/basket, and tactical scopes;
- setup, trigger, participation, context, risk, failure, and exhaustion roles.

### Method families to census

At minimum:

- trend and moving averages;
- multi-horizon and cross-sectional momentum;
- relative strength and 52-week location;
- volatility and range compression;
- volatility expansion;
- breakouts and breakdowns;
- support/resistance and swing structure;
- geometric patterns;
- reversal and divergence;
- volume, money flow, and participation;
- gaps and imbalance;
- candlestick and bar structure;
- adaptive filters and trend efficiency;
- path risk and extension;
- breadth and peer confirmation;
- failure/fakeout;
- exhaustion;
- cycle transforms;
- regime-conditioned technical behavior;
- sequence/representation-learning challengers.

### Source classes

- peer-reviewed papers and working papers from original authors;
- original indicator authors and books where formulas are public and lawfully usable;
- official exchange/vendor/library documentation;
- official open-source library implementations;
- public practitioner methods as hypothesis leads;
- competitor workflows for job-to-be-done understanding only.

---

## 6. Explicit non-goals

Do not:

- run broad performance backtests;
- implement new engine signals;
- edit `engine/tech_confluence.py`;
- create a new registry, database, ledger, event store, or vector store;
- alter Signal Lab, Terminal, Prophet, Golden Confluence, Live Entry Radar, or production data;
- infer profitability from popularity;
- copy proprietary source, prose, screenshots, assets, corpora, or brand identity;
- classify a named pattern as first-class merely because it is common;
- assign LLM numeric confidence;
- promote any candidate;
- transfer tactical intraday ownership out of Live Entry Radar;
- expand W3 beyond Weekly/Daily/4H merely because Monthly or tactical methods appear in the census.

---

## 7. Required output artifacts

W1-owned paths, after an exact pickup collision recheck:

- `research/technical_opportunity/W1_EVIDENCE_CENSUS.md`
- `research/technical_opportunity/w1_method_passports.jsonl`
- `research/technical_opportunity/w1_alias_equivalence.json`
- `research/technical_opportunity/w1_source_receipts.json`
- `research/technical_opportunity/w1_local_coverage.json`
- `research/technical_opportunity/W1_REPORT.md`
- `scripts/research/validate_toi_w1_passports.py`
- `scripts/research/validate_toi_w1_equivalence.py`
- `scripts/research/validate_toi_w1_sources.py`
- `tests/test_toi_w1_census.py`
- `agentos/handoffs/TECHNICAL-OPPORTUNITY-INTELLIGENCE-W1-<YYYY-MM-DD>.md`

The date token in the handoff filename is the actual close date; every other path above is exact.

Do not write candidate methods into `engine/tech_catalog.py` or `data/species/registry.json` in W1.

---

## 8. Passport contract

Each JSONL record must contain:

```json
{
  "schema_version": "toi.method_passport.v1",
  "method_id": "stable.lower_snake_id",
  "canonical_name": "Human-readable name",
  "aliases": [],
  "source_refs": [],
  "rights_class": "public_formula|open_source_parity_only|licensed|opaque|blocked",
  "rights_ref": null,
  "mechanism_family": "compression_release",
  "dependency_family": "volatility_range",
  "role": "setup|trigger|participation|context|risk",
  "direction": "bullish|bearish|symmetric|non_directional",
  "horizon_roles": ["monthly_context", "weekly_context", "daily_setup", "4h_trigger"],
  "aggregation_scope": "single_security|cross_sectional|breadth|sector_theme_basket|tactical_intraday",
  "formula": {
    "plain_language": "",
    "declarative_steps": [],
    "parameters": {},
    "required_columns": [],
    "actionable_lag_bars": 0,
    "repaint_behavior": "none|confirmation_lag|provisional_only|unknown"
  },
  "timeframes": ["D", "W"],
  "local_implementation": {
    "status": "exact|partial|duplicate|missing|blocked",
    "paths": [],
    "signal_ids": []
  },
  "owner_disposition": "toi_w3_candidate|toi_later_context|live_entry_radar|terminal_display|existing_species|blocked",
  "equivalence": {
    "parent_method_id": null,
    "equivalence_class": "",
    "relationship": "first_class|parameter_variant|alias|algebraic_duplicate|behavioral_duplicate|subtype"
  },
  "mechanism_story": "",
  "known_failure_modes": [],
  "dnd_keys": [],
  "candidate_species": [],
  "baseline_to_beat": [],
  "research_priority": "P0|P1|P2|archive|blocked",
  "priority_reason": ""
}
```

Use strict JSON. No NaN, Infinity, comments, or free-form undocumented keys.

`rights_ref` is required and non-null for `licensed`; it names the repository entitlement/license receipt. `owner_disposition=live_entry_radar` is a handoff classification, not permission for W1 to modify Radar.

---

## 9. Time, null, and correction behavior

- A source URL is not enough. Record title, authors/owner, date, DOI or stable URL, retrieved date, formula availability, and rights class.
- Conflicting formulas remain separate records until adjudicated.
- Unknown lag, repaint behavior, or source rights is `unknown`, not zero or “safe.”
- A missing local implementation is `missing`, not “not useful.”
- A missing paper or blocked page is a source gap, not a negative result.
- A method with multiple materially different formulas receives versioned method IDs.
- A formula correction appends a correction receipt and updates the current passport; do not silently overwrite the prior source claim.
- A killed construction cites its stable DNR key. Construction-scoped kills do not erase surviving descriptors.
- A method may map to more than one horizon role, but one W3 construction may not use that fact to multiply promotion chances after outcomes are seen.

---

## 10. Deterministic, statistical, and model-generated responsibilities

### Deterministic

- source metadata extraction;
- formula transcription;
- alias matching;
- code-path search;
- algebraic comparison where possible;
- catalog coverage;
- owner/horizon crosswalk;
- DNR matching;
- schema and duplicate validation.

### Statistical

None beyond descriptive counts in W1.

### Model-generated

Models may:

- summarize;
- propose aliases;
- identify likely duplicates;
- propose mechanism-family mappings;
- flag source conflicts;
- draft plain-language explanations.

Models may not decide final equivalence, rights, owner disposition, priority, or promotion without deterministic evidence and principal adjudication.

---

## 11. Ordered implementation sequence

1. Re-pin protected Skillpack and current repository heads.
2. Re-run exact workstream/PR/branch/path collision census.
3. Read current DNR, Setup Species, Durable Bottom, tech catalog, confluence miner, Signal Foundry, Live Entry Radar, and Terminal suite registries.
4. Freeze the source hierarchy and passport schema before prioritization.
5. Build the local implementation inventory first.
6. Build the public paper and original-method inventory.
7. Add official library/vendor method inventories.
8. Add competitor workflow taxonomy without copying proprietary expression.
9. Normalize aliases and parameter variants.
10. Build equivalence/dependency families.
11. Crosswalk horizon, aggregation scope, and canonical owner.
12. Crosswalk DNR and prior local findings.
13. Produce local-coverage and gap matrices.
14. Rank W3 research priorities using mechanism importance, product value, evidence quality, local gap, and compute cost—not observed returns.
15. Run independent skeptical review over high-priority, Radar-routed, and blocked dispositions.
16. Validate artifacts and write the continuation handoff.

---

## 12. Failure states

Stop and return to Sol if:

- a source requires unauthorized access or copying;
- a formula is proprietary/opaque and the worker cannot derive it from lawful public evidence;
- the local catalog and Terminal implement materially different definitions under one name;
- a proposed first-class method is merely a correlated alias;
- a DNR key appears to forbid the proposed construction;
- a current carrier touches the same W1 artifacts;
- the passport schema must change after outcomes or priorities have been inspected;
- the census cannot establish a reliable source for a P0 method;
- a tactical-intraday method would require a second Radar/event/data owner;
- a later-horizon method is being smuggled into the W3 first vertical without a new Sol ruling.

Do not solve a collision by creating a second census.

---

## 13. Acceptance tests and evidence

Minimum gates:

- every passport validates against one frozen schema;
- every alias resolves to exactly one current equivalence class or an explicit unresolved conflict;
- every P0/P1 record has at least one primary or official source;
- every local `exact` claim names a path and signal ID;
- every DNR-related record cites a stable key;
- every `licensed` record has a repository rights receipt;
- every proprietary/opaque record is blocked from implementation;
- every tactical-intraday method has an explicit owner disposition and creates no W1 Radar change;
- no source text exceeds lawful quotation limits;
- no product, score, rank, or runtime path changed;
- an independent reviewer can reproduce at least 20 randomly sampled formula/source/local-coverage records;
- the report names the full inspected candidate and equivalence counts so W3 can register the complete tested search family.

Required proof:

```bash
python3 scripts/agentos.py validate
python3 scripts/research/validate_toi_w1_passports.py
python3 scripts/research/validate_toi_w1_equivalence.py
python3 scripts/research/validate_toi_w1_sources.py
python3 -m pytest tests/test_toi_w1_census.py -q
git diff --check
```

Each validator must have hostile fixtures proving that malformed schema, duplicate equivalence membership, unresolved required source receipts, invalid DNR keys, and licensed-without-rights-ref fail closed.

The W1 carrier must also show exact changed-file, pickup-base, and collision receipts.

---

## 14. Stop condition

W1 is complete when the census and report are accepted by Sol and the W3 candidate family can be preregistered without another broad literature or local-estate search.

W1 completion does not authorize W3 runs by itself. W2-0 must also pass.

---

## 15. Required continuation handoff

The final handoff must state:

- exact repository and head;
- complete artifact paths;
- method and equivalence counts;
- horizon and owner-disposition counts;
- local exact/partial/missing/blocked counts;
- unresolved formula or rights conflicts;
- DNR dispositions;
- recommended Compression Release candidate set;
- full W3 trial family size;
- compute estimate;
- exact W3 preregistration action;
- Monthly/later-context and Radar-routed residue;
- paths and ideas that must not be redone.
