# MKT-D09 — Studio W2: Heatmap Cards, Day-Recap, Threads, Weekly Receipts

**Department:** Studio · **Priority: P2** · **Status: ready now**
**Playbooks:** `research/MARKETING_ZERO_FOLLOWER_TRACTION_PLAYBOOK_BY_FABLE.md` + the TrendSpider playbook — these four formats are proven high-reach staples we don't produce yet.

## Why

The Studio currently produces 9 content kinds but only single-post formats. TrendSpider's reach engine leans on: the daily **sector heatmap** (screenshot-bait, zero reading required), the **closing-bell recap** (breadth + leaders in one card), **threads** (signal → evidence → receipt chain, the highest-retention format), and the **weekly receipts recap** (the trust builder). All four are deterministic composites of data we already compute.

## What already exists (do not rebuild)

- Sector heatmap engine + page: `scripts/build_market_heatmap.py`, `templates/market_heatmap.html.j2` — reuse the computation, render a card-sized variant.
- Breadth/macro facts: `engine/marketing/market_facts.py`; movers: `movers_source.py`; graded receipts: `receipt_source.py`; Prophet track record page (us_track_record).
- Card branding conventions: `chart_render.py` v3 (logo, CTA footer, typography).
- Tilt system: add new kinds to `config/marketing.yml desk_network` tilts + `content_studio.py` planner (the 9-kind pattern from #2950 — follow it exactly, including stub-strip).

## Deliverables — W2

1. **Heatmap card** (`render_heatmap_card` in `chart_render.py` or a sibling module): card-sized S&P sector heatmap (intensity = day %, labels = sector + %), brand footer. Kind `heatmap`, small tilt weight on `flagship` + `research_b`.
2. **Day-recap card + copy:** close data → one card (index moves, breadth line, top 3 gainers/losers with logomarks) + persona copy (Tape Reader voice fits). Kind `recap`, scheduled post-close via the outbox `scheduled_at`.
3. **Thread engine** (`engine/marketing/threads.py`): outbox items gain an optional `thread: [text1, text2, ...]` field (D02 actuator posts as a reply chain). First thread format: signal post → chart → confluence win-rate receipt → CTA. Every segment individually passes `validate_copy`; Sentinel counts a thread as ONE post for caps.
4. **Weekly receipts recap:** Monday morning card from the graded ledger — last week's closed calls, winners AND losers printed (the cherry-pick detector in D08 audits this), net stats with Ns. Kind `receipt_weekly` on the `receipts` account.
5. Tests: each new kind renders from fixtures, appears in the plan under its tilt, passes validate_copy, stub-strip doesn't eat it; heatmap card math matches the site heatmap for the same date.

## Acceptance

- One nightly run produces all four formats in `content_plan.json` with media files; a `designer`/opus screenshot taste gate passes on each card (operator bar: TrendSpider-grade, not default-matplotlib-grade); thread structure round-trips through the outbox schema.

## Traps

- Tilt weights must be **renormalized** when adding kinds (they currently sum to 1.0 per account) — don't silently break the distribution tests.
- Post-close scheduling needs D02's `scheduled_at` support — coordinate the schema, don't fork it.
- Losers must appear in the weekly recap even when the week was bad — an all-red recap posted honestly is the brand; a skipped week is the scandal.
