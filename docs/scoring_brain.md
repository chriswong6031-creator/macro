# Scoring brain runbook (XG-W5 = IS-W2)

The marketing-internal wire triage layer: an L0 story spine, six L1 deterministic
features, a P0 garbage gate, and a golden-set eval harness. Nothing here is a
market signal and nothing here is user-facing.

**Charters:** `research/agentic_media/X_GROWTH_UNIFIED_OPERATION_BY_FABLE.md` §6
(XG-W5) · `research/agentic_media/INTELLIGENCE_SUITE_MASTERPLAN_BY_FABLE.md` §3
(IS-W2 spec) + §0 (IS-W2 acceptance gate).

**Code:** `engine/marketing/story_spine.py` · `engine/marketing/signal_features.py` ·
`engine/marketing/garbage_gate.py` · `engine/marketing/golden_set.py` ·
`engine/marketing/breaking_relevance.py` (`score_item`, `_components`) ·
`engine/marketing/press_lane.py` (`run_press_tick`, the production wiring) ·
`scripts/marketing_golden_set.py` (CLI).

**Config:** `config/marketing.yml` → `breaking.scoring` and `breaking.garbage_gate`.
Every threshold and weight is a key there; charter §8 binds them as hypotheses,
not truths.

---

## 1. What is live, and what is dark

| Layer | State | Arming lever |
|---|---|---|
| Garbage gate (5 detectors) | **LIVE** | `breaking.garbage_gate.detectors.<name>: false` to disable one |
| L0 story spine (exact identity + clustering) | **LIVE** | `breaking.scoring.enabled: false` kills the whole layer |
| L0 MinHash near-dup pass | **degraded off** — `datasketch` is not installed on the press host | `pip install datasketch` in the daemon venv; no config change needed |
| L0 semantic pass (Model2Vec) | **dark** | §3 below (needs an artifact AND a config flip) |
| L1 features + persisted `_components` | **LIVE** for 100% of ingested items | — |
| `rank_score` **ordering** the queue | **dark** | `breaking.scoring.rank_ordering: true` — **gated on §2** |
| Salience demotion multiplier | **dark** | `breaking.scoring.demote_enabled: true` |
| `source_authority` prior | **inert — rank weight 0.0** (review F-5) | two preconditions below; the accrual machinery runs meanwhile |
| `tone_extremity` | **inert** (no GDELT join exists) | lands with the IS-W1 GDELT provider |
| L2 learned ranker | **out of scope** | needs ≥3 weeks of real labels first |

The two "inert" features are not broken. They report their own state
(`neutral-prior`, `absent`) in `_components.feature_detail` and contribute a
constant, so they are rank-neutral until they have something to say.

### `source_authority` — why its ordering weight is 0.0, and what would arm it

The accrual machinery ships and runs; only its **ordering weight** is zero. Two
things must be true before that weight moves, because today the feature would
rank noise:

1. **The prior must live on the measured axis.** The neutral prior is 0.5, which
   on the log scale equals ~21.4 weighted engagement. A real source that crosses
   `min_samples` with genuinely low engagement therefore scores *below* a source
   we have never measured at all — measurement demotes it. A prior that is not
   comparable to the thing it stands in for is not a prior, it is a different
   number wearing the same units.
2. **Engagement must be sampled at a fixed post age.** `press_providers.parse_tweets`
   reads the counts once, seconds after the poller first sees the post. What that
   measures is *how quickly we polled*, not how the post performed — so handles on
   the fast tier would score lowest and the ranking would invert. A fixed-age
   refresh (re-read each post at, say, T+60min) is the fix, and it is deliberately
   **not** attempted in this wave.

Until both hold, `_components.feature_detail.source_authority` keeps reporting
`neutral-prior` with its sample count, so the label loop can still accrue.

### Gate ordering — what a score may and may not do

A score may **reorder** and **deprioritize**. It may never publish. In
`press_lane.run_press_tick` the ordering sort is step 3; every gate that decides
whether an item goes out runs after it and none of them reads `rank_score`:

