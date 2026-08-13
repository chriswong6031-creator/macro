# W3 — Risk Center crops, and every delta from the pinned design

The pinned design is `mockups/refs/psi/workspace/workspace.html` + `DESIGN_NOTES.md`
(now on `main`). This file is the W3 implementation's side of the record. The rulings
this build establishes are folded into `DESIGN_NOTES.md` §7(g) rather than left here,
for the reason W2 recorded and this wave acted on: a builder reads the pinned design,
not the crop folder.

---

## 1. How the crops were taken

`shoot_w3_crops.py`, beside this file. 40 PNGs at 2× device scale, viewports 1440×900
and 390×844, in all five variants (desktop dark EN · desktop light EN · desktop ZH ·
390 dark EN · 390 ZH).

Every shot renders `templates/watchlist.html.j2` through the same builder context
`scripts/build_site.py` injects, and runs **the page's own scripts** against the **real
nightly artifacts** in `site/`. Nothing is staged: the seed puts a BOOK in
`localStorage` — the same store a real visitor's book lives in — and every figure on
screen is the page computing over that book.

Two departures from the W2 harness, both deliberate and both recorded in the script:

1. **ROOT is derived from the file's own location.** W2's `shoot_crops.py` hardcodes an
   absolute path into a worktree that no longer exists, so it cannot be re-run. This one
   runs wherever it is checked out.
2. **The Risk Center shots are ELEMENT crops of `#ws_sec_rc`.** The subject of this wave
   is one panel; a 2× full-page shot of a twelve-position workspace buries it and costs
   ten times the bytes. State 08 is the one full-page shot, because there the whole page
   is the subject.

| # | state | proves |
|---|---|---|
| 01 | Concentration | the single-name claim + the risk ladder, unchanged from W2 |
| 02 | Correlation | the closest pair printed with its number even though none crosses 0.70 |
| 03 | Factors & macro | the force the book leans on, the rate line, the grouping caveat |
| 04 | Stress | the calm↔falling-days comparison, in both directions |
| 05 | Events | the calendar, and what it says it did not read |
| 06 | Weak links & strengths | risk per dollar on one shared scale + the diversifier |
| 07 | Scenario Lab, expanded | a real comparison run through `RiskCore.whatIf` |
| 08 | full portfolio, EMPTY watchlist | the defect-3 case: a real factor read reaches the page |

### What the harness asserts rather than leaves to the eye

The script exits non-zero on any of three conditions, so these are regressions with a
name rather than things a reviewer must re-check:

- **No page errors** in any variant.
- **Zero page-level horizontal scroll at 390px on every tab** (`scrollWidth - clientWidth
  == 0`), including the Scenario Lab open. The tab strip scrolls inside `.rc-tabs`; the
  page never does.
- **No tab rendered the thin-book fallback.** See §3 — this check exists because the
  first run produced six perfectly rendered EMPTY tabs and would otherwise have shipped
  them as evidence.

---

## 2. Deltas from the pinned design

**W3-D1 — The Scenario Lab keeps the `$10,000` default; the mockup shows an average-position
default.** The pinned copy reads "Sizes start at $15,350, your average position, and you
can change it." The build keeps the existing `W4_DEFAULT_DOLLARS = 10000` and explains it
instead: "a round number makes two runs comparable — it is not drawn from your book and it
is not a suggested size."

Reason, and it is a product judgement worth the commissioning session's attention: a
default derived from the reader's own average position is a number *about their book*,
and a number about their book sitting in a size field reads as a suggested size — which
is exactly what WRI-R3 forbids and what the handoff flagged the contextless $10,000 for.
A round constant cannot be mistaken for advice once it says it is a round constant. The
packet's instruction to this wave was to state the existing default, not to change it, so
the change was not taken as a builder decision. **If the commissioning session prefers the
mockup's average-position default, it is a one-line change** (`W4_DEFAULT_DOLLARS` becomes
a function of the book) plus its copy.

**W3-D2 — The five "being built" shells became thin-book fallbacks, not deletions.** The
mockup has no state for a book too thin to read. Every tab keeps its question in plain
words and adds "Add at least two positions the nightly model covers and this fills in."
A tab never shows an empty panel and never borrows another tab's answer.

**W3-D3 — Tier-2 receipts ride the sentence; the `?` glyph is gone.** The first build used
`.wri-q` (the braid hero's affordance). W2 deleted the braid hero and its CSS, so it
rendered as a bare question mark hanging off the end of a line — visible in the first crop
run. The receipt now uses the page's own `data-tip-en`/`data-tip-zh` pattern with a dotted
underline. Recorded because it is a rule for later waves, not a one-off fix.

**W3-D4 — Weak links draws its two bars on ONE shared scale.** The first build normalised
money and risk independently. The name with the largest money drew a full bar, the name
with the largest risk drew a full bar, and NVDA — the name the headline was about, at 13%
of the money and 19% of the risk — drew neither. The picture contradicted the sentence
above it. Caught in the crops, not in the tests.

**W3-D5 — The factor ladder gets a wider label column (`.conc.is-factors`).** Factor names
are words, not tickers: "Growth / Tech" wrapped to two lines at the ticker width and broke
the ladder's rhythm.

**W3-D6 — `portfolio.js`'s FX seeding workaround is retired.** W2 could not touch
`factor_exposure.js`, so it worked around the empty-watchlist defect from the caller. W3
fixed the guard at the mechanism, so the workaround is removed: two independent guarantees
of one property is how a mechanism fix goes untested, since with the seeding in place the
guard is never the thing carrying the case in production. Both halves are pinned.

---

## 3. One honest limitation, stated plainly

**The per-ticker artifacts in this environment are a mix of real and fixture data.** This
is the same limitation W2 recorded (several names carry a placeholder close of exactly
`100.00`), and it is visible in the Events crops: MSFT, AVGO, XOM, **GLD and TLT** all
carry `next_date = 2026-08-27, after-hours` in `site/stockdata/*.json`. GLD and TLT are
ETFs and do not report earnings at all, so those rows are artifact fixture values, not a
real calendar.

The Events tab is rendering faithfully what the artifact says, from the same `earnings`
block the per-name drawer's events lane already reads. **No filter was added.** Dropping
ETFs would mean inventing a rule inside a presentation wave, and `is_etf` is not even
reachable for a name the factor model does not cover. The crops are the real page over
the artifacts it was given — computed, not authored — but those particular dates are not
production values.

**A second, sharper version of the same hazard, and the reason the harness now fails on
it.** `site/stockdata/` is an untracked nightly artifact directory (1,630 files in the
main checkout). A fresh agent worktree has none of it, and the page degrades exactly as
designed: no per-ticker JSON → no last close → `portfolio.js` can price no position → no
dollar weights → the factor read never runs → every tab renders its honest thin-book
fallback. Nothing looks broken, which is the danger — the first run of this harness
produced six beautifully rendered empty tabs. The script now links the directory from the
main checkout for the duration of the shoot (removing the symlink afterwards, since an
untracked symlink blocks the ship-loop guard) and **fails if any tab still renders the
fallback**.
