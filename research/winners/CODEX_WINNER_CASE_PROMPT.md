# Codex winner-case research prompt (paste everything below the line, fill the two blanks)

Operator usage: replace `{{TICKER}}` and `{{EPISODE_YEAR}}`, paste to Codex in the repo,
save the output verbatim as `research/winners/cases/{{TICKER}}_{{EPISODE_YEAR}}.md`.
For an instructive failure, add "This is a FAILED breakaway case (`case_type:
failed_breakaway`)" after the first paragraph.

---

Run a deep research study on why **{{TICKER}}** produced (or failed to sustain) large
alpha versus its own sector cohort and the index during **{{EPISODE_YEAR}}**. This is a
standardized "winner autopsy" pull for the Winner Autopsy Lab
(`research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md`); your output feeds a machine-parsed
case library, so the format contract at the end is mandatory.

## What to produce

A single markdown file with these sections, in order:

1. **Bottom line** — what actually drove the move, in one paragraph, mosaic-not-headline.
2. **Local tape evidence** — compute from repo data and cite each file path used:
   - returns at 5/21/42/63/126 trading days and YTD vs the sector ETF and vs SPY
     (prices: `data/massive_stock_day/<SYM>.parquet`, ETFs also in `data/yahoo/`)
   - dollar-volume expansion (close×volume, z-score vs trailing 21d/60d), biggest
     dollar-volume days, whether gaps held 3/5/10 sessions
   - new-high structure: first 63d/126d/252d closing high dates
3. **Catalyst ladder** — every public event that let capital re-underwrite the name:
   dates are PUBLICATION/FILING dates with URLs. Check `data/edgar/material_8k_events.parquet`
   and `data/edgar/earnings_8k_dates.parquet` for filing anchors; use the web for the rest.
4. **Stage anatomy** — map the episode to the five stages (compressed prior → catalyst
   ladder → relative breakaway → liquidity confirmation → options convexity) with one-two
   lines of evidence each. Say "unknown" where evidence is thin.
5. **Fundamentals arc** — revenue/margins/runway before vs during the run
   (`data/edgar/fundamentals_panel.parquet`, `statements.parquet`,
   `statements_quarterly.parquet`, `eps_quarterly.parquet` — all PIT-gated by
   `asof_date`/`as_of`; state coverage gaps honestly).
6. **Options context (if available)** — current snapshot only: `site/gex/<SYM>.json`,
   `data/polygon_gex/summary_<SYM>.parquet`, `data/options_entry/state.parquet`.
   Per-ticker options HISTORY starts 2026-06; say so rather than inventing history.
   Never claim signed flow direction without trade-level NBBO (repo doctrine:
   `research/OPTIONS_FLOW_DATA.md`).
7. **Research echo** — consensus vs spot, notable target revisions, the "price escaped
   the published model" read. External sources with URLs; the repo has no analyst-target
   data.
8. **Ownership context (context-only)** — 13F breadth (`data/quiver/sec13f*.parquet`,
   PIT = ReportPeriod + 45d), insider activity (`data/quiver/insiders.parquet`, PIT key
   `fileDate`). Label the whole section context-only: standing ruling NEXTL-U13 forbids
   using ownership as a positive signal.
9. **Hazards & false-positive checks** — meme_squeeze / one_day_binary / sector_beta /
   options_mirage, each ruled_out|possible|likely with a note; plus current hazards
   (extension, call walls, catalyst exhaustion).
10. **Machine block** — a single fenced ```yaml block conforming to `winner_case.v1`
    (spec: `research/winners/README.md`). The YAML must parse; required keys: schema,
    ticker, case_type, episode_year, run_window, t0_hypothesis, thesis_one_liner,
    mechanism, stage_map, catalyst_ladder, hazards, false_positive_checks, sources.

## Hard rules

- Every external claim: URL + date. Publication timestamps only — no lookahead.
- No composite scores, no buy/sell language, no "validated" (CI-enforced).
- No MNPI, expert networks, or non-public sources.
- Print nulls: if a stage is absent or data is missing, say so — absence is data.
- Do not modify any repo file other than creating your output document.
