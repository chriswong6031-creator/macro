# China Alpha Program — charter (Fable-orchestrated)

**Owner mission (2026-07-03, verbatim intent):** radically revamp the China A-share stock + thematic
basket engines (`china_stocks.html`, `sector_central_china.html`, `baskets_china.html`) so the board
surfaces *"incredible stock picks at great entries"* — names **about to run** (sector about to run /
mean reversion after complete washout of sector AND name / catalysts), **not** extended leaders —
and fix the **ranking + contradictory UI** ("extended / HOLD / red / low-score names still rank
high; users can't tell why").

**Owner ground truth (the most valuable input in the program):** three picks the current board
surfaced that the owner designates GREAT: **300725, 603129, 688306**. Their shared signal signature
is the design target; their contradictory UI chips are the reconciliation target.

**Honest starting posture (owner's own words):** we do not understand A-share markets that well;
the CN engines never got the hundreds-of-sessions signal iteration the US board got. So this program
front-loads *understanding* (Phase 1) before *building*, and every shipped signal must carry forward
grading — the exit question is answered with evidence.

## Canonical inputs
- `research/china_alpha/OWNER_RATIONALE.md` — **owner's per-exemplar rationale + causal doctrine + distilled spec S1-S5 (the ground truth every wave is checked against)**
- `research/CHINA_STOCK_PIPELINE_PROBLEM_AUDIT_FOR_FABLE.md` — 2026-07-03 feeder→picker pipeline audit
- `research/CHINA_ENGINE_PROBLEM_BRAINSTORM.md` — 2026-07-01, 91 problems + §8 tensions (adversarial layer)
- `research/CHINA_STOCKS_OVERHAUL.md` — A-share research verdicts (what transfers / inverts)
- `research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md` — post-cross basing re-admission (US HOLD, #1032)
- `research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md` — the source system's pathologies (port primitives, not the product)

## Phases
| Phase | What | Artifact | Status |
|---|---|---|---|
| **P1 Investigate** | 10 parallel deep readers: 3 exemplar forensics, ranking+UI contradiction anatomy, [verify] items, data inventory, phase-0 verdict ledger, rotation machinery/fast-feeder feasibility, US→CN port recipes, external A-share signal research; + completeness critic + gap-fill | `research/china_alpha/phase1/*.md` | **LAUNCHED 2026-07-03** (workflow `china-alpha-phase1`) |
| **P2 Masterplan** | Fable synthesis: rulings on tensions, novel solutions, wave plan | `research/china_alpha/CHINA_ALPHA_MASTERPLAN_BY_FABLE.md` | pending P1 |
| **P3+ Waves** | Execution via Opus/Sonnet subagents; each wave ships commit→PR→merge with tests + forward-ledger hooks | per-wave PRs, Status log below | pending P2 |

## Acceptance gate (the owner's exit question)
> "Have I achieved the primary objective — a dashboard that genuinely provides incredible stock
> picks at great entries?"

This is answered **with forward-graded evidence** (CSI300-relative, fill-realistic: T+1 + limit-up
unfillability modeled), not vibes. If the evidence says no, the program loops: reassess → new
solution round → new waves.

## Standing constraints
- Do-not-rerun ledger: everything FALSIFIED in the phase-0 verdict ledger (P1) is a guardrail, not a suggestion.
- Ship-shape discipline: new signals enter as bonus/chip + forward ledger first; hard-gate power is *earned* by accrued grades.
- Owner risk posture: trades real money on low-n mechanism theses — add rigor, not lectures.
- Model tiers: Fable orchestrates/judges; Opus plans/analyzes; Sonnet executes mechanical code.

## Status log
- **2026-07-03** — Program chartered. P1 investigation workflow launched (10 readers + critic + gapfill). Worktree `lucid-knuth-523979`.
- **2026-07-03** — Owner supplied per-exemplar rationale → `OWNER_RATIONALE.md` (spec S1-S5: W-tier setup layer, lifecycle stages, narrative confluence, pick-strength tiers). P1b probe wave launched: mtf-machinery (owner-read reproduction), narrative-confluence feasibility, board-history timeliness from git.
- **2026-07-03 05:30** — P1 COMPLETE: 10/10 readers landed (`phase1/*.md`). Workflow critic + all 3 P1b probes died on session limit (resets 09:30 PT) — orchestrator ran the critic pass inline → `phase1/_SYNTHESIS.md` (cross-exemplar signature, contradiction reconciliations, gap list D1-D6, firm rulings R1-R6). Headline: owner archetype = washout→base→turn (NOT the advertised reversal edge; rev_z negative on 2/3 exemplars); rank bonuses inverted vs signal earliness (COILED earliest/+0.25, washout latest/+0.50); capture 0-42% of exemplar runs; volume plane + THS heat + daily sector first-tick-up all present-and-unwired; gate_factor stuck at 0.2 (Accumulate unreachable). NEXT: resume P1b probes + read full signal-research report after reset → author masterplan.
