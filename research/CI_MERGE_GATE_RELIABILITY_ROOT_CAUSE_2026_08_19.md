# The merge train stalls because main is green 44% of the time

**Status:** diagnosis COMPLETE and reproducible; remediation NOT started (§4 is the program).
**Measured:** 2026-08-19. Reproduce with `python3 scripts/ci_gate_reliability_report.py`.
**Occasion:** 24 open pull requests, a backlog running ~2 weeks, and an operator report that
session compute has roughly doubled because sessions spend it repairing CI rather than building.

---

## §0 Acceptance gates for the remediation

Not done unless:

1. `python3 scripts/ci_gate_reliability_report.py` shows main's green rate **above 90%** over a
   trailing 100 runs, measured at least 72h after the change lands.
2. A pull request that touches only `engine/**` + `tests/**` merges **without any session
   healing main**, twice in a row, with the sweep log showing no `baseline-blocked` and no
   `main-red-repair` in between.
3. Every job moved off the merge gate still **runs** and still **reds something a human reads** —
   a `data-health` check, an issue, a dashboard row. Moving a receipt off the gate must not
   delete it. A silent drop is a failed gate, not a passed one.
4. The count of jobs moved is **logged explicitly** in the PR body, by name. No silent caps.

---

## §1 The two numbers

```
main green rate: 44/100 = 44.0%   [2026-08-09T15:32Z -> 2026-08-19T05:46Z]
  conclusions: {'failure': 45, 'success': 44, 'cancelled': 11}
  (main's OWN ci.yml runs — no pull-request diff in any of them)

merge-gate legacy jobs: 194
  assert against the committed data tree: 130
  code-only:                              63
  => 67% of classified merge-gate jobs are data-coupled
```

`main`, carrying no pull request at all, fails its own gate **more often than it passes**.

That is the whole problem. It is not the sweeper, not any one test, and not sessions being
careless.

## §2 Why 44% produces a two-week backlog

Every mechanism downstream of the gate assumes main is usually green:

- **`merge_on_green` never merges a red head**, even when the red is inherited. That is correct
  behaviour — it cannot tell a genuinely broken head from an unlucky one — but it means a PR
  inherits main's state.
- **The base-inherited excuse needs a fresh green proof of main** to compare against. Below ~50%
  that proof is routinely stale or itself red, so the excuse is unavailable exactly when it is
  needed.
- **`ship_loop_guard.py` asks the same question** and gets the same answer, so it tells the author
  to fix a red the author cannot reach.

So each session arrives, finds its PR red on something it did not cause, and pays to heal main
before its own work can land. **That toll is the doubled compute.** It is not waste inside a
session; it is main's repair bill, charged to whoever happens to be merging.

## §3 Why healing individual reds cannot converge

The failing set **rotates faster than a heal cycle**. Measured live on 2026-08-19:

