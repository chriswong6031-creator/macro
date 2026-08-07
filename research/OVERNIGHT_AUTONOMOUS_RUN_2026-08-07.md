# Overnight autonomous run — 2026-08-07

**Session:** Government Revenue Foresight build-out, continued autonomously while the operator slept.
**Scope granted:** "complete as much of the build-out as possible", everything pre-approved, no
check-ins. What follows is the honest record, including what did not work.

---

## NEEDS OPERATOR

These are the only things genuinely blocked on a human. Everything else either shipped or is
recorded below with its evidence.

1. **Publish the Wave 9D issuer-mapping candidate?** A live run on 2026-08-07 produced a candidate
   graph of **203 identifier edges across 101 legal entities for 19 of 21 issuers**, `withheld=0`,
   `admission=ready` (it loads clean through the real runtime loader). It is NOT published: the
   contract's `reviewState` enum is `confirmed | reviewed | analyst_approved` with no "proposed"
   member, which is the schema stating that the canonical graph is a **reviewed-only** artifact.
   `verification_state: reviewed` is an assertion a human makes. I will not self-approve 203 edges.
   - Worksheet (JSON + markdown) is regenerable at any time; see "How to reproduce" below.
   - To publish: review the worksheet, then run `scripts/curate_government_revenue_recipient_graph.py --input <candidate>`.
   - Two edges I would eyeball first: **AVAV → BlueHalo LLC** (verified correct — AeroVironment's
     own EX-21 lists BlueHalo, LLC / BlueHalo Labs, LLC / BlueHalo Innovations, LLC) and **NOC's 30
     identifiers**, which are 30 UEIs for ONE legal entity (`NORTHROP GRUMMAN SYSTEMS CORPORATION`)
     because SAM issues a UEI per registered establishment.

2. **An era break on the published track record is due, and it is not mine.**
   `tests/test_ob_mask_start_invariance.py::test_start_invariance` is RED on main — an
   `xfail(strict=True)` tripwire that fired **as designed** when #4732 re-anchored the timeframe grid
   to the absolute session calendar. It firing means the published track record moved and the era
   break is owed. Already owned by open PRs **#4942** and **#4934**; nothing for me to do but flag
   that it is real and waiting on your call.
   *(An earlier draft of this document claimed I had found a live canon violation here. That was
   wrong and is retracted in full below — I had read a worktree 330 commits stale.)*

3. **BWXT collects zero USAspending recipients.** Almost certainly a discovery-query defect rather
   than a true zero (BWX Technologies is a large naval-nuclear contractor). Diagnosis in flight.

---

## Corrections to things I previously told you

Recording these explicitly, because both were wrong when I said them.

- **"Wave 9G is next."** It was already built and merged — PR #4813, merged 2026-08-07T07:13:50Z,
  shipping `engine/government_revenue/candidate_grader.py`, a versioned preregistration, and its
  test suite. I verified it on `origin/main` myself. What I *did* contribute is below.
- **"I found a canon violation on the shipped track record."** I had not. I read
  `engine/confluence_tiers.py` in a worktree **330 commits behind `origin/main`**; the calendar
  `resample("{n}B")` I "found" was replaced by absolute-session anchoring in #4732. Retracted in
  full below, with the second error stacked on top of it (a direction generalised from a
  defense-heavy 12-name sample that the full 1,494-name panel does not support). My own notes name
  this exact failure — *run `git log origin/main -- <file>` FIRST* — and I did not.
- **"203 edges" as a coverage number.** That is an *identifier* count. The honest breadth figure is
  **101 legal entities across 19 issuers**. NOC alone contributes 30 identifiers for one company.
  Quoting 203 as though it were 203 companies is exactly the kind of impressive-sounding number this
  product exists to refuse.

---

## What shipped

| PR | What | State |
|---|---|---|
| #4782 | **Wave 9C** — award-event persistence recovery (the P0) | merged 07:12Z |
| #4776 | Wired **19 dark Government Revenue suites** into CI | merged 07:12Z |
| #4849 | **Wave 9D** — official-evidence issuer-mapping proposal tool | merged 08:20Z |
| #4906 | EX-21 picker missed EDGAR's bare-`x` separator | merged 10:25Z |
| #4794 | main-red heal — chat-nav drift | merged 07:13Z |
| #4827 | main-red heal — stale exit-policy horse race | merged 03:33Z |
| #4921 | Grader was missing its earnings/filings outcome labels | open, armed |

