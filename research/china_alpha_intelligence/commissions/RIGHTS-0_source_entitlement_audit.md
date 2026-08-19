# RIGHTS-0 — China source entitlement / rights audit (researcher commission)

**Program:** `WS:CHINA-ALPHA-INTELLIGENCE` wave `rights0` · **Route:** research (Sonnet `researcher`)
**Authority:** `research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md` §8 (audit-first law) + §13; `DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE`.
**Spawn note:** paste this file as the commission.

ROUTE: research

MISSION: Produce the rights/entitlement registry that gates every China data
acquisition in the program: for each priority source family, what we are
entitled to TODAY, what an upgrade costs, what the rights of persistence/
derived use are, and a VERIFIED/UNKNOWN verdict per cell. Audit before buying
(masterplan §8.1: "Buy/activate immediately IF NOT ALREADY OWNED — audit
first"). No capture, no purchase, no build.

WHY: P1 (institutional visit tape) is gated on this audit's verdict for the
visit source; every later family (fund holdings, announcements, named actors)
inherits the same registry. The estate's B0 census already established the
FF-1P2 STOP discipline: capture without a rights verdict is forbidden.

SCOPE:
1. **Tushare families** (client `collectors/tushare_client.py`, token env
   `TUSHARE_TOKEN` — name only, NEVER read or print its value). Consumed
   today (verified 2026-08-19): `stk_auction*`, `stk_mins`, `stk_premarket`,
   `cyq_perf`, `moneyflow_dc`, `daily_basic`, `margin_detail`, `forecast_vip`,
   `report_rc`, `broker_recommend`, chips-distribution. NOT consumed and
   P0-priority per the masterplan: `stk_surv` (机构调研 institutional
   visits/surveys — P1-critical), `fund_portfolio` (public-fund holdings),
   `anns_d` / full announcements, `hm_list` + `hm_detail` (named actors /
   游资), top-holder & holder-trade endpoints (`top10_holders`,
   `top10_floatholders`, `stk_holdertrade` — note repo already collects
   holder counts + holder-sale calendars from non-Tushare sources). For EACH:
   documented point/plan requirement (tushare.pro public docs), rate limits,
   history depth, PIT class (does the API expose announcement/publish date
   distinct from effective date?), and persistence/derived-use rights per the
   Tushare terms. Account-specific entitlement (our current point tier) is
   OPERATOR-ONLY knowledge — mark those cells UNKNOWN(operator) rather than
   probing the API with the token.
2. **Non-Tushare live sources already in production** — `collectors/china_irm.py`
   (SZSE 互动易), `collectors/china_einteraction.py` (SSE e互动),
   `collectors/china_lhb.py` + block trades (akshare/Eastmoney),
   `collectors/china_reports.py`, `collectors/china_analyst.py`,
   `collectors/china_filings.py` (cninfo metadata), holder-count/holder-sale
   collectors: state the source ToS/robots posture, whether our use is
   read-display-derive, and any redistribution limit that binds product
   display. Tag UNKNOWN where the ToS is unreadable.
3. **Primary official sources for the visit family**: SZSE/SSE investor-
   relations disclosure pages and cninfo 调研 records as the non-vendor
   fallback for P1 — availability, machine-readability, history depth, ToS.
4. **Entity-resolver vendors** (Qichacha / Tianyancha / equivalent): API
   persistence+cache rights and derived-use rights ONLY (the bake-off itself
   is a later wave; masterplan §8.2) — enough to know whether a bake-off is
   contractually possible.
5. Deliverable: `research/china_alpha_intelligence/RIGHTS_REGISTRY.md` — one
   table per family: {source, endpoint/page, access today (present/absent in
   repo), plan/point requirement, rate limit, history depth, PIT class,
   persistence rights, derived-use rights, product-display rights, verdict
   tag}. Plus a P1-specific verdict paragraph: which visit source the P1
   builder should use first and what remains operator-decidable.

OUT OF SCOPE: No API calls that spend entitlement or reveal the token's tier;
no scraping; no capture; no purchases; no ToS acceptance (prohibited action —
flag for operator); no new collectors; no edits outside
`research/china_alpha_intelligence/`.

QUESTIONS: (1) Can P1 run on Tushare `stk_surv` at a documented point tier, and
is our tier sufficient (or operator-unknown)? (2) Which of the seven priority
families are already effectively owned via live non-Tushare collectors?
(3) Which families carry redistribution/display restrictions that shape the
Hub/dossier surface? (4) Is a Qichacha/Tianyancha bake-off contractually
viable with persistence rights?

SOURCE STANDARD: Every claim tagged CODE VERIFIED (repo receipts, path:line) /
PRIMARY SOURCE VERIFIED (named public doc/ToS URL + date) / INFERRED /
UNKNOWN / UNKNOWN(operator). Chinese-language primary sources are first-class;
quote titles bilingually.

NOT DONE UNLESS: the registry covers all seven priority families + the four
resolver/ToS questions; every cell carries a tag; the P1 verdict paragraph
exists and names its blockers; `git status --short` shows only
`research/china_alpha_intelligence/` additions.

EVIDENCE REQUIRED: repo receipts for access-today claims; named URLs + access
dates for every rights claim; explicit UNKNOWN cells rather than guesses.

RETURN: STATUS / RESULT (the P1 verdict + top-line per-family verdicts) /
EVIDENCE / GAPS / DEVIATIONS.