```
step 3   sort (salience, or rank_score when armed)     <- the ONLY use of rank_score
step 4   corroboration_decision()                      -> digest / attributed / instant
step 5   salience floor + flagship top-K/day           -> salience, never rank_score
step 5c  story_lock.check()                            -> one conversation, one owner
step 6+  value gate -> make_item/validate_item -> enqueue
         (id-dedup, 7-day text-dedup, same-account and cross-account near-dup,
          sentinel caps, cadence resolver)
```

The demotion multiplier in `breaking_relevance._demotion_factor` is clamped at
`1.0`, so no feature can lift an item over the flagship floor arithmetically —
not just by convention.

---

## 2. Golden set (operator/Fable lever)

The masterplan gates `rank_ordering` on evidence: the scorer's precision@20 must
beat salience-only ordering on a ~200-item labeled set. Until labels exist the
harness reports `state="no-labels"` and a **null** precision — never a pass.

**The ingested corpus is runtime-only.** The press daemon writes
`data/marketing/press/ingest_corpus.jsonl` on the VPS and that whole directory is
gitignored (pollers make zero git writes), so there is no snapshot in the repo to
sample. Export on the host:

```bash
# on the press host
cd /srv/macro-dashboard
python3 scripts/marketing_golden_set.py export --n 200 --out /tmp/golden_batch.jsonl

# from a workstation
scp <vps>:/tmp/golden_batch.jsonl .
```

The batch is stratified (outcome family × source tier × salience band) and
deterministic in `(seed, item_id)`, so re-running it over the same corpus returns
the same batch and an interrupted labeling session resumes cleanly. Rows already
in the label store are excluded, so successive batches extend the set.

Label each row's `label` field with exactly one of:

| label | means |
|---|---|
| `garbage` | should never have entered the pipeline |
| `useful` | real information, not worth a post on its own |
| `post_worthy` | worth an X post |
| `viral_grade` | worth a prime slot |

`post_worthy` + `viral_grade` are the positive class for precision@20 — "did the
top 20 deserve the scarce slots", which is what the top-K/day counter spends.

Then fold and commit:

```bash
python3 scripts/marketing_golden_set.py import golden_batch.jsonl --labeler fable
git add data/marketing/golden_set/labels.jsonl     # a COMMITTED artifact
python3 scripts/marketing_golden_set.py eval --k 20
```

The label store is hand-authored and committed like `config/reply_targets.yml`.
No engine path writes it; the nightly does not advance it. It is ground truth,
not a forward ledger.

### Which sampling mode, and what the eval is entitled to claim

`export --mode` decides which estimator the eval may use:

| mode | what it draws | eval estimator |
|---|---|---|
| `stratified` (default) | round-robin across (outcome, source tier, salience band) — rich in rare cells, good for grading the **garbage gate** | **inverse-inclusion-probability**; each row carries `inclusion_weight` = 1/p |
| `head` | uniform random sample of the top `head_size` by the baseline score | **unweighted** — unbiased for precision on the head the top-K/day counter actually spends |

A stratified sample is *not* a uniform sample of the production head, so an
unweighted precision@k over it is biased. `evaluate` reads `sample_mode` off the
labels and names its estimator in the report; a store mixing both designs
reports `unweighted-mixed-design` and is explicitly indicative only.

### The gate is a paired test, not a sign test

`beats_salience` requires **all** of:

- `delta >= min_margin` (default 0.05), and
- **McNemar exact p ≤ `alpha`** (default 0.05) over the *discordant* top-k pairs
  — items one ordering caught and the other missed; concordant items carry no
  information about which ranker is better, and
- more positives found by rank than by salience.

A paired bootstrap CI on the delta is printed alongside, and the raw delta is
always displayed. Comparing two point estimates and declaring the bigger one the
winner reads "better" on noise about half the time; that is why it is gone.

**Arming rule:** flip `breaking.scoring.rank_ordering: true` only after
`eval` reports `state: ok` and `beats_salience: true`. Record the full report —
estimator, delta, CI, discordant pairs, p — in the arming PR.