| time | main's red |
|---|---|
| 04:47Z | `capital-structure-intelligence` |
| 05:15Z | healed and merged (#5930) |
| 05:46Z | `market-memory-contract`, `unrun-prophet-learning-loop`, `signal-contract` |

Three *different* jobs, one hour later, on main itself. A pack heal takes ~35 minutes; the nightly
pushes ~250 commits a day. Per-red healing is chasing a target that moves faster than the chase.

The reds are not code defects. Every one diagnosed on 2026-08-19 was a data or environment
condition:

| red | actual cause |
|---|---|
| `capital-structure-intelligence` | GitHub tool cache moved CPython 3.12.13 → 3.12.14, past a stdlib-source allowlist. Rolled out **per VM**, so the same commit passed or failed by which runner picked it up. |
| `signal-contract` price ladder | CEG paid a dividend, so a hardcoded "non-payer" control name stopped being a non-payer. |
| `unrun-prophet-learning-loop` | `data/baskets/ohlcv/ASTS.parquet` is one session stale, so the ladder fell to the next rung. |
| `house-law-registry` | `VMRK` absent from `2026-08-10.parquet` with no alias boundary. |

A pull request cannot make yesterday's dividend calendar agree with today's parquet. These are
legitimate instruments pointed at real conditions — they are simply not **merge preconditions**.

## §4 The arithmetic, and therefore the fix

With `N` data-coupled jobs each carrying probability `p` of being wrong-footed by a data change in
a given window, `P(all green) ≈ (1-p)^N`. At `N = 130` and `p ≈ 0.6%`, that is ~46% — the observed
rate falls straight out of the coupling count. **You cannot make 130 assertions over moving data
simultaneously green often enough to merge through.** Adding retries, widening tolerances, or
healing faster all lose to the exponent.

The fix is to change `N`, not `p`:

> **A pull request's merge gate tests the pull request's code against pinned fixtures.
> Assertions over the live committed data tree run in a data-health lane, after the nightly,
> and red an issue — not the merge gate.**

### Staged plan

- **W1 — classify.** Extend `.github/ci/legacy-jobs.yml` with an explicit per-job
  `gate: code | data` field. `scripts/ci_gate_reliability_report.py` already produces the
  candidate split; it is a starting point for judgement, **not** the answer — a job that reads
  `data/` to build a fixture is code-gated, and a job that reads a pinned golden is code-gated.
  Deliverable: every job carries an explicit field, with the count and the by-name list in the PR
  body.
- **W2 — split the lane.** `run_ci_pack.py` packs `gate: code` jobs into the packs `ci-gate`
  requires. `gate: data` jobs move to a `data-health.yml` workflow triggered after the nightly,
  whose failure opens or updates ONE issue naming the jobs. Nothing is deleted.
- **W3 — prove it.** Trailing-100 green rate above 90%; two consecutive ordinary PRs merged with
  no intervening `main-red-repair`.
- **W4 — keep it.** A test asserting that no `gate: data` job is reachable from `ci-gate`, so the
  split cannot silently erode.

### The trap W1–W4 must plan around

Any PR touching `scripts/**`, `.github/workflows/**`, `.github/ci/**`, or `.claude/hooks/**` sets
`authority_changed=true`, which **removes the base-inherited excuse entirely**
(`scripts/ci_authority_paths.py`). Every PR in this program is authority-changing. So the fix for
the problem is gated on the problem: it can only land in a fully-green window, which the 44% rate
makes rare.

Practical consequence: **land each wave in the smallest possible PR, and check main is actually
green immediately before merging.** Merging an authority-changing PR while main is red buys a
permanently unclearable stop gate — the merged head's checks are frozen, and descendant healing is
disabled by design for authority-changing PRs.

## §4b Operator authorization for the session that executes this

Recorded verbatim in intent from the operator on 2026-08-19, after being shown the §1
measurement:

> *"create hand off for this … And authorize Fable in the hand off access to do anything,
> including admin privilege, squash merging, with primary focus on fixing this once and for all
> from the root as per your diagnosis. and allow them to also freely diagnose if any other bugs
> exist."*

Concretely, the executing session is authorized to:

- **`gh pr merge --admin --squash`** its own waves, including while main is red, when the reds
  are provably not the PR's. Standing house law reserves `--admin` for "genuine wedges"; the
  operator has ruled that this program IS the wedge. Record the justification in the PR before
  using it, naming the inherited reds by logical job.
- **Merge without waiting for a full-green window**, which the 44% rate would otherwise make
  a coin flip per attempt.
- **Diagnose and fix anything else it finds**, in any lane, without opening a separate
  authorization. If a fix belongs to another lane, prefer a comment naming the owner over a
  silent patch — but do not let lane etiquette block the root fix.
- **Disarm, re-arm, rebase, or close** any pull request that stands in the way, provided the
  house rule holds: a disarm leaves a visible marker naming the session and the intent.

What is NOT authorized, and does not become authorized by this note: rotating or reading
secrets, force-cancelling protected production lanes (`daily.yml`, `render.yml`,
`closing-bell.yml`, `asia-close.yml`, `engine-render.yml`, `weekly.yml`, `prophet-rescue.yml`,
`nightly-liveness.yml` — the `gh_quota_guard.py` shape-6 set), re-stamping `data/**` receipts
from a pull request (nightly is the sole ledger advancer), or widening a tamper-detection
allowlist to turn a check green.

## §5 Already landed (2026-08-19)

| PR | what | effect |
|---|---|---|
| #5930 | pin `ci.yml` to CPython 3.12.13, the newest release the parser allowlist carries; guard test enforcing pin-before-allowlist ordering | removes the per-VM interpreter coin flip |
| #5922 | 4-hourly `schedule:` keepalive on `integration-baseline.yml` | stops the circuit breaker self-locking on a quiet main (~1×/night) |
| #5937 | price-ladder control asserts the back-adjustment signature instead of four hardcoded non-payers | removes one recurring data-driven red permanently |

These are real removals of specific generators. They do not change `N`, so they do not move the
44%. §4 is what moves it.

## §6 Do not redo

- **Do not diagnose a fleet-wide red from the PR diff.** Check the environment first —
  `pythonLocation`, runner image, tool versions — then main's own newest run, then sibling heads.
- **Do not widen a tamper-detection allowlist to make CI pass.** Trusting whatever the runner
  happens to have is the one thing such an allowlist exists to prevent.
- **Do not re-pin a data-derived constant** (a ticker list, a close, a fixture row) to today's
  value. It re-arms the same trap for the next data event. Assert the mechanism instead — see
  #5896 and #5937 for the shape.
- **Do not "fix" a red that is correctly reporting a data condition.** `ASTS` resolving on the
  `yahoo` rung is the ladder working; the baskets store being a session stale is the finding.
- **Do not chase a rotating red set per-pack.** If main's failing jobs differ between consecutive
  baselines, per-pack healing is structurally losing; measure the class instead.
- **Do not conclude the sweeper is broken** because PRs are not merging. It has run every ~2
  minutes throughout this backlog. Read its log line: `main proof: N clean name(s)` next to
  `baseline is pending` means main is fine and the breaker is stale; `classification=unknown`
  means the semantic replay could not check out the base (#5916).

## §6b The four roots red on main as of 2026-08-19 07:00Z

Tracked on issue #5935. Characterised, with the verdict for each:

| root | cause | verdict |
|---|---|---|
| `signal-contract` | CEG paid a dividend, so a hardcoded "non-payer" control name stopped being one | **fixed — #5937**, green on that PR's head |
| `market-memory-contract` | the fixture froze the ratio's numerator (`n_members` @ 2026-08-07 = 504) and left the denominator live (`constituents.parquet` = 503), so coverage reads 1.0020 and fails the `<= 1.0` bound. Live-vs-live is 502/503 = 0.998 and passes | **test defect, fixable.** `_FROZEN_FIXTURE_SESSION` is duplicated in `tests/test_market_memory_breadth_observation.py:46` and `tests/test_market_memory_breadth_store.py:35`; two 64-hex digests at `..._observation.py:277` and `:316` may be digests of the frozen body. Do NOT just advance the constant — that re-arms for the next reconstitution |
| `house-law-registry` | the symbol-directory snapshot collector wrote nothing after 2026-08-10, so the guard checked today's universe against a 9-day-old listing and reported the new S&P constituent `VMRK` as unresolvable | **root already fixed by #5936** (merged 2026-08-19T07:10Z): the live Nasdaq listing `NA` (Nano Labs) parsed as `NaN`, so the completeness guard refused the whole day's snapshot. Clears on the next nightly that writes a snapshot; verify `data/symbol_directory/manifest.json` shows `last_snapshot_date` past 2026-08-10 and `n_symbols` non-zero |
| `unrun-prophet-learning-loop` | `data/baskets/ohlcv/ASTS.parquet` ends 2026-08-17 while `data/yahoo/ASTS.parquet` reaches 08-18, so the ladder fell from rung 1 to rung 2 | data-plane. Both rungs are in `ADJUSTED_SOURCES` and the sibling invariant still holds, so **do not loosen the test** — it is correctly reporting a stale store |

Two of the four are the **same real-world event**: the S&P 500 reconstitution around 2026-08-18
(Reddit replacing AvalonBay; post-merger Vivmark). One index change, two guards firing in two
lanes. That is the §4 thesis in miniature — the gate is coupled to the world, not to the diff.

## §7 Open, not addressed here

- **#5916** — the semantic base replay cannot check out base SHAs in the blobless partial clone,
  so reds classify `unknown` instead of base-inherited. Fixing it does not raise the green rate,
  but it makes the diagnosis instant for every session that hits one.
- **`unrun-intl-libraries`** — `check_theme_graph_contracts --selftest` prints `OK` and *then*
  aborts at interpreter shutdown (`terminate called without an active exception`, exit 134), a C++
  teardown bug in a native extension. A step whose verdict passes and whose process then crashes
  reads as a contract failure forever.
- **#5935** — the two remaining roots of the 2026-08-19 main red (`market-memory-contract`,
  `unrun-prophet-learning-loop`), both in other lanes.
