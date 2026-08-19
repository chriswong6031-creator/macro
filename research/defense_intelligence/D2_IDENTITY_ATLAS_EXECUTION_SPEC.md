# D2 Identity Atlas — execution spec (frozen 2026-08-18)

Authority: Fable orchestrator session, executing `DEFENSE_D2_IDENTITY_ATLAS_PILOT_HANDOFF.md` under the Sol directive of 2026-08-18. This spec is the binding contract for the D2 build. It does not widen D2, does not merge #5424, does not start D3, and does not create a second identity system.

## 0. Acceptance gates (not done unless)

1. Entitled dossier for each pilot shows an Identity Atlas section: public security → legal issuer → legal entities → exact recipient identifiers → ownership path → validity interval → review state → evidence, with unresolved hops shown as unresolved (never minted).
2. IRDM: reviewed path rendered; P00032 clocks untouched (`effective_at 2026-05-12`, `known_at 2026-08-12T23:50:04.442107+00:00`, `is_late_discovery true`, `18416666.66`).
3. HII: reviewed entities rendered; deobligation `govws-aa6f1867ab7cae18de92e16c` (N0002415C2114/AZ0010) keeps `listed_company_impacts: []`.
4. LMT: registrant entity + 14 identifiers rendered without flattening; a Sikorsky-named identifier can never auto-attach to the registrant entity (test-pinned); Ex.21 omission clause honored (absence ≠ negative proof). (Amended 2026-08-18: the earlier "Sikorsky shown as filing-known but recipient-unobserved" display would require minting an LMT entity row with zero observed identifiers — not requested by the directive and not attempted; the directive's three LMT requirements are the enforceable set.)
5. GE: `issuer_attribution: not_asserted`, visibly unresolved with plain-word reason; no GE graph rows; no pre-split backdating.
6. BWXT: five reviewed chains live via defense21-v1; three identifiers visibly unresolved (2 gaps + 1 explicit conflict).
7. SPR: represented historical/listing-terminated (Boeing close 2025-12-08); never presented as a live issuer.
8. No candidate/authority regression: no new `grc1-*` from unreviewed paths; display/context only, no rank/gate/size.
9. defense19-v1 rows preserved byte-identical inside defense21-v1; no re-timestamped history; every evidence ref resolves; zero orphans.

## 1. Current truth (verified against bytes at origin/main `a7cfd4bef589f3c21be4712847ba35653a9fc995`)

- Live graph `recipient-graph:reviewed:2026-08-08:defense19-v1`, digest `0733a966c4442a4fc5bb883d1670320218ecc3b6754131f7ee84965d3036f758`, at `data/government_revenue/recipient_entity_graph.json` (19 companies / 101 legal entities / 203 identifiers / 101 ownership edges / 241 evidence, 0 conflicts). Contract `government_recipient_entity_graph.v1`, schema `1.1.0`.
- PR #5424 (`defense20-v1`) OPEN/draft — not merged, not consumed. Minable: BWXT evidence approach, merge-construction discipline (defense19 rows byte-identical, additions appended), test-pin updates. Poisoned: GE handling (panel-scoped zero), retained LHX/NOC `-de` phantom rows, GDLS `wholly_owned/1.0` JV overclaim.
- Mapping backlog 21 rows; BWXT `grmb1-b6aea55c4513e34edcd39b0f`, GE `grmb1-*` — both `issuer_attribution: not_asserted`, `curated_fuzzy_name`.
- Stock Identity snapshot (2,781×22, asof 2026-08-13): IRDM/HII/LMT/GE/GEV/GEHC/BWXT present; SPR/CACI/SAIC absent. `central:*` is GovRev-minted (`scripts/propose_government_revenue_recipient_graph.py:789`), not an SI field; sanctioned SI read = direct `pd.read_parquet` (house pattern, `engine/stock_identity/plane.py:26-30`).
- Production baseline (D0R): workspace `grw2-dd9d7af893a7f3c773909351`, candidate queue `grcq1-d93ebaf6878402e3be09e490`, cookie plane `government-revenue-data/*.json` (401 anon / 200 entitled), bearer plane `/api/government-revenue/*`.

## 2. Graph delta — defense21-v1

New file content at `data/government_revenue/recipient_entity_graph.json`:

- `graph_id: recipient-graph:reviewed:2026-08-19:defense21-v1` (defense20 is reserved by unmerged #5424 — do not reuse).
- `graph_known_at`/`graph_effective_at`: the actual construction stamp (2026-08-19TXX:00:00+00:00, set at build).
- Every defense19 row byte-identical (same `known_at`, `retrieved_at`, receipts, order semantics per `_graph_row_order_canonical`). A test pins this: for every defense19 row id, the defense21 row is deep-equal.
- Additions (BWXT only — GE gets nothing):
  - company `central:BWXT` (ticker BWXT), evidence: FY2025 10-K cover (`sec:1486957:0001486957-26-000007:bwxt-20251231.htm`), scope `public_company`.
  - legal entities: `legal:bwxt:bwx-technologies-inc` ("BWX Technologies, Inc.") + `legal:bwxt:bwxt-nuclear-operations-group-inc`, `legal:bwxt:bwxt-nuclear-energy-inc`, `legal:bwxt:nuclear-fuel-services-inc`, `legal:bwxt:bwxt-advanced-technologies-llc`, `legal:bwxt:bwxt-technical-services-group-inc` (canonical names exactly as Ex.21 prints them).
  - identifiers (namespace `sam_uei`): WJYVCPD5HKK7, C4L1VT236AA1, SMJQJGD5JEJ3, UMBKD2WKD8N5, PZDQCRZW7GJ3 → respective entities.
  - edges: `issuer-identity:bwxt:bwx-technologies-inc` (parent `central:BWXT`, relationship `issuer_legal_entity`) + five `ownership:bwxt:*` edges, `wholly_owned`, `economic_share 1.0` (Ex.21 prints "100" for each, FY2023+FY2024+FY2025).
  - evidence rows: real fetched-bytes receipts (sha256/byte_length/retrieved_at at fetch) for: FY2025 10-K cover; Ex.21 FY2025 `https://www.sec.gov/Archives/edgar/data/1486957/000148695726000007/exhibit211_123125x10k.htm`; one USAspending award record per UEI (award ids in §4); optionally the parent recipient profile `api.usaspending.gov/api/v2/recipient/bed8b6d9-3be2-efa0-2fa1-c2678095ea21-P/` (parent UEI CMT4S6G76QB5). Receipts must be produced through the proposer's receipt seam (allow-listed hosts, real `retrieved_at`), never hand-typed.
  - `valid_from` on BWXT rows: `2025-12-31T00:00:00+00:00` (Ex.21 as-of), matching the IRDM pattern.
- REFUSED from the graph (stay backlog + Atlas-unresolved): MMACD85DT5D5 (Ordnance Tennessee — live parent field says L3HARRIS on 2026-02-26 action vs 2025-11-10 Indenture guarantor: explicit conflict, display only), PM7HBL2KDX46 (NOG Technologies), URJ3CAC3MSH8 (Enrichment Operations) — Indenture guarantor status is affiliation, not an ownership percentage; asserting `wholly_owned/1.0` from it would repeat the GDLS overclaim defect. BWXT Government Group (Ex.21-proven) has zero observed award rows — nothing to attach.
- Validation: `load_recipient_entity_graph` clean; digest via `engine/government_revenue/entity_resolution._graph_fingerprint`; update the digest/count test pins the way #5424 did (mine its test diff; cherry-pick with `-x` only if the sibling's version is genuinely better).
- Rollback: revert the PR; defense19 stays untouched on main history. No silent bump.

## 3. Identity Atlas artifact — `government_revenue_identity_atlas.v1`

New deterministic projector `engine/government_revenue/identity_atlas.py` + build step in `scripts/build_government_revenue.py`, emitting `data/government_revenue/identity_atlas.json` (+ site twin via `--site-only`, cookie plane `government-revenue-data/identity_atlas.json`).

Inputs (read-only): reviewed graph (via `load_recipient_entity_graph`), SI snapshot parquet, `candidate_queue.json` mapping backlog, `dossiers.json` recipient observations, and a small curated PIT file `data/government_revenue/identity_atlas_curated.json` (committed, human-authored, evidence-URL-bearing) carrying: SPR listing termination (Boeing 8-K `https://www.sec.gov/Archives/edgar/data/12927/000162828025055825/ba-20251208.htm`, Spirit 8-K `https://www.sec.gov/Archives/edgar/data/1364885/000110465925119096/tm2532915d1_8k.htm`, effective 2025-12-08) and the GE separation boundary (GEHC spin 8-K acc 0001193125-23-001157 eff 2023-01-03; GEV spin 8-K acc 0001193125-24-084038 eff 2024-04-02; registrant remains "General Electric Company" CIK 40545, trade name GE Aerospace) and the BWXT unresolved-identifier notes (Indenture acc 0001104659-25-109152; Ordnance Tennessee L3Harris-parent conflict; A.O.T acquisition 2025-01-03 per FY2025 10-K narrative).

Output per issuer (pilots: IRDM, HII, LMT, GE, BWXT, SPR; other graph companies may project mechanically from the same code path, but the five pilot + SPR records are the acceptance surface):

- `public_security`: state ∈ `verified_live` (SI row, tape fields) / `listing_terminated` (curated evidence) / `not_in_si_universe`; SI facts quoted (first_date/last_date/asof).
- `legal_issuer`: canonical name + review state (from graph issuer_legal_entity edge) or `not_asserted`.
- `entities[]`: per graph entity — canonical_name, relationship, economic_share, valid_from/valid_to, known_at, verification_state, evidence (id/publisher/url/sha256), identifiers[] (value/namespace/state/evidence).
- `unresolved_identifiers[]`: ONLY curated, evidence-backed entries (the BWXT trio) — value, observed_name, state (`mapping_needed`/`evidence_conflict`), reason (plain words), evidence citations. Scope-observed identifiers with no reviewed path are NEVER named at issuer level (discovery scope is fuzzy association, not issuer proof — the GE scope contains unrelated third-party companies); they surface only as an aggregate count inside `gaps[]` (adjudicated 2026-08-18 after adversarial review finding B6).
- `issuer_attribution`: `reviewed` | `not_asserted`, with `attribution_reason`.
- `listing_events[]` (SPR), `separation_events[]` (GE) from curated file, each with evidence URL.
- `gaps[]`: plain-word unresolved statements (GE: "no reviewed exact recipient → legal entity → GE Aerospace path").
- Header: `contract`, `schema_version`, `generated_at`, `graph_id`, `graph_digest`, `si_asof`.

Laws: projector performs exact-ID joins and graph traversal ONLY — no name normalization joins, no LLM values, no event attribution (the Atlas carries identity paths, never event links, so it structurally cannot leak attribution onto unlinked events). Write path limited to `identity_atlas.json` — the projector must not open ledgers/workspace/candidates for writing. Display/context only: no authority fields, no rank/gate/size input.

Contract JSON schema at `contracts/government_revenue/government_revenue_identity_atlas.v1.schema.json`, validated in tests and (if the house pattern does so for other twins) in `scripts/check_government_revenue_projection.py`.

## 4. Frozen evidence receipts (research packets, 2026-08-18)

- IRDM: CIK 1418819; FY2025 10-K acc 0001418819-26-000009 filed 2026-02-12; Ex.21 `ex2111231202510k.htm` line "Iridium Government Services LLC — Delaware" (also FY2024 acc 0001628280-25-005302, FY2023 acc 0001418819-24-000008 → known-at bound 2024-02-15).
- HII: CIK 1501585; FY2025 10-K acc 0001501585-26-000006 filed 2026-02-05; Ex.21 `hii-ex211202510xk.htm`; "Huntington Ingalls Incorporated" (VA), "Ingalls Shipbuilding, Inc." (DE), "HII Mission Technologies Corp." (DE), "Newport News Shipbuilding and Dry Dock Company" (DE). Recipient string "HUNTINGTON INGALLS INDUSTRIES INC" = the registrant itself. FY2023 Ex.21 (acc 0001501585-24-000007) prints 100% ownership column.
- LMT: CIK 936468; FY2025 10-K acc 0001628280-26-004195 filed 2026-01-29; Ex.21 `ex21q42025.htm`: "Sikorsky Aircraft Corporation — Delaware" + omission clause verbatim: "In accordance with Item 601(b)(21) of Regulation S-K, the company has omitted from this Exhibit the names of additional subsidiaries which, considered in the aggregate or as a single subsidiary, do not constitute a significant subsidiary as defined in Rule 1-02(w) of Regulation S-X." All 14 graph UEIs observe recipient names "LOCKHEED MARTIN CORP/CORPORATION" in our own award data — no Sikorsky-identified recipient observed to date.
- GE: registrant "GENERAL ELECTRIC COMPANY", CIK 0000040545, `formerNames:[]`; GEHC spin eff 2023-01-03 (8-K acc 0001193125-23-001157); GEV spin eff 2024-04-02 (8-K acc 0001193125-24-084038, "General Electric Company now operates as GE Aerospace"); FY2025 10-K acc 0000040545-26-000008 cover still "GENERAL ELECTRIC COMPANY". ≥5 distinct UEIs display as "GENERAL ELECTRIC COMPANY" on USAspending (E3HYKKLT5ZT1, J1T1FEN3PWX6, DJY8WLTGF577, M2FYKG7HP723, C7X2U84J6GE1) — none SAM-verified to CIK 40545. Verdict: `mapping_needed`, `not_asserted`.
- Admission-standard note (recorded plainly after review finding N2): the UEI→legal-entity hop rests on punctuation/case-normalized equality of the registered recipient name across three independent sources (our award rows, live USAspending, SEC Ex.21) — e.g. "NUCLEAR FUEL SERVICES INC" ↔ "Nuclear Fuel Services, Inc." — a HUMAN admission call, corroborated by the USAspending parent-recipient plane, not an exact-document join. The projector itself performs no name joins. Parent-plane receipt: `api.usaspending.gov/api/v2/recipient/children/CMT4S6G76QB5/` lists all five admitted UEIs as children of BWX TECHNOLOGIES, INC. (fetched + receipted into the graph per review finding B4; the per-award `parent_recipient_uei` field is null in the five award receipts, and `parent_recipient_name` is "BWX TECHNOLOGIES, INC." on four of five — UMBKD2WKD8N5 self-parents on its only award, which is why the children-endpoint receipt is load-bearing for that chain).
- BWXT: CIK 1486957; FY2025 10-K acc 0001486957-26-000007 filed 2026-02-23; Ex.21 FY2025/FY2024 (acc 0001486957-25-000008)/FY2023 (acc 0001486957-24-000011) all list the five admitted entities at 100 (Delaware). Corroborating award records: WJYVCPD5HKK7 → `CONT_AWD_89233123FNA400535_8900_89233120DNA000025_8900`; C4L1VT236AA1 → `CONT_AWD_80MSFC17C0006...`; SMJQJGD5JEJ3 → `CONT_AWD_89233124CNA000371...`; PZDQCRZW7GJ3 → `CONT_AWD_HQ085926FF258...`; UMBKD2WKD8N5 → `CONT_AWD_N0017325C2403_9700_-NONE-_-NONE-`. Parent profile: "BWX TECHNOLOGIES, INC." UEI CMT4S6G76QB5, Lynchburg VA. Refused trio evidence: Indenture 8-K Ex.4.1 acc 0001104659-25-109152 (2025-11-10 guarantor list); Ordnance Tennessee most-recent action `CONT_AWD_W15QKN26F0107_9700_W15QKN23D0018_9700` parent "L3HARRIS TECHNOLOGIES, INC" SJULQDJ8NZU7; A.O.T acquisition completed 2025-01-03 (FY2025 10-K narrative).
- SPR: Boeing 8-K `ba-20251208.htm` (acc 0001628280-25-055825, CIK 12927) + Spirit 8-K `tm2532915d1_8k.htm` (acc 0001104659-25-119096); close 2025-12-08; absent from SI snapshot and from `config/delisted_symbols.yml`.

## 5. Hostile test matrix (all must exist and pass)

| # | Test | Enforceable form |
|---|---|---|
| 1 | SPR cannot appear live | Atlas SPR record `public_security.state == listing_terminated` and `issuer_attribution == not_asserted`; projector fail-closed test: curated file claiming a live state for a ticker absent from SI is refused; SPR absent from filmstrip/companies payload (existing golden test stays green) |
| 2 | GE not backdated across separation | GE record `not_asserted` + separation_events present; fixture test: an ownership interval spanning 2024-04-02 for a GE entity without explicit reviewed edge is never emitted; no GE rows in graph |
| 3 | IRDM clocks untouched | Projector writes only `identity_atlas.json` (write-path test); fixture P00032 row round-trips byte-identical through an atlas build; PR diff contains no `candidate_ledger.jsonl`/`workspace.json` change |
| 4 | HII sibling non-leak | Atlas output contains zero event references (structural: schema has no event/award fields); fixture: workspace event with empty `listed_company_impacts` + reviewed HII graph → event unchanged after build |
| 5 | Correction cannot overwrite interval | defense19 rows deep-equal inside defense21 (row-id-keyed test); admission test: mutated historical row (changed known_at) fails the byte-preservation pin |
| 6 | No unreviewed grc1-* | Existing gate `build_government_revenue_candidates.py:680` + test: GE/BWXT-unresolved atlas states produce no issuer-attributed candidate; candidate builder does not import the atlas module |
| 7 | LMT entities distinct | Atlas LMT: entities not merged; fixture: a Sikorsky-registered identifier (name "SIKORSKY AIRCRAFT CORPORATION") must land in `unresolved_identifiers`, never auto-attach to `legal:lmt:lockheed-martin-corp` |

## 6. Product (UI) requirements

Extend the company inspector on `government_revenue.html.j2` + `templates/government-revenue-dossiers.js` (dossierUI factory pattern, sibling section to Award history — same idiom as `renderSubawardLedger`/`renderIdvRelationships`). Fetch `government-revenue-data/identity_atlas.json` on the cookie plane with the same locked/teaser degradation as workspace.json. EN/ZH via existing `t()`/`tr()` mechanism. Glance tier per DESIGN_DOCTRINE + mockup idiom (`research/defense_intelligence/evidence/compositions/d2-company-dossier-irdm.html`): chips (Reviewed issuer path / Link pending / Identity unresolved / Listing terminated / Conflict on record), plain-word stance lines, technicals (UEIs, sha256, intervals) demoted to expandable receipt rows. Unresolved copy pattern (GE): "Public security: verified · Government recipient attribution: unresolved · Exact issuer attribution: not asserted — no reviewed exact recipient → legal entity → GE Aerospace path." No falsifier/refutation vocabulary. No third header family; no new page; no viewport hijack.

## 7. Authority + routing

Deterministic code owns joins/traversal/intervals/orphans. Human review (this session's adjudication, red-teamed by opus reviewer pre-merge) owns the BWXT admission and the three refusals. LLM-originated values are forbidden in graph/atlas rows: every UEI/CIK/date/share in §2/§4 traces to a fetched receipt. D2 display/context only.

## 8. Ship plan

One vertical PR off `a7cfd4be...` (branch `claude/defense-d2-identity-atlas`): graph delta + projector + curated file + contract + tests + UI + this spec + evidence dir updates. Opus adversarial review before merge (coverage gate: motivating exemplars = the five pilots + SPR). Merge-on-green armed, session owns to merged + live verification. Record: start SHA, merge SHA, production checkout, graph_id/digest before+after, bundle_id, candidate content_id, pilot outcomes, remaining mapping_needed, proof timestamp.