---

## 3. Semantic pass (Model2Vec) — artifact is an operator/R2 step

There is **no runtime model download on any path**. `story_spine.load_encoder`
only ever loads from a local directory and returns `None` — pass disabled, one
start-of-line notice — when the directory is absent, when `model2vec` is not
installed, or when the load fails.

To arm it:

1. Fetch the `potion-base` artifact once, off the render path, onto the press
   host (R2 mirror or a one-off download on a workstation, then `rsync`). Put it
   somewhere outside the git checkout, e.g. `/var/lib/macro-live/models/potion-base-8M`.
2. `pip install model2vec` in the daemon venv.
3. Set in `config/marketing.yml`:
   ```yaml
   breaking:
     scoring:
       semantic:
         enabled: true
         model_path: "/var/lib/macro-live/models/potion-base-8M"
   ```
4. Restart `marketing-press-feeds`. Confirm the absence notice is gone from the
   unit log; if it is still there, the artifact path is wrong and the pass is off.

Never point `model_path` inside the repo checkout — the render lane resets it.

---

## 4. State and its bounds

All scoring-brain state lives in the daemon-local, gitignored
`data/marketing/press/state.json` alongside the provider cursors:

| key | holds | bound |
|---|---|---|
| `story_spine` | stories, their sources/tier mix/engagement, content keys | TTL `story_ttl_h` (72h) + hard cap `max_stories` (1500) |
| `signal_corpus` | hourly + daily token/document counts | `burst_window_h` (72h), `novelty_window_d` (30d), `max_tokens_per_bucket` (2000) |
| `source_authority` | per-source EWMA engagement + sample count | `max_sources` (500), trimmed by sample count |

`data/marketing/press/ingest_corpus.jsonl` rolls past **64 MB** (config
`breaking.scoring.corpus_sink.max_bytes`) down to its newest
`corpus_sink.max_rows` rows. The roll is streaming — two passes, one line of
memory — so even the rare roll never stalls the live tick.

One further bound matters for the labeling sample: an item contributes **at most
one corpus row per `corpus_row_window_h`** (default 24 h). The lane's `seen`
ledger only advances on emit/refusal, so without that window a digest or
below-floor item would be re-rowed every 120 seconds forever and a "200-item"
batch would come back holding a dozen stories.

Pruning runs every tick. If `state.json` grows unexpectedly, check the tick log
for `::warning title=scoring-brain-prune`.

---

## 5. Reading a decision

Every scored item carries `_components`:

```
_components.scoring_version        "xg-w5.1"
_components.salience               the historical salience breakdown + demotion_factor
_components.features               the six L1 values, 0-1
_components.feature_detail.<name>  per-feature state + inputs (incl. honest nulls)
_components.rank.contributions     weight x value, per term
_components.rank_score             the ordering number
_components.story                  story_id, match kind, source_count, tier_mix,
                                   observed_engagement
```

It is persisted three places, all internal: the tick's corpus rows, the outbox
item's `source.scoring` block, and the daemon log. It is **never** written to
`wires.json` or any other user-facing surface — the rail builder copies named
display fields only.

To re-weight without re-polling anything, edit `breaking.scoring.rank_weights`
and re-run the eval over the stored corpus.

---

## 6. Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| `::notice story-spine-no-datasketch` | wheel not installed | expected today; install `datasketch` in the daemon venv to enable near-dup |
| `::notice story-spine-no-model-artifact` | semantic pass on, artifact missing | fix `model_path` or set `enabled: false` |
| `::notice press-garbage-gate::promo_spam=N` | the gate dropped N items | inspect `blocked` rows in the tick result; disable one detector if it is over-firing |
| `::warning scoring-brain-unavailable` | the whole layer failed to construct | lane fell back to salience-only ordering and kept publishing — read the exception name |
| `::warning breaking-relevance-features` | one item's features failed | that item carries `_components.features_error` and still scored/gated normally |
| eval prints `state: no-labels` | correct, not a failure | run the §2 labeling session |
