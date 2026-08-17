# PROPHET US V4 — EXPERIENCE REFERENCE COMPOSITIONS (V4-0A)

**Status:** reference compositions for wave handoffs (V4-B5, B7, E2). NOT an implementation and NOT a visual design — visual language is chosen at build time by the design lane (`designer`/main loop) under `docs/DESIGN_DOCTRINE.md`, `research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md` (archetype/specimen/tokens), and the frontend-design skill. On conflict, the doctrine wins. The design-system update that shipped the week of 2026-08-10 is the visual substrate for all V4 surfaces.
**Composition source:** masterplan §9 (lanes), §17 (views/anatomy). This doc adds only V4-0A composition rulings + the current-page anatomy deltas.

## 1. Product shell — one Prophet, six linked views (§17.1)

1. **Action Desk** — availability-first lanes for "what can I do right now".
2. **Early Radar** — emergence-first view of what is beginning.
3. **All Candidates** — the complete, searchable, sortable, filterable table. Nothing is invisible.
4. **Themes & Propagation** — theme/micro-theme acceleration and peer read-through.
5. **Track Record** — cohort-honest performance (denominators named per cohort).
6. **Health & Receipts** — operators only: settlement chain, source freshness, correction log.

The Radar engine remains its own producing workstream; Prophet embeds/links its projection without duplicating the expert store.

## 2. Lane composition (frozen)

Primary lanes derive from `availability_state` only: **Entry Open Now · Approaching Entry · Early Radar · Wait for Pullback · Ran — Don't Chase · Invalidated/Expired · All Candidates**.

- **"Live Now" and "Setting Up" are retired labels.** Green appears in exactly one place — a row whose server-published `availability_state == ENTRY_OPEN` — and nowhere else. No green accents on maturity, scores, or themes.
- Maturity renders as a paired chip beside availability (`EARLY · ENTRY OPEN`, `CONFIRMED · RAN`), never as the lane key.
- The featured shelf is a bounded projection of lane+priority; every card links back to its complete-row context in All Candidates.
- Empty lanes are honest states with plain-word explanations, not hidden sections.

## 3. Board header (always present, §17.2)

Market session · quote/evaluation time · source session · freshness status (current/degraded/stale/unavailable) · episode counts (active / new / entry-open / approaching / wait-pullback+ran) · evidence-coverage summary · board definition · correction banner when applicable. A stale board announces itself before it shows a single card.

## 4. Card anatomy (§17.3)

Identity (ticker/company, sector/subsector, top themes, asset type) → Availability (price, zone, distance, invalidation, risk, state + blockers) → Timing (earliest event time/price, latest event, move since first event, 1D/4H/2D/3D timeline, maturity) → Intelligence (V4 priority + coverage band, top positive families, top risks, theme acceleration, catalyst/earnings state) → Provenance (source clock, provisional/corrected markers, nulls) → Actions (dossier, watch, pass, reject, promote, signal analysis).

Glance-tier language rules bind (doctrine): plain-word stance under hard word budgets; no internal state/study names, no untranslated stats, no raw slugs; technicals demoted to hover/detail; every panel answers "so what do I do", including the honest "watch — don't chase". Falsifier/refutation vocabulary never appears front-facing; user surfaces show windows, watch-conditions, and "read being updated" chips.

## 5. Drawer/dossier (§17.4)

Answers, in order: why it entered the candidate plane · why the trade is available/blocked (with exact blockers) · what happened since first event · which themes/peers are moving · what intelligence is measured · **what is missing (named nulls)** · what would invalidate · similar episodes · what the Chairman previously did.

## 6. All Candidates table (§17.5)

Search; multi-column sort; saved views; filters by lane/expert/theme/sector/asset type/score/coverage/freshness; complete row count displayed; virtualized rendering for large counts; export bounded by rights and auth; **no client-only hidden authority** — the table renders server rows byte-for-byte.

## 7. Alerts (§17.6)

Transition-driven (new early event, APPROACHING_ENTRY, ENTRY_OPEN, WAIT_PULLBACK, re-entry, invalidation, material priority/theme change, stale/degraded source), computed per symbol/watchlist independently of featured top-K.

## 8. Acceptance surface (binding on B5/B7/E2 handoffs, §17.7)

Desktop wide, laptop, tablet, 390px mobile; no horizontal overflow; keyboard + screen-reader basics; explicit stale/degraded/empty/partial/correction states; large-candidate-count performance proof; EN/ZH bilingual per house law (no translated text in `title=` attributes). Production browser proof with real auth — reference mockups are never "shipped".

## 9. Current-page anatomy (what V4 replaces)

Full receipts: `CURRENT_STATE_2026-08-17.md` §8. In brief: `site/us_stocks.html` renders lanes `live/setting_up/ran/basing/blocked` from `engine/us_board_rank.py` stages, where `buy_soon` counts as "Live now" (`:429`) while the bridge refuses it and the card's own verb chip renders "Near" — plus two additional lane-derived stage derivations (table `ENTRY/RIPENING/RAN_LATE`; int-stage rail) that never read entry timing. Featured cap is disclosed (12, ≤4/sector); the table view is the closest all-candidates surface but excludes watch/leaders/laggards/ran; tier gating is a DOM overlay with the full board in page source; TURN WATCH engine copy has zero template consumers.

## 10. MP-1 is the executed base (binding)

`research/migration_packets/MP-1-prophet-board.md` (design-authority-ratified 2026-08-13; spawn gates G-A/G-B/G-C all satisfied at pin) is the specification V4-B5/E2 execute for this page — the 7-cell plan-lifecycle ladder (`watch/ready/entered/delivering/overtime/invalidated/resolved` on the `.mx-ladder` primitive), retirement of the RIPENING chip and `_STAGE_BY_LANE` duplicate, and the population re-source to the plan book. Reconciliation ruling (freeze §12.4): the ladder is the plan-lifecycle presentation; `availability_state` is the board-lane truth; the B5 handoff maps the two with design-authority sign-off, re-checks MP-1's population re-source against `DNR:KILL-PROPHET-POP-MERGE`, and confirms the frozen R3/R4 reference crops (`mockups/refs/institutionalize/us_stocks/`) are still current. MP-1 §9's banned vocabulary (no "stage/阶段" user-facing; no falsifier/refuted/证伪; no blended confidence numbers) binds every V4 surface, alongside `DNR:KILL-STAGE-WIN-GATE` (lifecycle cells are display-tier, never win-rate authority).
