# W2R — research triage & tiering (XG-W8)

Runbook for `engine/press/research_triage.py`, `engine/press/research_veto.py`,
`engine/press/research_lane.py` and `scripts/run_research_triage.py`.

Charters: `research/agentic_media/MEDIA_NETWORK_MASTERPLAN_BY_FABLE.md` §5b (the
spec) and `research/agentic_media/X_GROWTH_UNIFIED_OPERATION_BY_FABLE.md` §6
(the reconciliation ruling: *"Media W2R's W-score reuses IS-W2 components —
one scoring brain, two consumers"*).

## What it does

About 150 institutional reports enter the research vault every day. The triage
layer scores **every one of them in the window**, ranks them, lets a cheap model
strike out the ones that cannot carry a piece, hands the ranked order to the
press planner, and writes the whole thing down.

```
data/research_vault/catalog.json
        │
        ▼
engine/press/research_triage.rank()      six components, deterministic, no LLM
        │                                 (garbage gate runs first: gated reports
        │                                  never reach a model, but still print)
        ▼
engine/press/research_veto.run()          cheapest model, DEMOTE ONLY
        │
        ▼
research_triage.apply_vetoes()            the ONLY place a verdict becomes a number
        │
        ├──► data/press/research_triage.jsonl     one row per report per day
        │
        └──► engine/press/desk_planner._plan_research()
                     research_desk (flagship tier) → 500–900w analysis
                     research_note (desk-note tier) → 300–500w note   [DARK]
                              │
                              └──► engine/press/research_lane.py       [DARK]
                                       x_post   short-form, value-complete
                                       x_article X-native long-form
```

## The W-score

Six components, every one in `[0, 1]`, blended by `research_triage.weights`.
**Every weight is a hypothesis awaiting main-loop ratification** — the
masterplan's wave table says so explicitly ("weights ratified in main loop") and
the charter's §8 assumptions register binds this wave like every other.

| Component | Default weight | What it measures | Reuses |
|---|---|---|---|
| `extraction_quality` | 0.24 | structure/depth of OUR vault `summary_points` | — |
| `relevance` | 0.22 | report tickers/themes vs live movers, hot chronicle threads, watchlist | `signal_features.tokenize`, `movers_source` |
| `cluster_density` | 0.18 | independent institutions on one theme in the window | `story_spine` (MinHash + `independence_key`) |
| `institution_tier` | 0.16 | per-institution prior; unlisted = neutral | — |
| `novelty` | 0.12 | inverse 30-day self-similarity vs our own estate | `validators.window_jaccard` |
| `attention_potential` | 0.08 | headline-grade shape; **ranking input only** | `signal_features.headline_shape` |

Ordering logic, in one line: *can we write it* > *does it matter to us* > *does
it matter to the street* > *who said it* > *have we said it* > *will anyone
look*. `attention_potential` is last on purpose — it is the term most able to
drag the brand toward the framing the §5 validators exist to ban, so it earns a
tie-break and nothing more. The §5 suite still fails any draft dressed in
unearned urgency; nothing about the ranking reaches the writer's prompt.

### Honest state of the components today

Run `python -m scripts.run_research_triage --dry-run` and read the
`context_states` block before trusting any ordering. As shipped:

* `institution_tier` — the register (`research_triage.institution.tiers`) ships
  **empty**, so every institution scores the `unranked` neutral and the
  component orders nothing. That is an operator/Fable lever, not a builder's
  opinion about which houses matter.
* `cluster_density` — needs the optional `datasketch` wheel. Without it, story
  identity is the exact normalized-headline key only, so the count is a
  **floor** and every row says `state: exact-only`. The production workflow
  installs `datasketch`; a local checkout usually does not.
* `novelty` — with six evergreen posts and no research desk output yet, overlap
  is zero and every report scores 1.0. It starts biting once the desk publishes.
* `relevance` — **do not remove `exclude_chronicle_sources`.** The vault ingest
  writes one `research_vault` chronicle event per report, so a live 7-day
  chronicle window is 236 vault events out of 242. Before that exclusion existed
  the component compared the corpus with itself and sat at its saturated value
  for all 280 candidates.

## Nulls are printed

`data/press/research_triage.jsonl` carries **one row per report per day** for
every report in `research_triage.ledger.window_days` — selected, skipped and
garbage-dropped alike. A garbage-dropped report still carries its six
components: the gate decides LLM eligibility (a dropped report costs zero
tokens), not whether we admit to having looked.

Each component reports a named `state` rather than a bare number:
`observed`, `unranked`, `no-institution`, `exact-only`, `no-story`,
`no-context`, `no-extraction`, `no-peers`, `no-text`, `error`.

Ledger truncation (`ledger.max_rows_per_run`) emits a `::warning`. It is never
silent — a quietly shortened ledger is "nulls hidden" with extra steps.

## The veto pass can only demote

`engine/press/research_veto.py` performs **no arithmetic on any score**. It
returns `{report_id: reason}` where `reason ∈ {thin, paywalled, duplicate}`, and
the parser drops anything else: unknown ids, unknown reasons, non-truthy
`demote`, unparsable responses. There is no branch in that module that reads a
number, and "promote" is not a word its parser knows.

`research_triage.apply_vetoes` is the sole place a verdict becomes a number, and
it has three independent locks: the factor is clamped into `[0, 1]`, the new
score is `min(old * factor, old)`, and only reasons in `VETO_REASONS` for ids
that were actually ranked are honoured.

Spend rides the existing `engine.llm_auth` waterfall and lands in the existing
`lib.ai_costs` ledger under the usage lane `press-research-triage-veto`. Default
`head_size: 40` / `batch_size: 20` is two cheap completions a day; the
masterplan prices full 150/day coverage at about $5/mo, which is a `head_size`
edit, not a code change.

**With no credential visible the pass demotes nothing and the deterministic
ranking stands.** That is the safe direction by construction.

## Publish volume — the cold-start ramp

`config/press.yml` → `research_triage.volume.stage` selects a row from
`volume.stages`. **This one key is the only way to raise volume.**

| stage | flagship/day | notes/day | opens on |
|---|---|---|---|
| `cold_start` *(shipped)* | 1 | 0 | arrival |
| `warm` | 2 | 4 | Search Console rows flowing per URL, property indexed, no Beacon degradation over a trailing month |
| `target` | 3 | 12 | W2 per-desk scorecards trending, zero validator overrides for two weeks |

Masterplan §5b: *"publish volume is a GSC-evidence-gated config knob, never a
day-one 1,500/mo — a cold domain at that cadence is the scaled-content-abuse
profile Google deindexes."* Moving the stage is an operator/main-loop decision
with the W2 scorecards in hand.

The desk cadence and the volume knob compose as **stricter-of**, so neither can
be raised alone into a cadence the other never agreed to.

## What is dark, and exactly how to arm it

| Thing | Lock | Arming lever |
|---|---|---|
| The triage workflow | `vars.RESEARCH_TRIAGE_ENABLED != 'true'` | create the repo variable = `true` |
| The veto pass | no LLM credential visible | repo secret `ANTHROPIC_API_KEY` (or an OAuth pool key / `DEEPSEEK_API_KEY`) |
| Ledger writes | `--dry-run` is the CLI default | the scheduled workflow passes `--write`; a manual dispatch needs `write: true` |
| Press publishing | `vars.PRESS_PUBLISH_ENABLED != 'true'` | unchanged from W1 |
| `research_note` desk | `volume.stage: cold_start` → 0 notes/day | move `research_triage.volume.stage` |
| Mastermind Research X account | **four independent locks** | see below |

The X property is dark on four locks, and all four have to move:

1. **The X account does not exist.** X Growth charter §1 lists it as *(not
   created yet)*; §7 lever 1 is the operator creating it.
2. **No Buffer channel.** `publish.channels` has no `mastermind_research` entry.
   Discover the id with the `buffer-channels` workflow once the account exists.
3. **`desk_network` says no twice** — `enabled: false` **and** `disabled: true`,
   with no `handle:` key. Both keys, because the publish-time lanes once
   filtered on `disabled` alone and made a dark property postable.
4. **`research_lane.build_items` refuses.** It resolves liveness through
   `engine.marketing.accounts` and returns `state="dark"` with an empty item
   list before building anything. `enqueue=True` on a dark account is a no-op.

Arming order: create the account → discover and bind the channel id → fill
`handle:` and `created:` and flip both keys **in one PR**. Sentinel resolves the
ramp tier from `created:`; on an enabled account a missing value fails closed to
the strictest tier and prints a `::warning`.

## Running it

```bash
# rank the whole catalog, print the head, write nothing, spend nothing
python -m scripts.run_research_triage --dry-run --no-veto --top 25

# with the veto pass (needs a credential; still writes nothing)
python -m scripts.run_research_triage --dry-run --top 25

# what the nightly does
python -m scripts.run_research_triage --write

# reproduce one day's ranking
python -m scripts.run_research_triage --as-of 2026-07-28 --dry-run
```

`--as-of` is a **dev lever**, not an evidence lever: the vault catalog is a live
snapshot with no history, so a back-dated run sees today's catalog filtered to
that date's window, not that date's catalog.

## Tests

`tests/test_press_research_triage.py`, wired into the `press-lane` job in
`.github/ci/legacy-jobs.yml` (which installs `pytest pyyaml jinja2` — the suite's
whole closure). Nothing in it is `importorskip`-gated, so it cannot decay into a
skip-only suite; the `datasketch`-dependent branch is asserted through its
documented degraded state rather than by requiring the wheel.
