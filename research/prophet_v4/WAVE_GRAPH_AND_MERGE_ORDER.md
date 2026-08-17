# PROPHET US V4 — WAVE GRAPH AND MERGE ORDER (V4-0A)

**Pinned execution main:** `fc0557bb0873` (2026-08-17) · **Program:** `WS:PROPHET-US-V4-RECOVERY`
**Source of wave definitions:** masterplan §21 (missions/acceptance live there; this doc owns dependencies, merge order, and path ownership).
**Numbering is the V4 integration program's own** — it never renames sibling workstream wave IDs (Radar W0–W9, Fusion PR-3x, GMI W3x, EIOS E0–E2 keep their identities).

## 0. Standing merge-order law

1. **One independently useful capability per PR** (law 23). A wave may span multiple PRs; a PR never spans waves.
2. **No two lanes edit the same canonical authority without a written ruling appended to this file** (masterplan §20.3). Path ownership below is that ruling's baseline.
3. **Sibling-workstream boundaries are hard:** Conditional Fusion PR-3B→3D files are out of bounds for every V4 wave (V4-E1 rebases onto the *accepted* registry afterward); Live Entry Radar remains the expert-event producer; GMI owns the graph; EIOS owns earnings; Stock Identity owns identity epochs; the availability workstream's rescue plane is reconciled with, never duplicated.
4. Every wave handoff uses the masterplan §28 format with acceptance gates inline at §0 of the handoff (fleet spawn-handoff law).
5. A wave is DONE only at merged + production-verified (fleet ship-loop law); "built, staged, unproven" states must be recorded as such in `WS-PROPHET-US-V4-RECOVERY.md`.

## 1. Critical paths (frozen from masterplan §22)

```
Product:  A1 → A2/A3 → B1 → B3 → B4 → B5 → B6/B7 → C1/C2 → E1 → E2
Graph:    D1 → D2 → D3 → D4 → D5 → E1 → E3/E4 → E5 → E6
Earnings: EIOS E0/E1/E2 (external) → D6
Fusion:   PR-3B → 3D (external) → E1 consumes accepted registry
```

V4 must not wait for every lobe: E1 may launch with technical/structure + sector/industry context + current theme evidence + explicit `ACCRUING`/null families (§22.1).

```mermaid
graph LR
  subgraph P0[Phase 0]
    A0A[V4-0A freeze] --> A0B[V4-0B AgentOS reconcile]
  end
  subgraph P1[Phase 1 truth]
    A1[A1 settlement recovery] --> A2[A2 settlement manifest]
    A1 --> A3[A3 atomic publication]
    A2 --> A4[A4 fire-drill week]
    A3 --> A4
  end
  subgraph P2[Phase 2 candidate/entry truth]
    B1[B1 episode registry] --> B2[B2 correction hardening]
    B1 --> B3[B3 orthogonal lifecycle]
    B3 --> B4[B4 buyability firewall]
    B2 --> B4
    B3 --> B5[B5 early desk MVP]
    B4 --> B5
    B2 --> B6[B6 radar observation-only]
    B6 --> B7[B7 radar production UI]
  end
  subgraph P3[Phase 3 evaluation]
    B1 --> C1[C1 cohort ledger]
    C1 --> C2[C2 V3 legacy shadow]
    B5 --> C3[C3 operator instrumentation]
  end
  subgraph P4[Phase 4 graph/intelligence]
    D1[D1 theme census] --> D2[D2 ontology+probation] --> D3[D3 ThemeState v1] --> D4[D4 transmission] --> D5[D5 intel vector contract]
    D5 --> D6[D6 earnings adapter]
    D5 --> D7[D7 alt-data adapters]
  end
  subgraph P5[Phase 5 rank/cutover]
    B4 --> E1[E1 explainable priority]
    D5 --> E1
    C1 --> E1
    E1 --> E2[E2 V4 primary experience]
    B7 --> E2
    C2 --> E2
    A4 --> E2
    C1 --> E3[E3 listwise challenger]
    E1 --> E3
    E3 --> E4[E4 router/multi-head]
    D4 --> E5[E5 temporal graph challenger]
    E3 --> E5
    E3 --> E6[E6 promotion gauntlet]
    E4 --> E6
    E5 --> E6
  end
  A0B --> A1
  A4 -.-> B1
```