---

## Wave 9C — root cause, and why it was not what the handoff thought

The handoff's leading hypothesis was "a list-valued cell crossing a Parquet schema boundary."
**Nothing ever reached `to_parquet`.** It is a pandas 3.0 migration break:

```
collectors/usaspending_awards.py:1341  _ensure_snapshot_hashes
    out.loc[missing, "snapshot_content_sha256"] = [ ... ]
TypeError: Invalid value '['814c439cdeb3deed...', ...]' for dtype 'float64'
```

`snapshot_content_sha256` joined `SNAPSHOT_COLUMNS` at #4216; the committed
`award_snapshots.parquet` dates from #4182. `reindex` therefore materialises it as all-NaN
**float64**, and pandas 3.0 refuses the string write that pandas 2.x silently upcast. Latent since
#4216, fatal once the runner crossed the 2→3 boundary — `requirements.txt` pins only `pandas>=2.2`,
and 41 workflows share one mutable venv keyed solely by physical runner name.

**Why the review was misdirected:** `_safe_error` truncated the exception *suffix* — exactly where
`for dtype 'float64'` lives. The 800 characters that survived were receipt hashes, which reads
precisely like a Parquet problem. Truncate exception text from the middle, never the tail.

A **second instance of the identical hazard** was found by census in the same file
(`_ensure_award_keys`, `.at[idx, "award_key"] = "<string>"`) and fixed in the same PR. The cure
already existed in-house — `engine/china_standout_track.py` and `engine/board_ledger.py` both carry
a `_coerce_object_cols()` helper naming this exact TypeError. Grep for it before writing a third.

### Wave 9C is NOT yet live-verified

The fix is merged and confirmed present on `origin/main`, but **production still reports
`"availability":"projection_state_absent"`** and the award-event triad does not exist. Reason: no
nightly `daily.yml` collect has yet run the fixed collector. The in-flight daily
(`31138544929`) checked out `0412deb4d04`, which predates the 07:12Z merge, so it will fail at
persist again. `government-revenue-live.yml` does NOT collect — it only folds an already-committed
triad. **The next nightly on a post-merge SHA is what proves this.**

