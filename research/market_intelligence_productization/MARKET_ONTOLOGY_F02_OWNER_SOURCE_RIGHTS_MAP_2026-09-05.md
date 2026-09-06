# Market Ontology F02 (Policy/Geo) — Owner / Source / Rights Map

**Packet:** A-F02-W2-1 (lane F02-POLICY-GEO, wave 2). **Kind:** records, zero user-facing surface change.
**Verified at:** macro `origin/main` (this branch's base). All `file:line` anchors below were re-verified fresh at write time with `wc -l` / `grep -n`.

## 1. Purpose

This memo closes the OWNER-AMBIGUITY block recorded against ledger rows `MO-PAID-006`, `MO-PAID-023` and `MO-PAID-034` (`research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv:16,19,20`) by naming, for each F02 capability, ONE canonical existing-module owner — never a new truth plane. It also freezes the rights posture for `MO-PAID-048/049/050` and prints the nulls this archaeology could not resolve.

## 2. Verified owner map

### 2.1 Policy lifecycle (proposal → passage → effective → enforced)
- **Owner A — `engine/policy_intent_desk.py`** (515 lines). Append-only intent ledger: `gather_state()` :196, `synthesize()` :291, `_append_ledger()` :343, `_persist()` :388, `run()` :409, `_read_ledger()` :445, `score()` :459, `enabled()` :105.
- **Owner B — `engine/transmission_chains.py`** (1466 lines). Deterministic chain schema + evaluation: `ChainSchemaError` :109, `validate_chain()` :190, `load_chains()` :256, `build_adapters()` :399, `eval_test()` :589, `eval_node()` :619, `_latest_open_episode()` :643.
- Registry anchor: `policy-transmission-intelligence` at `config/mastermind_programs.yml:2306`; implementation root `engine/transmission_chains.py` at :2332; `authority_class: context_only`; `does_not_own: Directional decisions or portfolio sizing`.
- Adjacent, non-owning: `engine/policy_calendar.py` (466 lines; `compute_policy_calendar()` :70, `format_policy_reg_chip()` :222, `_compute_entity_list_events()` :299, `_append_ledger()` :410) — calendar/entity-list event chips, not the lifecycle-state owner.

### 2.2 Country / EM risk
- **Owner A — `engine/intl_risk.py`** (744 lines). `em_stress()` :486, `_country_row()` :632, plus `_leg()` family (:151-:443).
- **Owner B — `engine/international_macro_dashboard.py`** (1158 lines). `REGIONS: dict[str, RegionSpec]` :96, `build_country_view()` :933, `validate_view()` :1129.
- Consumer: `scripts/build_international_macro.py`. Surfaces (named only, not modified): `templates/intl.html.j2` → `site/intl.html`; country pages `japan.html`, `south_korea.html`, `euro_area.html`, `united_kingdom.html`, `india.html` (canonical destination registry at `templates/_navlinks.html.j2:176-188`).
- Registry anchor: `international-risk-intelligence` at `config/mastermind_programs.yml:2273`; implementation root `engine/intl_risk.py` at :2299; `authority_class: context_only`.

### 2.3 Political desk
- **Owner A — `engine/whitehouse_brain.py`** (567 lines). `enabled()` :199, `provider_label()` :223, `_call_model()` :274, `_macro_backdrop()` :377, `_norm_sectors()` :412. Gated, context-only, degrade-never-raise.
- **Owner B — `engine/whitehouse_feed.py`** (247 lines). `_parse()` :124, `collect()` :165, `_recent()` :191, `load_processed()` :214, `save_processed()` :226, `mark_seen()` :235, `new_items()` :244.
- Consumer: `scripts/build_whitehouse.py`.

### 2.4 Qualitative event bus
- **Owner A — `engine/qbus.py`** (627 lines). `assign_event_keys()` :176, `append_items()` :246, `event_key_for_title()` :563, plus `body_sha256()` :88, `normalize_row()` :113, `read_items()` :274, `build_index()` :348, `novelty_z()` :445, `echo_stats()` :502.
- **Owner B — `engine/china_news_intel.py`** (1067 lines, China-scoped PIT). `event_id()` :184, `classify_theme()` :194, `tag_baskets()` :202, `tag_tickers()` :288, `source_tier()` :325, `is_surprise()` :338, `importance_score()` :346, `importance_band()` :358. Consumer: `scripts/build_china_news.py`, `scripts/collect.py`.
- **Owner C — `engine/news_vector.py`** (701 lines, generic wire PIT). `event_id()` :146, `classify_theme()` :153, `source_tier()` :163, `build_records()` :180, `accrue()` :266, `fetch_range()` :355.
- Registry anchor: `qualitative-intelligence` at `config/mastermind_programs.yml:2054`; implementation root `engine/qbus.py` :2082 and `data/qbus/`; `authority_class: context_only`; `does_not_own: Deterministic ranks, gates, sizes, or trades`.

### 2.5 Sanctions display owner — IN FLIGHT, NOT LANDED

**Correction to the packet's own drafting note:** the packet text asserted `engine/sanctions_map.py` exists and is verified at fresh main. It does **not** exist at this branch's base (`wc -l engine/sanctions_map.py` → no such file). The module is real work, but it is **unmerged**, in flight on sibling branch `claude/mo-a-a1-a-f02-1` (commits `aa2a3a6`, `366b6b1`, `b7e7ff3`; branch head `b7e7ff33d8fd1931e52f4300fc2db3a6c404c8ee` at verification time). This memo therefore cites it as an **in-flight design**, not a landed owner, and does not claim its line anchors as verified against this branch's base.

Per that branch's own commits (not independently re-verified here — flagged `unverified` in the handoff), the intended shape is: `engine/sanctions_map.py`, a human-reviewed, display-only sanctions leaf reading `data/sanctions_ofac/` (`STORE_DIR`, `SDN_FILE`, `META_FILE`) against `config/sanctions_ofac_programs.yml` (`PROGRAMS_CONFIG`), with a `build()` entry point; the design intent (per that branch's docstring) is "no LLM originates any attribution, count, or rung. Every country<->programme edge comes from the human-reviewed config/sanctions_ofac_programs.yml. Never raises. Nulls are `None`, never `0`." Intended builder: `scripts/build_sanctions_map.py`; intended surface: `templates/sanctions_map.html.j2` → `site/sanctions_map.html`; intended nav: `templates/_navlinks.html.j2:195`.

