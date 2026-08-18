---
key: REBASE-SPLICES-RENDERS-INTO-A-PAYWALL-LEAK
claim: >
  A tier-gated page shell can publish a PAID row with every gate check correct, because
  the leak is manufactured after the render, by git. Every render lane pushes through
  `git pull --rebase --autostash -X theirs origin main` (closing-bell.yml:611,
  scripts/ci/push_retry.sh). `-X theirs` decides only CONFLICTING hunks; non-conflicting
  hunks from BOTH generations survive the 3-way TEXT merge, so when two renders of the
  same page race, git assembles a file NEITHER render emitted. Measured 2026-08-18
  (33f7bdde0c3a): site/us_stocks.html shipped a card grid of FOUR rows against its own
  `preview: 3`, the 4th being row 0 of the LOCKED payload (ONTO), while its own
  #us-stocktable-data still held the previous generation's three — which additionally
  published that same locked row's FULL paid record (conviction, alpha, factor_z, sue_z,
  entry status). scripts/build_site._split_us_board was correct throughout and 28 of the
  29 tests in tests/test_us_board_gate.py passed; only the shipped-BYTES assertion failed.
falsifier: >
  `git check-attr merge -- site/us_stocks.html` stops printing "merge: unset" (the
  .gitattributes rule added by #5857 removed or narrowed), or the lanes stop rebasing
  render output onto a moving main — .github/workflows/closing-bell.yml:611 and
  scripts/ci/push_retry.sh — via a whole-file checkout of site/ after rebase, a render
  concurrency group that serializes page writes, or dropping `-X theirs`. Any of these
  moves where the splice can occur. The mechanism itself is falsifiable in six commits:
  `git init t && cd t && seq 1 40 > page.html && git add -A && git commit -m base`, branch
  A edits line 3, branch B edits line 38, then `git rebase -X theirs B` from A — WITHOUT a
  `-merge` attribute the result contains BOTH edits (a state neither branch had); WITH
  `page.html -merge` in the base commit it contains only A's. If that ever yields one
  generation without the attribute, this record is wrong.
so_what: >
  A gate suite that only asserts on the RENDERER cannot see this class. Hermetic tests
  (fake rows, real templates) stay green while the shipped bytes leak, so the
  shipped-artifact assertion is the load-bearing one and must never be relaxed to make
  main green. Two diagnostic rules follow. (1) When one artifact is internally
  inconsistent — two blocks that read the same source disagreeing — suspect the MERGE,
  not the generator; cross-generation drift is provable from the artifact alone (the
  payload's ONTO card renders Priority 63 against board prophet.score 63.1, the shell's
  renders 67; the shell's stocktable row carries conviction 62 against the board's 56).
  (2) BISECT READS BACKWARDS on this class: the "last good" commit 352326447a4d is the
  bad commit's rebase BASE, so bisect fingers the render that got spliced rather than any
  code change, and a session that trusts it will hunt a renderer bug that does not exist.
  Also: enumerate EVERY block that serializes gated rows when writing a leak check — the
  original assertion greps `data-ticker="TK"` while the JSON island spells the key
  `"ticker"`, so the richer leak was invisible to it.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  site/factordata/us_standouts.json (buy = [DAR, EWBC, EW, ONTO, ...] x 71, ONTO at
  index 3) against site/premiumdata/us_stocks.json (preview=3, locked=68, total=71,
  rows[0].ticker=ONTO) — i.e. exactly _split_us_board(board, 3), so the classification
  was right; scripts/build_site.py:4861 (_split_us_board, a clean [:n]/[n:] slice);
  templates/dashboard.html.j2:15897 (`_board = _su.buy`) and :15856 (#us-stocktable-data
  iterating the same `_su.buy`) — one source, so a 4-vs-3 disagreement is not renderable;
  `python3 -m pytest tests/test_us_board_gate.py -q` = 28 passed / 1 failed pre-fix;
  .github/workflows/closing-bell.yml:611 (the rebase);
  `git log -1 --format=%p 33f7bdde0c3a` = 352326447a4d (single parent — a rebase, and the
  bisect's own "last good" commit).
  Fix verified: PR #5857 — .gitattributes `-merge` on the four gated shells
  (`git check-attr merge` = unset), shell rebuilt through the template's own Jinja block
  and asserted equal to build_site._us_board_row_flat(), and two regression tests that
  FAIL on the spliced bytes (`assert ['ONTO'] == []`,
  `assert ['DAR','EWBC','EW','ONTO'] == ['EWBC','EW','ONTO']`) and pass on the repaired
  ones; tier-gate step 90 passed.
scope: [macro]
confidence: verified
---

## Detail

The gate was designed against the renderer and is sound there. What it did not model is
that `site/**.html` is *whole-file* output whose two halves can be recombined by a tool
that has no idea what a paywall is.

`-X theirs` reads like "take my version", and that is the trap: it governs only hunks git
considers to be in conflict. Two renders of a 650 KB page touch mostly disjoint regions,
so almost nothing conflicts — the board grid comes from one render, the JSON island from
the other, and both are "successfully" merged. The result passes every structural check
(valid HTML, balanced tags, plausible-looking blocks) and only fails an assertion that
compares the shipped bytes against the payload's declared split.

The repo already understood this hazard for *ledgers* — `.gitattributes` carries
`merge=union` for append-only JSONL with a comment naming this exact push loop, and
explicitly notes that whole-file JSON documents must NOT be union-merged. Generated HTML
had no rule at all, so it silently took the default 3-way text merge. `-merge` is the
correct third answer for this class: not union, not text-merge, but *one generation
wins*. Losing the older render is not data loss — it is superseded, and the next lane
re-bakes the page regardless.

Blast radius beyond the board: any generated page can be spliced this way. The
consequence is only a *paywall* leak where the page is tier-gated, which is why the
`-merge` rule is scoped to the four gated shells (us_stocks, etfs, special_situations,
china_special_situations) rather than all of site/ — a broader rule would also change how
concurrent edits to hand-authored pages (lib/pages.HAND_AUTHORED_PAGES) resolve, which is
a separate call with its own tradeoff. On any other page the same splice produces a
mixed-generation display bug, not a disclosure failure.
