# CN-G0 — Adoption and collision map (China)

**Lane id:** `CN-G0`. **Not** US GROK-G0 (`research/alpha_intelligence/censuses/G0/` on PR #5953).
**Lane:** GROK-CN-G0 · **Date:** 2026-08-19 · **Pin:** `6353b77f5aaa`
**Parent:** China Alpha Intelligence program. US c0g / GROK-G0 is a sibling wave and a **path collision** if this packet stays under `censuses/G0/`.

---

## 1. Adopt (never rebuild)

| Need | Adopt | Never |
|---|---|---|
| Event / claim / document product truth | `WS:EARNINGS-INTELLIGENCE-OS`, `event_workspace.v1`, `company_event.v1`, `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP` | `china_corporate_event.v1` as a second canonical event object |
| Event lifecycle | Existing `EVENT_STATES` (`scheduled` / `rescheduled` / `completed_partial` / `complete` / `corrected`) | A China-only state machine |
| Issuer identity | `engine/stock_identity/` + Data OS listing identity; Earnings OS `company_identity.v1` **extended**, not forked | `cik:` ids for A-shares; ticker-as-issuer |
| CN disclosure schedule | `collectors/china_earnings.py` | A second 预约 collector |
| 预告 / 快报 | `collectors/china_preannounce.py` both parquets | Re-scrape Eastmoney inside Earnings OS |
| Announcement index | `collectors/china_filings.py` | Revive `china_inquiry.py`; fetch PDF bodies |
| On-record Q&A | `china_irm` + `china_einteraction` | A US transcript port as if A-shares had calls |
| Expectations tape | `china_reports` + `china_analyst` + gated `tushare_forecast` | Collapse them into one "consensus score" |
| Context desk | `china_special_sits.v1` | Fold Special Situations into the Terminal CI workspace |
| Salience ledger | QLedger family `cn_special_sits` | A second forward grader for inquiry/unlock |
| Flow / attention | LHB, Connect, QVIX, 千股千评 | Treat as document restatements |
| Macro calendar | `engine/china_event_calendar.py` | Confuse PBoC/NBS prints with issuer events |
| PIT / Eval | QLedger evidence clock; Eval OS workstreams | China-only skill scoreboard |
| Ranking | China Prophet / `china_intel_interest` existing seam only, via gauntlet | G-lane scores, fused composites (`DNR:KILL-FUSED-COMPOSITE`) |

---

## 2. Collision table

| Collision | State at pin | Rule for G |
|---|---|---|
| **US GROK-G0 directory** | PR #5953 owns `research/alpha_intelligence/censuses/G0/` (US estate + c0g adjudication). | **This packet lives only in `censuses/CN-G0/`.** Do not merge the two directories. |
| **E2 frozen scope** | `WS:EARNINGS-INTELLIGENCE-OS` next_action is AAPL FY2026 Q3 Terminal + dossier glance. Do not broaden into E3+. | **Untouchable.** Any China adapter is a later E-wave. |
| **`company_id = cik:`** | `identity.py` / `events.py` / E0 freeze § issuer rule | A China adapter is a **contract amendment**, not a silent ticker pad. Dual-class law still applies (one issuer, many listings). |
| **#5822 China institutional alpha masterplan** | OPEN research PR. Proposes `china_corporate_event.v1` and a full announcement corpus. | Reconcile *fields* into Earnings OS. Refuse a second store. Same standing as PASS-0 collision #4 for lane B. |
| **#5933 C0 adjudication** | OPEN. Five censuses accepted; G0 outstanding; `c0g` wave added. | This packet **is** the G0 return. Do not open a second G0. |
| **Special Situations vs event workspace** | Live page vs US-only workspace | Desk stays. Workspace, when it exists, may *cite* the desk; it must not replace it. |
| **Two 预告 tapes** | Eastmoney keyless + Tushare gated + derived `guidance_score` | One primary document source per workspace. Score stays in `china_validation`, never in the workspace facts. |
| **Q&A shard coverage** | ≤40 names/night per exchange platform | Workspace must print typed absence, not imply full-universe Q&A. |
| **Northbound net retirement** | Permanent after 2024-08-16 | Do not "repair" into a reaction slot. |
| **`DNR:KILL-CN-SUPPLY-ABSORPTION`** | Closed construction | No post-event price-absorption score. |
| **`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`** | STOP-SHIP | CN-G0 does not touch limit-alpha artifacts. |
| **CN-limit-alpha / china_alpha pick board** | Separate programs | Out of G scope. |
| **Prophet / `china_board_rank` / Hub circularity** | #5822 architecture ruling: preserve DataOS, GMI, board-independent `china_intel_interest`; do not feed Hub/Board terms into Prophet | G produces no rank family. |
| **Theme-graph / #5894** | PASS-0 wait for D; may have landed since pin — do not touch | G does not edit `engine/theme_graph/*`. |
| **FIF / FF STOP** | #5889 / #5898 | No US bulk-filings coupling. Irrelevant to CNInfo metadata except as a reminder not to invent a "full corpus" capture in this lane. |

---

## 3. Capability-adoption vs #5822 P0 families

| #5822 / #5953 family | CN-G0 disposition |
|---|---|
| 7.1 Institutional visits (`stk_surv`) | **Not G.** No in-tree collector found this session (UNKNOWN if a stub exists under another name). B-lane / China P0. |
| 7.2 Expectations Intelligence | **Partial G.** Reports tape + analyst snapshot + Tushare exist; not joined to an event. |
| 7.3 Ownership & alignment | **Not G.** B0 already flagged CN holders/LHB/southbound as prior art. |
| 7.4 Corporate Communication / Q&A | **G input.** Collectors exist; no product; no bind to fiscal event. |
| 7.5 Corporate Event Intelligence | **G core.** Metadata corpus exists; ontology does not. Owner = Earnings OS. |
| 7.6 Named market actors | **Not G.** LHB stays China-system. |
| §§9–11 demand / capacity / vertical lobes | **Not G.** |

---

## 4. Forbidden duplicates (do_not_redo)

- A second earnings store or China event warehouse.
- An event clock outside `event_workspace.v1` / `company_event.v1` lineage.
- An independent G build lane or "China Earnings OS".
- Any E2 markup, glance, or publisher change.
- Prophet / score / fused opportunity number.
- PDF-body scrape of CNInfo or Eastmoney 研报 from this census.
- Porting LHB mechanics onto US 13F or onto event truth (B0 already said the first half).
