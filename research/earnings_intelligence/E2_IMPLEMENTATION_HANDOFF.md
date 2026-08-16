# E2 Implementation Handoff — Golden Event Workspace

**Blocked on E1.** Do not start until `evt_cik0000320193_2026q3_results` has a live `event_workspace.v1` that passes the E1 gates.

**Not done unless** the existing Terminal Company Intelligence workspace and the dossier glance module render AAPL Q3 FY2026 from that payload — what happened, reported/prior/consensus where basis matches, guidance change or typed absence, Q&A materiality without fake exchanges, history comparison, market reaction or `not_joined`, source completeness, exact evidence opens — at 1440 / 820 / 390, EN/ZH, dark/light.

Read first: `E0_E1_E2_CONTRACT_FREEZE.md`, `E0_EXPERIENCE_ARCHITECTURE.md`, `compositions/e0_real_data_specimen.html`, Terminal `docs/COMPANY_INTELLIGENCE_V2_DELTA_SPEC.md` (spec only — do not treat screenshots as live proof), this file.

---

## What to extend (not replace)

- Terminal CI v1 lenses: Brief, Transcript, History, Topics, Sources, EvidenceRail.
- Macro dossier Company Intelligence block.
- Existing Terminal shell, nav, Ask Mastermind entry.

Do not add Peers, Slides, Command Center, global search, or a third header.

---

## Acceptance interactions (screenshot these)

1. `/analysis?symbol=AAPL&page=intelligence` Brief shows FY2026 Q3 call 2026-07-30, canonical or aliased id, state from the payload (not a stale Q2).
2. Click revenue $109.4B (or the bound fact that replaced it) → Evidence rail opens the span or typed absence. A no-op fails.
3. Transcript lens opens the **same** event body.
4. Sources lists 8-K/Exhibit 99.1 as present or explicit `not_ingested` — never silent.
5. Dossier module on the AAPL stock page uses the same stance sentence and event id as Brief.
6. Repeat 1440, 820, 390; EN and ZH; dark and light.

Glance copy budget: title ≤ 4 words; stance ≤ 14 words. Pending/overlay chips are required if any fact is still `address_only`.

---

## Honest empties (must render, not hide)

| Field | If E1 omitted it |
|---|---|
| Guidance | Typed absence — no invented beat/miss |
| Q&A exchanges | Count + “Open transcript”; no fake pairs |
| Narrative / commitments | Empty state |
| Market reaction | `not_joined` chip unless E2 joins PIT display-only |
| Slides / consensus | Completeness chips already on the payload |

---

## Forbidden

- Reading CI v1 `score_overlay` as the glance once `event_workspace.v1` exists.
- Building Command Center, Peers, Slides, keyword alerts.
- Promoting any metric to Prophet authority.
- Starting if E1 is not merged and live.

---

## Files

Allow-list: Terminal CI components + e2e; Macro dossier consumer of `event_workspace.v1`; paired tests. No engine identity rewrite (that was E1).