End-to-end proof that it *will* work, run against the live USAspending API into a scratch root
(the repo's ledgers were never written): triad materialises, generation binding matches the on-disk
pair, no `.tmp` leaks, baseline emits **zero** eligible events, and a second run over the same
accrued root adds **+0 rows** with an unchanged `projection_generation_id` — the declared schema
round-trips without fabricating source revisions.

---

## Wave 9D — the discovery half

`scripts/propose_government_revenue_recipient_graph.py` proposes a candidate graph from official
evidence only. The analyst-driven curate script remains the sole writer of the canonical graph; CI
asserts there is no second writer.

Chain, official end to end, needing **no schema change** (`publisher` already permits SEC and
USAspending.gov):

```
SEC company_tickers.json   ticker -> CIK      (SEC's own authority)
SEC submissions API        CIK -> latest 10-K (lookup only; data.sec.gov is NOT an
                                               allow-listed evidence host)
SEC EX-21                  -> subsidiary legal names
USAspending award record   -> recipient_name + recipient_uei
```

The join is exact equality after a normalization limited to case, punctuation, corporate-form
spelling, and a leading article. No edit distance, no token overlap, no containment, no score, no
LLM, no web snippet. `discovery_query_ticker` is never a join condition.

**Positive control:** run blind, it reproduces PLTR's two hand-reviewed UEIs (`FSY4LVSBGWB7`,
`HNN4F9JZWDY8`) and an independent fetch of PLTR's EX-21 reproduces `content_sha256
a139ad357b80c8de…` — byte-identical to the hand-curated evidence row already shipped.

**Negative control:** GE proposes **zero** edges. Its collected recipients are other companies
(`MARSHALL OF CAMBRIDGE AEROSPACE`, `PRESTIGE AEROSPACE LLC`) — discovery-query false positives.
Zero is correct and is reported as `no_exact_match`, never `mapping_needed`.

### Two defects the review and the live run caught

Adversarial review over three lenses returned **two BLOCKED** verdicts before this was fit to ship.

1. **The extractor made the tool assert something false.** `\binc\b`/`\blp\b` were tested against
   the RAW line, so `Incorporated` and dotted `L.P.` were silently discarded — and the tool then
   emitted *"This is a finished answer, not an outstanding mapping task"* for HII, whose exact match
   `HUNTINGTON INGALLS INCORPORATED` is present in the shipped `awards.parquet`. A wrong null wearing
   a finished verdict. Fixed by testing the vocabulary against the NORMALIZED line and adding
   `ex21_lines_extracted` / `ex21_lines_rejected` / `ex21_rejected_samples` so a zero is auditable.
2. **The EX-21 picker missed EDGAR's bare-`x` separator** — found only by running against live data.
   TXT reported `no_ex21_exhibit` against a filing whose EX-21 is `q4202510k-exx21.htm`. The
   separator class was `[-_.]?`. Fixed to `[-_.x]?`; Textron's own listing (seven `exx` siblings) is
   the regression fixture. Recovered TXT's 7 edges: 18/21 → 19/21 issuers, 196 → 203 edges.

Nine further defects from the same review were fixed with mutation proofs, including an `edge_id`
collision that would have made the **whole** artifact unloadable, a CLI that wrote an invalid
candidate and reported success, and `content_sha256`/`byte_length` — the tool's only falsifiability
mechanism — pinned by nothing at all.

**Pattern worth naming:** three separate defects in this one file were the same shape — a silent
filter converting a finished verdict into a phantom errand. The picker's own docstring already
records an earlier instance. Treat any silent filename/text filter here as guilty until it carries
an extracted/rejected counter.

---

## Wave 9G — already shipped; one gap closed

Wave 9G (#4813) shipped **six of the handoff's seven build items**. Item 4 — "earnings-window and
subsequent-filings outcome labels where available" — landed in neither registration 1.0.0 nor
2.0.0: `earnings` and `filing` had **zero occurrences** across module, preregistration, and suite.
Closed in **#4921** in place, rather than standing up a second grader the existing module's
docstring explicitly disclaims.

Decision worth your attention: `unavailable` is deliberately NOT `none_in_window`. The natural
implementation (a mapping returning `[]` for an unknown ticker) merges them **in the flattering
direction** — every issuer with the worst disclosure data would score as having the cleanest window.
This is the same denominator-conditioned-on-outcome sin `engine/track_scoring.py` exists to forbid.

Labels are held structurally outside the verdict, pinned by a test asserting the verdict block is
**byte-identical** with and without a calendar, because §7.2 derives N=545 from a power calculation
and a decision rule that grew a term would leave the registered N describing a statistic the
instrument no longer computes.

**The grader currently has nothing to grade** — zero eligible events, zero candidates — and that is
the correct state, not a failure. It returns a valid empty evaluation: `verdict_state: accruing`,
`issued/abstained 0/0`, `h63 hit_rate: None` (None meaning "no rate", not a zero).

---

## RETRACTED: the "canon violation on the shipped track record"

**I reported a defect that does not exist. Retracting it in full, with the cause.**

I read `engine/confluence_tiers.py:197` in a worktree that was **330 commits behind
`origin/main`** and found `_tf_bars` bucketing with calendar `daily.resample(f"{n}B")`. On current
main that function is already session-anchored —
`bucket(d) = session_anchor.session_positions(d, market) // n` — repaired in **#4732**
(`2a0c5e27184`, era `abs-session-2026-08-06`) with its own ruling doc
`research/SESSION_ANCHOR_ABSOLUTE_CALENDAR_ADJUDICATION_BY_FABLE.md`. The repair's own docstring
records the blast radius it fixed: one dropped leading bar flipped the tier on 13/232 names.

This is precisely the failure my own notes name — *stale worktree diagnoses a fixed bug; run
`git log origin/main -- <file>` FIRST*. I did not.

**A second, independent error on top of it.** I measured the divergence on 12 tickers and reported
that the calendar path fires overbought "more almost everywhere". Over the full broad panel (1,494
names, 940,756 ticker-days) the split is **819 names higher / 637 LOWER / 38 equal** — 56/44, with
only +1.4% relative difference. The magnitude of disagreement (6.78% of ticker-days) was real, but
**the sign is close to a coin flip**. My sample was defense-sector-heavy and overstated the
systematicity. The "over-firing exit systematically shortens holds and moves the published track
record downward" story is not supported at panel scale.