(Dashed edge: B1 may start once A1–A3 are merged; A4's fire-drill week runs concurrently and only gates E2.)

## 2. The 29 waves

Legend: **Deps** = must be merged first (external deps in *italics*). **Paths** = files/dirs the wave owns while active. Missions and acceptance criteria: masterplan §21 (not restated).

### Phase 0 — freeze and reconcile
| Wave | Deps | Owned paths | Status |
|---|---|---|---|
| **V4-0A** estate archaeology + architecture freeze | — | `research/prophet_v4/**`, `agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md` | **THIS PR** |
| **V4-0B** AgentOS reconciliation (records only) | 0A | `agentos/workstreams/{WS-PROPHET-US-AVAILABILITY,WS-LIVE-ENTRY-RADAR,WS-GMI-THEME-GRAPH,WS-EARNINGS-INTELLIGENCE-OS,WS-PROPHET-CONDITIONAL-FUSION,WS-STOCK-IDENTITY}.md` status fields + handoffs | NOT STARTED |

### Phase 1 — truth and availability (Lane A)
| Wave | Deps | Owned paths | Status |
|---|---|---|---|
| **V4-A1** Aug-14 + current-session settlement recovery | 0A | `daily.yml` Prophet steps, `scripts/build_prophet.py` checkpoint plumbing, `scripts/prophet_rescue.py`/`check_nightly_liveness.py` only if the root cause lives there (`V4_A1_AVAILABILITY_RECOVERY_HANDOFF.md` §3) | NEXT (handoff in this packet) |
| **V4-A2** canonical settlement manifest | A1 | new manifest module + schema (minted at handoff); `scripts/prophet_rescue.py` + `scripts/check_nightly_liveness.py` read paths | NOT STARTED |
| **V4-A3** atomic publication + split-brain fence | A1 | `daily.yml` publish/upload steps, `scripts/ci/push_retry.sh` interface, bundle-ID stamping in `scripts/build_prophet.py` | NOT STARTED |
| **V4-A4** availability fire-drill week | A2, A3 | drill scripts + receipts only | NOT STARTED |

### Phase 2 — candidate and entry truth (Lanes B/C)
| Wave | Deps | Owned paths | Status |
|---|---|---|---|
| **V4-B1** canonical candidate episode registry | A1–A3 | new episode module + store (minted at handoff; extends the candidate-store plane, consumes `mastermind.entry_event.v1` + TURN WATCH triggers read-only) | NOT STARTED |
| **V4-B2** entry-event correction hardening (B-15…B-19) | B1 | `engine/us_early_turn.py`, its `engine/prophet_bridge.py` wiring (`:4018,:4318-4319`), manifest/roster tests | NOT STARTED |
| **V4-B3** orthogonal lifecycle contract | B1 | server state fields (bridge/board-rank stage vocab: `engine/us_board_rank.py:418-448`, `engine/prophet_bridge.py` status vocab), `templates/dashboard.html.j2` prophet stage plumbing, retires the four-way split per MP-1 | NOT STARTED |
| **V4-B4** deterministic buyability/chase firewall | B2, B3 | new availability engine module + mutation tests (minted at handoff); geometry prior art read-only (`us_early_turn` chase decay, live-states plane) | NOT STARTED |
| **V4-B5** Early Entry Desk MVP | B3, B4 | `templates/dashboard.html.j2` prophet section per MP-1 + `mockups/refs/institutionalize/us_stocks/` refs; TURN WATCH consumption (`site/turn_watch/turn_watch.json` read-only) | NOT STARTED |
| **V4-B6** Radar observation-only activation | B2; *Radar W4 staged (merged)* | Radar activation config + receipts only (`/etc/macro-live.env` arm via operator; Radar WS owns detectors) | NOT STARTED |
| **V4-B7** Radar production UI + Prophet integration | B6 | new `templates/entry_radar.html.j2` + route (closes Radar W9; #5737 reference input only) | NOT STARTED |

### Phase 3 — evaluation and learning plane (Lane F)
| Wave | Deps | Owned paths | Status |
|---|---|---|---|
| **V4-C1** cohort-separated all-candidate ledger | B1 | new cohort projection over `data/us_prophet_rank/` + QLedger claim wiring (`engine/qledger.py` consumed, never modified; control leg MUST be populated or control-matching not claimed) | NOT STARTED |
| **V4-C2** V3 legacy shadow | C1 | new `us_prophet_v3_legacy_shadow` definition module + stores, following the two-grain precedent (paired-row board grain; keyed-parts plan grain) | NOT STARTED (activates at cutover) |
| **V4-C3** operator decision instrumentation | B5 | new episode-keyed action store + API (minted at handoff) | NOT STARTED |

### Phase 4 — theme graph and broad intelligence (Lanes D/E)
| Wave | Deps | Owned paths | Status |
|---|---|---|---|
| **V4-D1** theme-source and identity census | 0A | docs + registries only | NOT STARTED |
| **V4-D2** canonical ontology + probation mapping | D1 | GMI-owned graph stores, `config/theme_crosswalk.yml` (executed in/with GMI lane) | NOT STARTED |
| **V4-D3** ThemeState v1 | D2 | GMI-owned (dynamic state layer = GMI W3B territory; merge-order ruling required before start) | NOT STARTED |
| **V4-D4** peer and transmission features | D3 | GMI-owned | NOT STARTED |
| **V4-D5** V4 intelligence-vector contract | D3 (may start on D1 census with theme family `ACCRUING`) | `engine/us_context_vector.py` extension + new `prophet.intelligence_vector/v1` emitter (family states governed by the Fusion registry, read-only) | NOT STARTED |
| **V4-D6** earnings adapter | *EIOS stable contract* | thin adapter only | BLOCKED EXTERNALLY (EIOS in E0) |
| **V4-D7** alt-data family adapters | D5 | one adapter per family | NOT STARTED |

### Phase 5 — ranking and product cutover (Lanes G/H)
| Wave | Deps | Owned paths | Status |
|---|---|---|---|
| **V4-E1** explainable deterministic V4 priority | B4, C1, D5; *Fusion PR-3B/3D accepted registry* | Fusion registry extension (post-acceptance), V4 rank projection | NOT STARTED |
| **V4-E2** Prophet V4 primary experience (cutover) | E1, B7, C2, A4 | Prophet product shell (`templates/dashboard.html.j2` prophet views or successor templates per MP-1), rollback switch, `premiumdata/us_stocks.json` server-side withholding (closes the anon leak at the latest here) | NOT STARTED |
| **V4-E3** listwise ranker challenger | C1, E1 | research + shadow lane only | NOT STARTED |
| **V4-E4** conditional router/multi-head challenger | E3; *Stock Identity interfaces* | shadow lane only | NOT STARTED |
| **V4-E5** temporal heterogeneous graph challenger | D4, E3 | shadow lane only | NOT STARTED |
| **V4-E6** promotion gauntlet + V3 retirement ruling | E3–E5 forward evidence | ruling docs + ledger | NOT STARTED |

## 3. Lane concurrency rules

- After 0A/0B: **Lane A (A1–A4) runs first and alone on the publication plane.** Nothing else touches publication paths until A3 merges.
- B-lane and D-lane may run concurrently after A1 (disjoint paths). C1 may start as soon as B1 merges.
- D2–D4 execute inside/with the GMI workstream (graph owner). Before D3 starts, a one-paragraph merge-order ruling must be appended here naming whether GMI W3B ships it or a V4 builder ships it under GMI review — the two must not both build ThemeState.
- **MP-1 rule (B3/B5/E2):** the page migration executes against `research/migration_packets/MP-1-prophet-board.md` (gates G-A/G-B/G-C satisfied at pin) mapped onto the four V4 state fields — freeze §12.4. The B5 handoff must confirm R3/R4 reference currency with the design authority and re-check the population re-source against `DNR:KILL-PROPHET-POP-MERGE` before executing it. No V4 wave re-designs what MP-1 already ratified without design-authority sign-off.
- E-lane opens only when its listed deps are merged; E3–E5 are shadow-only and may never edit production ordering paths.
- Model-routing law applies to every wave: sonnet `builder` builds, opus `reviewer` reviews, design surfaces via `designer`/main loop; every spawn carries explicit routing.

## 4. Appended merge-order rulings

*(none yet — append dated rulings here when two lanes need the same canonical authority)*