**Why this still matters here:** once `claude/mo-a-a1-a-f02-1` merges, this design — and no other — is the sanctions-display owner-to-be, and the lane `do_not_redo` (§6) forbids a second sanctions truth store from being started in parallel. Until that merge, sanctions display ownership is **not yet resolved on main** and is recorded as UNRESOLVED-3a below in addition to the lifecycle gap in UNRESOLVED-3.

## 3. Row dispositions

**MO-PAID-006** (`UPGRADE_EXISTING_OWNER / PARTIAL`; missing contract = political/institutional dossier layer; note: "OWNER-AMBIGUITY flagged to program: F02 lane owner unresolved").
- OWNER: `engine/international_macro_dashboard.py` — the dossier is a new field family inside `build_country_view()` :933 and must pass `validate_view()` :1129; `engine/intl_risk.py` (`_country_row()` :632, `em_stress()` :486) stays the risk-leg leaf feeding it.
- NOT OWNER: `engine/qbus.py` (event bus, not a country master), `engine/whitehouse_brain.py` (US political desk, not a country dossier producer), the in-flight sanctions leaf (§2.5, display leaf, not a dossier producer). **No new country master** — binding under do_not_redo.
- NULL: no dossier producer or schema exists today (UNRESOLVED-1).

**MO-PAID-023** (missing contract = political-intelligence coverage beyond US WH + China tone; correction behavior = "banner gated/context-only; policy_intent append-only ledger").
- OWNER: the `engine/whitehouse_brain.py` + `engine/whitehouse_feed.py` contract is the template a second-country political desk must mirror (gated `enabled()` :199, provider-disclosed `provider_label()` :223, degrade-never-raise, feed dedup `new_items()` :244); `engine/policy_intent_desk.py` remains the append-only intent ledger (`_append_ledger()` :343).
- NOT OWNER: `engine/qbus.py` (join surface, not a desk), `engine/china_news_intel.py` (China-scoped ingest, not a political desk), `engine/news_vector.py` (generic wire ingest).