**What the investigation was actually worth.** Routing `_tf_bars` to `canon.resample_sessions` — my
proposed "fix" — would have been a **regression**. Measured over 1,185 name×start-offset pairs:

| grid | any-field flips under a dropped leading session |
|---|---|
| `_tf_bars` as shipped | **0 / 1185 — 0.00%** |
| `canon.resample_sessions` as a delegate | 152 / 1185 — **12.83%** |
| pre-#4732 calendar `{n}B` | 153 / 1185 — 12.91% |

`canon.resample_sessions` is as start-dependent as the calendar bin it would have replaced, and
carries no `market` parameter (it would bucket CN/HK/CA tapes on the US grid). Five production
consumers ride `_tf_bars`.

So the two implementations are **deliberately different anchors**, and canon.py's docstring law
("a concept computed two ways is a bug the moment the two disagree") had no guard behind it either
way. That guard now exists — **PR #4949** adds 8 tests to `tests/test_canon.py` pinning the
byte-for-byte tie on an aligned contiguous window, the never-a-calendar-bin regression, and
start-invariance holding for `_tf_bars` and explicitly NOT for canon, so neither can be silently
made a delegate of the other. Docstring-only change to `engine/canon.py`; no behaviour change, no
golden vector moved.

**Genuinely open, found during this work:** `tests/test_ob_mask_start_invariance.py::test_start_invariance`
is RED on main — an `xfail(strict=True)` tripwire that fired as designed when #4732 landed, meaning
the published track record moved and an era break is due. Owned by open PRs **#4942** and **#4934**.
Also `scripts/grade_us_board.py` (~:2272, :2290) still claims `_tf_bars` resamples on `3B`, which is
now stale prose; that file is in #4942's diff.

## What I deliberately did NOT do

- **Did not publish the Wave 9D candidate.** `verification_state: reviewed` is a human assertion.
- **Did not fix `test_intl_market_state`.** Two tests fail on main; one is clean date rot, but the
  other (`same event code on consecutive entries: crash_20d`) enforces the *first-crossing
  discipline*, and freezing a fixture at today's data would enshrine a possible real bug as the
  expected baseline. Handed off with that distinction stated; #4829 picked it up.
- **Did not force-merge during the GitHub Actions outage.** `ci-pack` runs on `ubuntu-latest`; all
  four jobs sat `queued` with no runner assigned. A head with zero non-spurious checks is unproven,
  not green. I substituted for CI locally instead — which caught a trigger-closure hole I had myself
  introduced into the CI-darkness PR, so the hold paid for itself.
- **Did not re-run the in-flight nightly.** House law: re-run only after an unsuccessful conclusion
  plus diagnosis, with one session owning the recovery.

---

## How to reproduce anything here

```bash
# Wave 9D candidate + review worksheet (live, official sources, writes nothing to the repo)
python3 scripts/propose_government_revenue_recipient_graph.py \
  --out-dir /tmp/9d --as-of 2026-08-07 --pace-seconds 0.35 \
  --user-agent "MastermindX Government Revenue research (contact: <you>)"

# Production truth (apex 301s to www — follow redirects or it reads as garbage)
curl -sL https://www.mastermind-x.com/api/health
curl -sL https://www.mastermind-x.com/api/government-revenue/candidates

# The canon divergence
python3 -c "from engine.confluence_tiers import _tf_bars; from engine.canon import resample_sessions"
```

---

## What I would do next, in order

1. **Wait for a post-merge nightly**, then verify the triad materialises and `projection_state_absent`
   clears. Nothing downstream is trustworthy until the event spine actually persists once.
2. **Review and publish the Wave 9D candidate** — that is what moves 20 companies off
   `mapping_needed` and gives the grader a universe to attribute events to.
3. **Land the canon fix** once you have seen how far the track record moves.
4. **Raise the award-query caps.** 19 of 21 queries truncate at `max_pages_per_entity: 2` with
   `hasNext=true`, so `source_exhausted` can never be true and the baseline is built on a truncated
   universe. Diagnosis in flight with measured request cost.
5. **Then Wave 10 rails** (IDV child bridge, DoD budget graph, SBIR, SAM lifecycle, recompete) —
   but only after the grader has real candidates to grade, because rails without a grader are
   surface area without evidence.

Zero candidates remains the correct, honest output today.
