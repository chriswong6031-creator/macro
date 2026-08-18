# B0 — Collision and adoption map

**Lane:** GROK-B0 · **Date:** 2026-08-18 · **Pin:** `3d12412e561e` (PASS-0 snapshot was `47aaa6036846`; delta-checked open PRs this session)
**Parent:** PASS-0 §1-B, §3, §4, §6 rider for B0.

This map is advisory. It does not grant a lane and it does not freeze contracts.

---

## 1. Adopt these owners (never rebuild)

| Need | Adopt | Never |
|---|---|---|
| Universal 13F evidence / amendment lineage / public census | `engine/institutional_census/*`, `config/institutional_13f.yml`, `contracts/institutional_13f_*.json`, workflows `smart-money-13f-census.yml`, `smart-money-13f-bulk-reconcile.yml`, `smart-money-13f-r2-conformance.yml` | A second 13F store; git directories of 8k filers; **Quiver `sec13f_changes` as canonical** (that tape still exists — see §2a) |
| Featured manager desk | `config.yml::smart_money`, `collectors/edgar_13f.py`, `engine/smart_money.py`, `scripts/build_smart_money.py`, `smart-money-filings.yml` | Expanding the 51-CIK roster to the long tail |
| Per-ticker 13F context | `engine/company_institutional_context/` (`AUTHORITY=context_only`) | A second sidecar |
| Daily ETF / ARK holdings + ΔQ proxy | `collectors/holdings.py`, `collectors/etf_holdings.py`, `engine/holdings_signals.py`, `engine/etf_*`, `research/ETF_DATA_SOURCES.md` | A third SO proxy; iShares headless; Vanguard scrape |
| Unfused ownership events | `engine/ownership_event_wire.py` + beneficial-ownership + special-sits 13D | Fused sponsorship score |
| Borrow / HTB | `collectors/ibkr_borrow.py` | A second borrow vendor as truth |
| PIT receipts / clocks | Census `accepted_at` / `first_seen_at`; desk `acceptance_available_date`; Quiver `_first_seen` | A fifth PIT vocabulary (PASS-0 §3) |
| Identity | `engine/stock_identity/`, theme-graph identity, `share_class_equiv.yml` | A B-local company-security plane |
| Ranking | None. 13F is context_only. If a family is ever tested, it enters `engine/us_prophet_fusion.py` via Eval OS | Any B ranker; `DNR:KILL-OWNERSHIP-BREAKAWAY` |
| Artifact governance | Register any *new* cross-engine artifact in `config/synapse.yml` | A B registry |
| Bulk issuer filings | **Stopped.** FF-1P2 #5898 / `DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE` | Routing 13F history through `submissions.zip` |

---

## 2. Open PR / workstream collisions (checked 2026-08-18)

| ID | State | Collision with B | Rule for B |
|---|---|---|---|
| **#5910** PASS-0 + `WS:ALPHA-INTELLIGENCE-INTEGRATION` | OPEN | Creates `research/alpha_intelligence/`. This census lands in `censuses/B0/` under that tree — **additive, no file overlap** | Cite PASS-0; do not rewrite the ownership matrix |
| **#5822** China institutional intelligence alpha masterplan | OPEN draft | Manager ontology + "institutional" vocabulary overlap | **Reconcile before any B ontology freeze** (PASS-0). Reuse patterns; do not copy LHB |
| **#5898** FF-1P2 STOP (`submissions.zip` 1.45 GiB) | OPEN | Bulk-filings substrate | **No B recommendation may route around it** |
| **#5889** FIF-1R3 | OPEN, DO NOT MERGE | Fundamentals truth | No A/B/C coupling until Sol rules |
| **#5894** GMI→Data OS identity bridge | merge-blocked (PASS-0) | Identity / theme-graph | B does not touch `engine/theme_graph/*` |
| **#5902 / #5903** PIT replay + era pin | armed (PASS-0; re-check at c0) | Mesh replay, not 13F storage | Adopt if building as-of replay over 13F receipts |
| **#5850 / #5854 / #5855 / #5858** 13F census cadence + atom completeness | MERGED 2026-08-18 | Current live census contract | Do not re-derive atom page-size / 700-filing budget |
| `WS:FUNDAMENTAL-FORENSICS` | blocked | Same STOP | No shared bulk client |
| `WS:FINANCIAL-INTELLIGENCE-FABRIC` | Sol review | Adjacent "financial intelligence" name | Different object; do not merge stores |
| `WS:EARNINGS-INTELLIGENCE-OS` | active, E2 frozen | Not a 13F owner | G lane only |
| `institutional-sector-intelligence` | subprogram of sector-rotation | Sector evidence, not manager identity | Do not park B ontology there |

