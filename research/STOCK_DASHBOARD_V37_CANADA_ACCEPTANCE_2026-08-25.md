# Stock Dashboard V3.7 — Canada production acceptance record (2026-08-25)

Session: Fable COO, `WS:PROPHET-HK-CA-REVAMP` presentation lane (V3.7
supersession per `DEC:V37-SUPERSEDES-V36-ACCEPTANCE`; Sol Skillpack pin
`Mastermind@51f9942733b86e550bb9169d2a43462bd28e774f`). Review law:
`research/SOL_CANADA_V37_ADVERSARIAL_REVIEW_GATE.md` +
`research/SOL_V37_REFERENCE_ARTIFACT_PRODUCTION_ADDENDUM.md` (both delivered
by Sol 2026-08-25 and committed verbatim in this PR — the V3.7 HTML mockup
was never used as semantic truth; no copy of it exists in-repo).

## Implementation identity

| Item | Value |
|---|---|
| PR | #6416 `claude/canada-v37-functional-completeness` |
| Reviewed content head | `ba0f9fb3de1a220f28af55d3a2f49b2ba2a48477` (final head `38c804cd19cc` = update-branch merge, owned files byte-identical) |
| Squash merge | `41efeba82b0193dd9090c600567e0b551ad8dd98` |
| CI | ci.yml run 32911400774 SUCCESS on the final head (an earlier pack-9 red was an inherited main-side Agent OS record defect, healed by Sol's #6425 `c5d6dcc1c2f6`; a frozen-merge-ref rerun could not clear it — update-branch minted the clean merge ref) |
| Files | `site/canada-stock-v36.js`, `tests/test_canada_v36_composer.py` only |
| Adversarial review | Opus reviewer, REQUEST_CHANGES round (3 MAJOR / 3 NONBLOCKING / 0 BLOCKER) fully adjudicated + repaired; second Sol-gate repair round (leadership silent-switch) repaired; verdict PASS on `ba0f9fb3` |

The four V3.7 changes: (1) V3.7 header/constitution stamp
`SOL-STOCK-DASH-V37-CA-FUNCTIONAL-COMPLETENESS-20260825`; (2) owner-native
Act-Now lane vocabulary in `collectSectors()` (verbatim
`Buy Now/立即买入 · In Favour/看好 · Bottoming Watch/洗盘观察 ·
Reduce / Avoid/减仓 / 回避` from `templates/canada.html.j2:854-996` —
replacing V3.6's invented labels); (3) `Evidence & Record` panel between
Leadership and Research tools that MOVES the owner's `.trk` chip+dialog
(`#trd-btn`/`#trd-dlg`, `_track_record_dlg.html.j2`) plus a
`Methodology → measurement.html` link; (4) group-action band in the Expand
Leadership modal partitioning sectors 1:1 by harvested lane, on the existing
modal activation delegation. Review repairs: days-in-state feature REMOVED
(producer value is a forward wait-window, not elapsed time — an unlabeled
`~3d` at glance tier misreads; reviewer MAJOR-3); leadership activation no
longer force-switches Top Picks→All (Sol gate law) — explicit bilingual
"No Top Picks in this group." zero state with a deliberate
`View All Candidates` control; two CSS fixes; test pins hardened against
four named mutation escapes (reviewer MAJOR-2).

## Production matrix (entitled Claude-in-Chrome session, www.mastermind-x.com, 2026-08-25)

VPS release identity first: `/opt/macro` HEAD `9cebc0fff5af` (descendant of
the merge; merge object present), `site/canada-stock-v36.js` on the VPS
carries all V3.7 markers.

| Cell | Result |
|---|---|
| §5 journey order header→Leading Now→Prophet→Leadership→Evidence & Record→Research tools | **PASS** (DOM section list verified) |
| Population projection (§6A) | **PASS** — Top Picks: 5 visible of 6, counter `5 shown · 6 on board`, 5 haloed; All: 6/6 |
| Grid XOR Table (§6B) | **PASS** both directions — grid `display:none` under Table, StockTable pane (21 controls) sole surface; population mode preserved across switch |
| Table workbench (§6C) | **PASS** — search 5→1 on "SAP", header sort reorders, same Top-Picks population in both presentations |
| Evidence & Record (§6D) | **PASS** — moved chip shows real server stats (`Track record · building · 364 calls logged`), dialog opens/closes with REAL ledger rows (LNR.TO/LUN.TO/SAP.TO, accruing, honest `—` for unmatured; `factordata/ca_track_ledger.json` 200 `private, no-store`), `Methodology →` resolves to the live Calibration Lab; section sits below Leadership, never above Prophet |
| Group-action in Expand Leadership (§6E) | **PASS** — four owner lanes verbatim EN+ZH with tone-coded headers, sectors partitioned (e.g. Materials: `LUN.TO · LIF.TO · 2`), quiet `— · 0` empties, rows activate the Prophet filter via the existing delegation |
| Sol-gate no-silent-switch law | **PASS, proven end-to-end** — activating `ca_rails_ind` (board member WSP.TO, zero Top Picks) while Top Picks active: population stayed `top`, 0 cards, exact zero state `No Top Picks in this group.该组别中暂无首选。` + `View All Candidates` button; deliberate click switched to All showing exactly WSP.TO. Sector with zero board members (Energy) correctly shows the generic empty message (switching would not help) |
| Leading Now | **PASS** — Theme Gold Miners · Sector Energy; no no-op prose |
| Terminal route | **PASS** — card anchor `canada_stock.html#SAP.TO` |
| Dark + Light desktop | **PASS** (screenshots; Evidence panel, chips, stances legible in both) |
| EN + ZH | **PASS** — all new copy bilingual and native under ZH (证据与往绩, 方法论 →, lane heads); stance-chip hue follows the site-wide ZH Asia action-color convention exactly as the owner's own legacy board does; price-change chips keep the composer's Western pin (V3.6-reviewed behavior, unchanged) |
| Console errors | **NONE** (entitled load, zero errors) |
| Horizontal overflow | **NONE** (scrollWidth == clientWidth) |
| Delivery/cache receipt | **PASS** — entitled `GET /canada-stock-v36.js?v=20260823` → 200, `Cache-Control: private, no-store`, body carries V3.7 markers (closes the review's MAJOR-1: no warm-cache stranding is possible on the entitled path) |
| 390 px | **Residual (bytes + local-real-browser proven)** — builder verified the exact shipped bytes at 390px in a local real browser (single column, `scrollWidth==clientWidth==390`); the `≤680px` fluid block plus new `≤680` rules (`.ca-v36-modal-lanes`→1 column, evidence re-pad) govern 680→390 with no fixed-width child; the OS ignores window resize on the automation tab's hidden Space, so an exact-390 PRODUCTION pixel pass remains unexecuted |
| Live quote paint | **Mechanism proven; paint residual** — `live/quotes.json` fresh at probe time (all 6 `.TO` symbols with `changePct`), 12 `.nb-px/.nb-chg[data-sym]` targets in the moved DOM, live.js re-queries per tick and ticks on visibilitychange; `document.hidden` was true for the automation tab all session so the final paint needs any human view during market hours (same residual class Sol accepted on V3.6.1) |

## Sol §16 acceptance interrogation (addendum-required answers)

1. **Top Picks membership owner:** the first-5 projection of the
   owner-published board order (`board_pos`, rendered card sequence from
   `canada_standouts` via `build_canada_library`), ratified in the reviewed
   V3.6 design (#6315) and revealed — never re-ranked — by the composer.
   No client score, no fixture boolean.
2. **Default candidate order owner:** the same server-rendered board order;
   the composer moves card nodes in DOM order and never sorts.
3. **Grid preserves that order without client-side reranking:** yes —
   `collectCards()` iterates the owner DOM; verified live (rank pills #1–#5
   in order, WSP.TO sixth).
4. **Fresh Only source:** StockTable's own `days_since_signal` owner field
   (0–2d window) — no browser clock, no runtime-inferred badge.
5. **Theme/sector filter identity:** theme = canonical basket/pulse `id`
   (e.g. `ca_rails_ind`) with membership from `baskets.json` members;
   sector = owner ETF slug from the Act-Now row's own href (`XEG`, …) with
   membership joined on the owner-published `sector` name field carried by
   the owner's table rows. Both sides of every join are owner-published
   values.
6. **Track Record route/owner:** the moved server-rendered
   `_track_record_dlg` chip+dialog; data `factordata/ca_track_ledger.json`
   written by `track_ledger.from_board_ledger_grade` off
   `board_ledger.scorecard("CA")`. No new ledger, no placeholder stats.
   Signal History has NO separate canonical route for Canada (grepped
   zero) — the per-call history table inside the same dialog IS the
   integrated history surface (INTEGRATE_COMPRESS), so no `Signal History →`
   link was fabricated. Methodology → `measurement.html` (live).
7. **Expanded Leadership producer states:** sector partition = the Act-Now
   board's own four-lane partition (`_action_board()` if/elif buckets → the
   template's four lanes), labels verbatim; theme stances = owner
   `reco_en/reco_zh` (`Accumulate/加仓`, `Hold/持有`, …). No generic
   tone-bucket ontology; nothing translated to fit a shared component.
8. **LIVE claims:** the header `● LIVE · <today>` chip and card price/change
   fields ride the proven Canada live quote plane (`live/quotes.json`);
   `Board <date>` is the separate board-vintage clock; both rendered
   distinctly (verified `Board Aug 24, 2026` vs `LIVE · Aug 25, 2026`).
9. **Every restored feature has a real consumer/destination:** Track Record
   dialog (real rows), Methodology (live page), lane rows (activate the real
   Prophet filter), zero-state button (real deliberate population switch),
   Thematic Baskets / Canada Macro links (live pages). Nothing is a
   `href="#"` or toast placeholder.
10. **Is any mockup fixture treated as semantic truth:** no — no copy of the
    V3.7 reference exists in-repo; every count, label, stance, membership,
    price, and stat above binds to a named owner artifact.

## Classification

**Canada Stock Dashboard V3.7 is `PROVEN_LIVE` as of 2026-08-25** — merged
exact reviewed content, production deployment descends from the merge,
signed-in real production browser proof executed on production bytes, the
visual/interaction matrix passing, and no product-authority regression
observed (nothing moved ranking, signal, lifecycle, availability,
entitlement, quote, or persistence semantics). Two enumerated residuals
carry forward, both mechanism/bytes-proven as tabled above: the exact-390
production pixel pass and the final live-paint observation.

Per `research/SOL_HK_V37_FOLLOWER_ARCHITECTURE.md`, this promotion releases
the HK V3.7 follower wave: feature-disposition census FIRST, then
implementation under the frozen HK architecture (no fabricated LIVE, Featured
= selection not action, Southbound integrate/compress ladder).
