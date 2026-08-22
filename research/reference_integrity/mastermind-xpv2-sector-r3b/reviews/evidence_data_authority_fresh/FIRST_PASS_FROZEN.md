# XPV2-SC-R3B — Data/Authority Critic — FIRST-PASS FREEZE
Frozen at: 2026-08-22T13:05:05Z
Quarantined material read so far: NONE except breach B-1 (see BREACH_LOG.md — one row of
QA_ATTACK_REPORT.md, immaterial: the finding it touches was already independently derived).

## First-pass verdict
BLOCK — 2 HIGH findings (DAC-001, DAC-002) are producer/authority regressions vs production
on the Overview hero. Remaining findings are MEDIUM/LOW or inherited conditions.

## Findings (frozen IDs)
DAC-001 HIGH   Hero drops the LIVE position-sizing statement (theme_intel.regime_sizing
               active, gross_scalar 0.81 -> production renders "positions sized to 81%").
               Candidate: 0 occurrences of hero-sizing/pulse-size/positions sized/仓位缩.
DAC-002 HIGH   Hero drops the methodology receipt chip and its governed caveat
               ("Shape read only — not a forecast.") while KEEPING the succession
               assertion it governs. Candidate: 0 occurrences of "How this works",
               "Trailing-momentum", "skips the most recent"; the sole "not a forecast"
               string in the file is inside embedded fixture JSON, not rendered copy.
DAC-003 MEDIUM theme_context.migration.note_en ("Money is moving into Software and out of
               Semiconductors.") producer fact dropped from the hero.
DAC-004 MEDIUM allocation.html / "Open the playbook →" working destination absent
               (0 occurrences). Ledger #86 RETAIN; R3A forbids implicit deletion.
DAC-005 MEDIUM S&P coverage sentence asserts 48 thin rows are "listed in the table" when
               they are gate-DROPPED and absent (table = 65 rows, 113-65 = 48).
               Inherited verbatim from subsectors.js:221-222; A5 diagnosed it, ledger #65
               RETAINed the contradicting wording. CONDITION, not BLOCK.
DAC-006 LOW-MED Hero handoff meta enrichment (20d/5d rel perf on out/in cards) and
               "· 49 themes · 15 categories" count dropped.
DAC-007 LOW    Same producer field theme_intel.themes[].score labeled "Score/评分" on
               Overview and "Strength/强度" on Map (9/9 values identical).

## Notes (NOT candidate defects)
N1 Cross-artifact contradiction inherited: "Buy now" Non-AI Software trace -> "Conviction 25
   Reduce"; "Almost ready" Financials -> "21 Reduce"; several avoid-lane rows -> "Constructive".
N2 REF.parseJSON NaN->null coercion; the 2 bare NaN tokens are factor_z, never rendered here.
N3 rvxData null coercions (score==null?50, rank||999) inherited verbatim; 0 nulls in fixture.
N4 Reference comment repeats A5's inaccurate "basket_confluence carries only n_baskets"
   (also carries n_high/n_med/n_low_conf/thin_share); behaviour correct (guard on n_gateable).
N5 thin_share = n_low_conf/listed, NOT gate-dropped share (Nasdaq n_thin=0, thin_share=0.667).
   Candidate never renders it — correct.
N6 universe field absent from all confluence rows -> ledger #78 detector clause unsatisfiable.
N7 forming class absent from all four universes -> fold is code-live, render-unevaluable.
N8 ai_watch null in fixture -> A8 labeling verified in CODE only.
N9 Map drops production's buyable flag / "buy" filter — deliberate de-amplification.

## Verified clean
Artifact chain: candidate sha256 19553267...=frozen=main; BUILD_MANIFEST a7b9ae8a...;
18/18 R3A receipts recompute; 23/23 manifest inputs match; 22/22 embedded blobs
byte-identical; 5/5 supplements byte-identical to site/ at capture epoch 4c55fe43;
si_workspace.js identical at epoch/frozen/main.
Authority: 6 keys->5 columns; hold+avoid concat never re-sorted; counts off FULL board
(4/5/5/3/27); gate arithmetic reproduces split_actnow exactly (1+2+2+0+24=29=locked);
ledger #26 R2 invariant holds; Bottoming Watch signal/timing_state never read + watch-only
copy + truthful "All 3 rows" aggregate; A2 Moving binds exactly 5 artifacts; A3 reco
de-amplified ("Noted" header + extra caveat); A4 tab order; A5 no fabricated Baskets
disclosure; A6 no invented staleness threshold, no correction UI; A8 only ai_watch labeled;
Confluence class read from g['class'], distribution 1/16/21/18/9 = producer exactly;
all 12 client sorts production-owned with verbatim keys; hydrate() validates schema+page.

## POST_FREEZE_DRIFT
Only config.yml notify.site_url (Pages mirror -> production origin, DEC:B1-MACRO-PRIVATE-CUTOVER).
No sector_central schema/route/authority/access/producer/capability change.
Candidate contains 0 github.io references. Does NOT invalidate migration law.