**MO-PAID-034** (note: "OWNER-AMBIGUITY flagged: geopolitical event mapping owner explicitly unresolved"; missing contract = non-China geopolitical/policy event pipeline joined to the qbus Event system).
- OWNER of event identity/join: `engine/qbus.py` (`assign_event_keys()` :176, `event_key_for_title()` :563, `append_items()` :246) — the single Event system. OWNER of the non-China producer pattern: `engine/news_vector.py` (`build_records()` :180, `accrue()` :266), following the China reference implementation in `engine/china_news_intel.py`.
- NOT OWNER: `engine/china_news_intel.py` is not the owner of non-China events (China-scoped by construction); `engine/transmission_chains.py` owns policy→asset transmission edges, not event identity; `engine/international_macro_dashboard.py` and the in-flight sanctions leaf are consumers/leaves, never event owners. **No second event database** — binding under do_not_redo.

**Closure sentence:** the 2026-08-26 F02 handoff `unresolved[]` entry — "Exact canonical owners for policy lifecycle, sanctions, trade restrictions and geopolitical event mapping" — is closed **by name** for policy lifecycle (§2.1) and geopolitical event mapping (§3, MO-PAID-034). Sanctions display ownership is **named but in flight, not closed** (§2.5 — unmerged branch `claude/mo-a-a1-a-f02-1`). Trade restrictions and the sanctions LIFECYCLE plane remain open and are recorded as UNRESOLVED-3, UNRESOLVED-3a and UNRESOLVED-4 below, never as resolved.

## 4. Rights docket

| Row | Capability | Ledger disposition | Rights state | Gate holder |
|---|---|---|---|---|
| MO-PAID-048 | Military asset tracking | `REJECTED_BY_DESIGN / NOT_BUILT` | `PENDING_RIGHTS confirmed — no lawful source integrated` | Chairman / commercial licensing gate |
| MO-PAID-049 | Maritime / AIS | `BLOCKED_RIGHTS / NOT_BUILT` (AIS/maritime grep clean — only a keyword list in `config/theme_thesis_registry.yml`) | `PENDING_RIGHTS — no lawful AIS vendor in repo` | Chairman / commercial licensing gate; consolidated F09/F02 rights docket |
| MO-PAID-050 | Satellite imagery | `REJECTED_BY_DESIGN / NOT_BUILT` (only "satellite" code hit = sector keyword `engine/altdata_models.py:274`) | `PENDING_RIGHTS — Planet/Maxar-class licensing gate; none present` | Chairman / commercial licensing gate |

Ruling, recorded verbatim: "RULED (Sol PROGRAM-CEO C2 docket ruling, #6748 comment 5504596085 / CEO carrier 1788325004.496539): REJECTED_BY_DESIGN / RIGHTS_GATED_UNLICENSED — the lawful military-asset-tracking job is preserved behind a future explicit licensing gate; no spend/build authority now." (Same ruling text applies to MO-PAID-050 for satellite/Planet-Maxar-class sources.) No build authority and no spend authority exists for 048/049/050 today; all three are `context_only` even if later built.

## 5. Nulls printed, not hidden

