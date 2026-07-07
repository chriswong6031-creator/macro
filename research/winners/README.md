# Winner case library — `winner_case.v1`

Part of the **Winner Autopsy Lab** (see `research/WINNER_AUTOPSY_MASTERPLAN_BY_FABLE.md`).
One file per (ticker, episode): narrative markdown + one fenced ```yaml block carrying the
machine-readable case. The engine (`engine/winner_autopsy.py`) parses every file under
`research/winners/cases/` and reconciles each case against the mechanical episode census;
a case whose YAML does not parse fails `tests/test_winner_autopsy.py`.

## Operating loop

1. You notice a big winner (or an instructive *failed* breakaway).
2. Open `research/winners/CODEX_WINNER_CASE_PROMPT.md`, fill in TICKER / EPISODE_YEAR,
   paste the whole prompt to Codex.
3. Save Codex's output as `research/winners/cases/<TICKER>_<YYYY>.md`, commit via PR.
4. The next `--backfill` / nightly run joins the case to its mechanical episode
   (`case_joined=true` in `data/research/winner_episodes.parquet`) and it appears on the
   admin **Long-Hold Lobe** page.

## Schema `winner_case.v1` (fenced YAML block, required keys marked *)

```text
schema*             : "winner_case.v1"
ticker*             : uppercase symbol
case_type*          : winner | failed_breakaway
episode_year*       : YYYY of the run
run_window*         : [start ISO date, end ISO date]  # the visible run, Codex's judgment
t0_hypothesis*      : ISO date Codex believes the breakaway began (engine computes its own
                      mechanical t0 independently; disagreement is a finding, not an error)
benchmark           : ETF override (default: engine assigns GICS sector ETF; SPY fallback)
benchmark_rationale : one line, required if benchmark set
thesis_one_liner*   : one sentence, no scores, no "validated"
mechanism*          : platform_rerating | turnaround | squeeze | cycle_upswing |
                      policy_beneficiary | index_flow | other
stage_map*          : for each of compressed_prior, catalyst_ladder, relative_breakaway,
                      liquidity_confirmation, options_convexity:
                        {present: true|false|unknown, evidence: "one-two lines"}
catalyst_ladder*    : list of events, each:
                        date*        : ISO publication/filing date (PIT — never event
                                       "effective" dates that were disclosed later)
                        type*        : regulatory_decision | regulatory_panel |
                                       clinical_data | earnings | guidance |
                                       partnership | contract_win | product_launch |
                                       investor_day | ma_activity | capital_return |
                                       index_inclusion | management_change |
                                       macro_policy | other
                        headline*    : one line
                        source_url*  : URL
                        durability   : high | medium | low  (descriptive read)
research_echo       : {consensus_vs_spot, notable_revisions, sources[]} — qualitative;
                      analyst-target data does not exist in-repo, cite external sources
ownership_context   : {context_only: true*, notes} — WA-R2: context display only, never a
                      positive signal input
hazards*            : list from docket §5.3 vocabulary (extended_after_vertical_move,
                      call_wall_overhead, catalyst_exhausted, low_float, ...) — free-form
                      additions allowed
false_positive_checks* : for meme_squeeze, one_day_binary, sector_beta, options_mirage:
                        {verdict: ruled_out | possible | likely, note}
local_evidence      : numbers computed from repo data files, each with the source path —
                      optional but encouraged (see MRNA_2026.md)
sources*            : list of {url, accessed: ISO date, claim}
```

## Hard rules (from the masterplan rulings)

- Every external claim carries a URL and a date. Publication timestamps only (PIT).
- No composite scores anywhere (WA-R1). No "validated" (CI-enforced repo-wide).
- Ownership/13F/insider material is context-only (WA-R2) and must say so.
- No MNPI, expert networks, or non-public sources (qualitative-intelligence boundary).
- Failed breakaways are first-class citizens: `case_type: failed_breakaway` cases teach
  the detector what death looks like; target ≥1 failed case per 4 winners.