No dedicated `WS` for US 13F / smart-money / institutional-census exists. That is acceptable: PASS-0 says do not mint a B workstream until a contract wave actually starts (K2, after this census + #5822).

### 2a. In-tree duplicate 13F tape (not a PR — a standing collision)

`engine/altdata_models.py` still defines `CHANNEL_WEIGHTS["smart_money_13f"] = 0.85` and `["13f_add"] = 0.40`, fed by Quiver `sec13f_changes` via `inst_13f_changes()` which filters on **`ReportPeriod` (quarter-end)**. The marquee list includes Citadel and Renaissance (SM2-R6 excluded names). `OWNERSHIP_SIGNALS_CASE_STUDY_REVIEW.md` (2026-06-21) already called this the higher-priority look-ahead. B must **not** grow this kernel. A later owner (altdata / Eval OS) should either retire it or re-clock it to `accepted_at` from the official census. That retirement is **not** this census's build.

---

## 3. Capability-adoption for the B missing delta

PASS-0 named the B gap as: manager-complex ontology · ΔQ_active · behavior casebook · ETF-holdings history · linkage to expert-value learning (J).

| Gap | This census | Next lawful act | Still forbidden |
|---|---|---|---|
| Ontology | `B0_MANAGER_COMPLEX_DRAFT.md` (data-only) | K2 contract after #5822 reconcile | Auto-promote to featured desk; scoring weights |
| ΔQ_active | `B0_INTENT_NORMALIZATION_INPUT_MATRIX.md` — formula **already shipped** with a proxy S; 20 failure modes | Optional true-S capture (ProShares NAV / N-PORT / ARK SO) after rights | Applying the ETF formula to 13F; missing=zero |
| Casebook | `B0_MANAGER_BEHAVIOR_CASEBOOK.md` (57 labeled rows; few accession-level) | Fill accessions from census R2 on a full checkout | Invented share counts; LLM track records |
| ETF history | Exists for dated sponsors; current-only is perishable | Verify nightly completeness; optional ProShares | iShares headless |
| Link to J | Not designed here | K6 inside Eval OS + Stock Identity, prospective only | Retrospective skill scoring; outcome audition |

---

## 4. File-touch map (so a future builder does not wander)

Safe to *read* anywhere. Safe to *propose a later PR* only on:

- `research/alpha_intelligence/**` (this program's docs)
- possibly additive flags on `config.yml` etf/holdings **after** rights (not now)
- never on `engine/us_prophet_fusion.py`, `engine/theme_graph/**`, fundamentals bulk paths, or CI pack YAML from a B lane

---

## 5. Name collisions to keep distinct in prose

| Phrase | Means in this repo | Does not mean |
|---|---|---|
| "institutional census" | `engine/institutional_census` 13F plane | This B0 markdown census |
| "institutional roadmap" | `research/INSTITUTIONAL_ROADMAP.md` (factor/survivorship grade) | Manager intelligence |
| "institutional sector intelligence" | Sector-rotation subprogram | 13F desk |
| "company institutional context" | Per-ticker 13F sidecar | Universal census |
| "smart money" | Featured ~51 CIK desk | The 8k-filer universe |
| "China institutional" | #5822 + CN holder/LHB/southbound | US 13F |
