# MKT-D03 — Engagement Telemetry → Lab Learning Loop

**Department:** Lab (growth_science) · **Priority: P1** · **Status: W0 SHIPPED (PR #3053, 2026-07-19) — telemetry schema/join/rollup (post-deduped N-floor) + build_marketing wiring + admin Lab page; W1 capture depends on D02 live posting**
**Charter:** `engine/marketing/departments.py` id=`growth_science` ("Growth Science & Self-Improvement", 14 chartered engines — stubs).

## Why

The whole self-improving-CMO premise rests on a feedback loop that does not exist yet: we publish, but never measure. The zero-follower playbook (`research/MARKETING_ZERO_FOLLOWER_TRACTION_PLAYBOOK_BY_FABLE.md`) is a set of *hypotheses* about what reaches (multi-cashtag theme lists, instant earnings, chart receipts) — the Lab's job is to grade those hypotheses with real reach data and feed the winners back into the Content Studio tilts and CMO incentives.

## What already exists (do not rebuild)

- Rich per-post provenance already in `data/marketing/content_plan.json`: content kind, account, persona, cashtags, source engine, mode (llm/deterministic). This is the join key surface — do not invent a parallel taxonomy.
- CMO loop + experiments scaffolding: `engine/marketing/cmo.py`, `experiments.py`, `economics.py`.
- D02's outbox ledger will hold `posted` items with tweet URLs + timestamps.

## Deliverables

### W0 — schema, join, and Lab surface (buildable now against fixtures)
1. `engine/marketing/telemetry.py` — schema + ingest: `data/marketing/telemetry/YYYY-MM.jsonl`, rows `{post_id, captured_at, impressions, likes, replies, reposts, bookmarks, link_clicks?, followers_at_post}`. Join to content_plan provenance by `post_id`; classify each post into the analysis dimensions: **format kind × cashtag traffic tier × persona × account × time slot × mode(llm/det)**.
2. Roll-up job (nightly, cheap, off the heavy path): per-dimension reach medians, follower deltas per account, top/bottom posts. Artifact `data/marketing/lab_rollup.json`.
3. Admin **Lab page** (via `designer` agent): the hypothesis board — each playbook hypothesis as a card with its current evidence state (seeding/confirmed/refuted), the dimension roll-ups, top posts with media thumbnails. Fixture-driven until real data lands.
4. Tests: join integrity (orphan telemetry rows flagged, not dropped silently), roll-up math on fixtures, empty-data renders honestly ("no live data yet"), never invents numbers.

### W1 — real capture (needs D02 live + analytics access)
5. Capture lane in the actuator session: after posting windows, visit own-post analytics per account via the same browser profiles and record metrics into the telemetry file (rate-limited, once or twice daily; screenshot receipts for spot-audit).
6. Wire the loop: weekly Lab verdicts adjust **display-tier recommendations only** — a `lab_recommendations.json` the CMO loop and admin surface show ("theme_list posts on research_b at 9:30 ET outperform 3.2×"). Tilt changes remain a human/CMO decision in config, not an automatic write.

### W2 — experiments
7. A/B lanes through `experiments.py`: pre-registered (hypothesis, dimension, window, success metric written BEFORE the run), one variable at a time (e.g. persona A/B on the same format+slot). Results append to the hypothesis board.

## Acceptance

- W0: synthetic fixture → correct roll-ups; Lab page renders the hypothesis board; join flags orphans.
- W1: ≥95% of posted items acquire at least one telemetry row within 48 h; roll-up appears in the nightly artifact.

## Traps

- **Epistemics law bites here hardest:** reach analysis is display-tier evidence, not authority. No automatic tilt mutation without the pre-registered experiments lane (W2) — the gauntlet pattern applies to promoting a hypothesis into standing strategy.
- Small-N humility: with zero followers, early reach data is mostly noise + cashtag-traffic beta. Roll-ups must print N and suppress verdicts under a floor (N<20 posts per cell → "seeding").
- Telemetry scraping is per-account browser work — it shares D02's cadence caps and kill-switch; never a separate uncapped loop.