1. **UNRESOLVED-1 — country political/institutional dossier producer.** No producer or schema exists (MO-PAID-006). Resolves when: a bounded child ships a dossier schema whose records pass `validate_view()` (`engine/international_macro_dashboard.py:1129`) and render on one country page.
2. **UNRESOLVED-2 — non-China geopolitical event producer.** Only `engine/china_news_intel.py` (China-scoped) and `engine/news_vector.py` (generic macro wire) exist; no region-scoped non-China PIT producer. Resolves when: one non-China region has a producer whose rows join through `qbus.assign_event_keys()` (`engine/qbus.py:176`).
3. **UNRESOLVED-3 — sanctions LIFECYCLE owner (licenses, amendments, delistings, versions).** Even once `claude/mo-a-a1-a-f02-1` lands, its design (§2.5) is a display-only snapshot view; it has no amendment/version/known-at plane. Resolves when: a versioned, human-reviewed lifecycle contract is defined on the existing store (never a second store).
3a. **UNRESOLVED-3a — sanctions display ownership is not yet landed on main.** `engine/sanctions_map.py` does not exist at this branch's base; it exists only on unmerged branch `claude/mo-a-a1-a-f02-1`. Resolves when: that branch merges to main — this memo's DEC record should then be updated to cite it as landed.
4. **UNRESOLVED-4 — trade restriction / export-control state owner.** No dedicated module; the only structured surface is entity-list events in `engine/policy_calendar.py:299` plus keyword hits in news modules. Resolves when: a named owner module with a deterministic legal-state contract is designated.
5. **UNRESOLVED-5 — program-registry binding gap.** `config/mastermind_programs.yml` carries implementation roots only for `engine/qbus.py` (:2082), `engine/intl_risk.py` (:2299) and `engine/transmission_chains.py` (:2332). `whitehouse_brain.py`, `whitehouse_feed.py`, `policy_intent_desk.py`, `china_news_intel.py`, `news_vector.py`, `international_macro_dashboard.py`, the in-flight sanctions leaf, and `policy_calendar.py` have no registry root binding. Resolves when: a separate registry-edit child adds the roots — out of this packet's owned paths; record it, do not do it.
6. **UNRESOLVED-6 — geospatial/map object owner.** No geospatial module exists in `engine/` (the `geo`/`map`-shaped filenames are not geography). Resolves only behind the rights gate in §4; no geospatial object store may be created (do_not_redo).

## 6. Binding do_not_redo

Restated verbatim from `agentos/handoffs/MARKET-ONTOLOGY-F02-POLICY-GEO-GEOSPATIAL-FABLE-COO-2026-08-26.md` frontmatter:

- "No second event database, country master, sanctions truth store, geospatial object store or map-specific identity plane."
- "No LLM-created sanctions, military, shipping or causal relationship facts."

Binding on every F02 child. Concrete planes protected: events → `engine/qbus.py`; country master → `engine/international_macro_dashboard.py:96` `REGIONS`; sanctions truth → the design in flight on `claude/mo-a-a1-a-f02-1` reading `data/sanctions_ofac/` + `config/sanctions_ofac_programs.yml` (no second store may be started while that branch is unmerged, and none after); geospatial object store → none exists and none may be created.

## 7. LLM authority clause

No LLM may originate a signal, score, escalation, sanctions fact or causal relation in F02. LLMs summarize or classify non-authoritatively over cited inputs only (Neural Web constitution A7 + F02 lane method law). Evidence: the in-flight sanctions design's own docstring states "no LLM originates any attribution, count, or rung" (§2.5, unverified against this branch's base — cited as design intent, not a landed guarantee); `engine/whitehouse_brain.py` is gated (`enabled()` :199) and provider-disclosed (`provider_label()` :223); all three landed F02 registry programs are `authority_class: context_only` (`config/mastermind_programs.yml:2054`, :2273, :2306).

## 8. Records

- `DEC:F02-POLICY-GEO-OWNER-MAP`
- `WS:MARKET-OS`
