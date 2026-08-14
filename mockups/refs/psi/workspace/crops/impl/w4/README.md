# W4 — Intelligence Drawer crops, and every delta from the pinned design

The pinned design is `mockups/refs/psi/workspace/DESIGN_NOTES.md` §7(a)–(g) + the CEO
handoff §10 content spec + packet §5's wireframe drawer block. There is no separate
drawer mockup and none was required: §7 pins the grammar, §10 pins the section list, and
W3 already styled all five classes the drawer's lane renderer emits — so W4 inherited a
working surface and the crops below are the visual evidence, not a comparison against a
static artifact.

Rulings this build establishes are folded into `DESIGN_NOTES.md` §7(h) rather than left
here, for the reason W2 recorded and W3 acted on: a builder reads the pinned design, not
the crop folder.

---

## 1. How the crops were taken

`shoot_w4_crops.py`, beside this file. 25 PNGs at 2× device scale, viewports 1440×900
and 390×844, in all five variants (desktop dark EN · desktop light EN · desktop ZH ·
390 dark EN · 390 ZH).

Every shot renders `templates/watchlist.html.j2` through the same builder context
`scripts/build_site.py` injects and runs **the page's own scripts** against the **real
nightly artifacts** in `site/`. Nothing is staged: the seed puts a BOOK and a WATCHLIST
in `localStorage` — the stores a real visitor's state lives in — and every sentence on
screen is the page composing over those artifacts.

**The row arithmetic, because every count below rests on it.** `WRI.intelSections` — the
shared composer — emits **15** rows: the seven lanes, then Distance from trend, Portfolio
role, Options, Macro sensitivity, Sector & theme, Ownership, Company notes, Transmission.
A **holdings** drawer adds one more, Stage, from `portfolio.js` (it needs
`portfolio_ctx.json`, which only the holdings path loads — see §3a), so scenes 02 and 03
are **16** rows and the watchlist scene 04 is **15**. Earlier versions of this file said
15 everywhere and were wrong by exactly the Stage row in two of the three scenes.

| # | scene | proves |
|---|---|---|
| 01 | Tier 1, alone | the glance read is one plain sentence + one stance word, and nothing else |
| 02 | Tier 2, expanded (AAPL, holdings) | **16 rows: 15 real, 1 coverage gap** (Events — the date is past). No evaluated-negative in this scene: AAPL's Transmission row sits downstream of an armed chain tonight and reads WATCH |
| 03 | degraded name (RIVN, holdings) | **16 rows: 7 real, 8 coverage gaps, 1 evaluated-negative** (Transmission — in no armed chain) — honest degradation over a real 50KB artifact |
| 04 | the same name (AAPL) from a WATCHLIST row | **15 rows: 13 real, 1 gap** (Events)**, 1 structural** (Portfolio role — "not a position", never an invented weight). One row fewer than scene 02 because Stage is holdings-only |
| 05 | the anonymous drawer | a lock shell, zero lane rows, zero gated signal |

### What the harness asserts rather than leaves to the eye

The script exits non-zero on any of these, so they are regressions with a name rather
than things a reviewer must re-check:

- **No page errors**, in any variant.
- **Zero page-level horizontal scroll at 390px with a drawer open.** The drawer is the
  widest thing on the page; the row grid collapses to two columns and the read wraps
  under it.
- **No drawer row renders a blank read.** A `.wri-lrow` with an empty `.rs` is the
  silent-empty failure this whole wave is about.
- **The rich name's drawer contains at most `RICH_MAX_NA` (3) coverage gaps** — AAPL in
  scene 02 measures **1 of 16**, and
- **the sparse name's contains at least `SPARSE_MIN_NA` (5), but not all** — RIVN in
  scene 03 measures **8 of 16**.

  Both counts are `.st.na` — the COVERAGE-GAP mark only. Since m8 the drawer distinguishes
  three coverage meanings (see §3a), so `none` (evaluated, answer is none) and `n/app`
  (does not apply to this row) are answers and are counted as real rows, not as gaps.
- **Neither scene is shot over a stub.** `assert_not_stub_grade` refuses any artifact under 20KB or missing a `tech` block, before the browser starts.
- **The large-list law, measured on a 100-name list** (no crop): twenty drawers opened
  and closed again. `100 -> 100` rows, 20 drawers open at once, 0 surviving their own
  close. Asserted because the failure here is gradual rather than obvious — the drawer
  is emitted by the row renderer, so every toggle re-renders the table, and a
  composition that got expensive would show as a table quietly losing rows. Wall time
  is 17.4s, of which 16.8s is the harness's own 420ms settle after each of the 40
  toggles; the composition itself is string concatenation over an object the page
  already holds, and adds no fetch.

Those middle two are the gate that matters, and §2 is why.

---

## 2. The false green this harness exists to refuse

W3 recorded that a bare agent worktree has no `site/stockdata/`, so the page degrades as
designed and photographs as a working page with a thin book. W4 inherits that hazard one
level sharper.

**Every section of this drawer has an honest-absence line.** That is the wave's headline
requirement. It also means a drawer composed over `null` renders thirteen well-worded
rows that all say "not covered tonight" — a screenshot indistinguishable from a working
drawer on a quiet name, produced by a run with no data in it at all. The wave's success
criterion and its total failure look the same.

So the assertion is two-sided. The rich name must render **almost no** absent rows; the
sparse name must render **some and not all**. A run where every row is honest is a run
with nothing behind it, and it exits 1. `link_nightly_artifacts()` borrows the 1,630
per-ticker JSONs from the main checkout for the duration of the shoot and removes the
symlink afterwards (an untracked symlink blocks the ship-loop guard).

**The first version of this scene was shot over a stub, and the crop could not show it.**
TLT's artifact in this directory is **1,354 bytes against a 59,273-byte median** — one of
16 stub-grade files here — so the "degraded name" scene was photographing a broken FILE
rather than a sparse name. The rationale written in this README for choosing it ("carries
macro sensitivity and ownership filings") was falsified by its own crop: the stub has
those KEYS but not the nested fields the rows read (`macro_sensitivity.headline.en`,
`smart_money.n_holders`), so both rendered n/a. A plausible ticker name and a plausible
crop hid a scene with no data in it.

The replacement is chosen by **measuring every artifact in the library** with the same
composer the DOM gets, not by picking a plausible ticker. Over the 1,613 real-size
artifacts the absent-section count runs 2..13. **RIVN** is a real 50KB artifact whose
holdings drawer renders **7 real rows, 8 coverage gaps and 1 evaluated-negative** (gaps:
Events, Estimates, Balance sheet, Who's selling, Rate sensitivity, Options, Macro
sensitivity, Ownership; evaluated-negative: Transmission). **AAPL** renders **15 real
and 1 gap** in the holdings scene and **13 real, 1 gap and 1 structural n/app** in the
watchlist scene, where Portfolio role does not apply and Stage is not loaded.
`assert_not_stub_grade()` refuses the whole class of file that made the first attempt
meaningless — size AND field presence, because a file can be big and still not carry what
a scene claims.

### Which of these figures is machine-derived, and which is not

The previous version of this paragraph ended "every figure here is per-scene and matches
the crop named beside it" — a sentence that certifies itself, and which then survived
three review rounds while the counts beside it were wrong. It is replaced by the actual
division of labour:

- **Asserted mechanically, so a regression fails the run**: the `.st.na` (coverage-gap)
  counts against `RICH_MAX_NA` / `SPARSE_MIN_NA`, the "not entirely gaps" bound, the
  total row count against a floor of 12, zero blank reads, exactly one Tier-1 block, the
  anonymous drawer's zero lane rows and its lock shell, zero page errors, zero
  page-level horizontal scroll at 390px, and the 100-name list's `100 -> 100` rows /
  20 opened / 0 surviving close.
- **Printed by the run, not asserted**: the per-scene `INVENTORY` lines — total rows and
  the label of every gap, evaluated-negative and n/app row, taken off the live DOM by
  `drawer_rows()`. Every count in this file's scene table and in the paragraph above is
  transcribed from those lines. They are machine-derived but not gated, so a future
  change moves them silently — re-run the harness and re-transcribe rather than
  reasoning about them.
- **Hand-written, and therefore the part to distrust**: the *reasons* beside each count
  ("the date is past", "in no armed chain"), the library-wide distributions quoted in
  §3a and in the round-3/round-4 sections, and every sentence of prose in this file.

---

## 3. Deltas from the pinned design, and the defects found while building

**W4-D1 — the `⌄` on a holdings row never opened its drawer.** `portfolio.js`'s row
handler returns early on `tgt.closest('button')`, and `data-row-exp` is on a button — so
the one control the design points at ("row ⌄ → PER-TICKER INTELLIGENCE DRAWER", packet
§5) was the one control that did nothing. It looked live because the chevron rotation is
CSS driven by `aria-expanded`, which the renderer sets from `openDrawers`. The expand
button is now handled before the generic bail. The watchlist table's own delegation
already handled `[data-exp]` first, which is why only this half was dark.

**W4-D2 — the anonymous holdings table had an empty affordance cell.** `renderAnonTable`
emitted `<td class="c-exp"></td>`: a column reserved for a control that was never drawn,
for exactly the audience the acquisition funnel is for. It now carries the `⌄`, and the
drawer it opens is the `.lockshell` — nothing gated is computed because none of the
gated scripts is on the page to compute it. Its links row drops "Remove from this list":
a pasted book is not a list, so there is nothing to remove from.

**W4-D3 — the dossier link was a 200 that opened an empty page.** The watchlist drawer
linked `stock.html?t=<T>`. `stock.html` takes its ticker from `location.hash` (four
readers) and from exactly one query parameter, `?ticker=`, which a boot shim rewrites
into the hash. `?t=` is neither. No link checker can see this — the page exists and
returns 200 — so `tests/test_watchlist_drawer_js.py` pins the accepted parameter set
against `stock.html.j2` itself.

**W4-D4 — a stateless row dropped its read into the state column.** `.wri-lrow` is a
three-column grid; `portfolio.js`'s local `lrow()` omitted the `.st` cell entirely when
a row had no state, so Stage and Extension mis-laid in the shipped drawer. The shared
painter always emits the cell, empty when there is no state.

**W4-D5 — "filed under AAPL".** `clusterLabel` returns `members[0]` for a one-name
group — its own bet — so passing the label through printed a tautology inside that
name's own drawer. The drawer now carries the two facts behind the label (which force,
how many names) and words them itself: a one-name group reads "moves on its own —
nothing else here is grouped with it", which is a finding rather than a label.

**W4-D6 — `entry_signal.action` is never read.** The engine writes it as an instruction
("take a half position here, or wait for the weekly to turn"). Holdings surfaces are
descriptive only (§7(b), doctrine Law 1), so Tier 1 reads `headline` and a test pins the
phrase itself rather than a proxy.

**W4-D7 — the chat launcher was never actually hidden.** The W2/W3 harnesses hide
`#mm-brain-launcher, .mm-brain-launcher, #mmb-launcher, [class*="brain-launcher"]`. The
widget is `#mmb-launch`. Four selectors, no match, in every crop those harnesses ever
took — it is absent from most of them only by luck of where it lands, and it appeared
over the drawer in the first run here. This harness derives the id by enumerating every
`position:fixed` element on the rendered page, hides the scrim and panel too, and then
**asserts the computed style went to `none`** rather than assuming the rule matched.

**W4-D8 — a date rode `.fig`.** "Jun 29, 2026" contains words, and mono numerals are for
figures only. Dropped from the Company-notes date.

**W4-D9 — a `title=` carrying translated text.** `watchlist.js` emitted
`title="从清单移除"` on the legacy remove button beside an `aria-label` already carrying
the same string. `scripts/check_title_i18n` scans `.j2`/`.html` only, so a JS file that
EMITS the attribute is outside its reach. Removed; the suite now pins its absence in all
three files.

---

## 3a. Round 2 — what the commissioning review found, and what changed

Verdict: BLOCK. Two blockers, three evidence-integrity majors, twelve minors. Every
finding was confirmed by execution against all 1,629 production artifacts, and the two
that mattered most were invisible to every fixture-based test in this file **for the same
reason**: a fixture only ever contains the cases whoever wrote it thought of.

**W4-R1 — the Tier-1 lead was a trade imperative on 66.6% of the library.** The lead
rendered `entry_signal.headline` raw, and that field is written in the engine's trading
voice: "Extended — wait for a pullback" ×588, "Buy soon — on confirmation" ×252, "Hold —
don't add here" ×104, "Topping — protect gains" ×50 — 1,085 of 1,629 names. Packet §0
bars imperatives outright and §7(b) bars the gain-protection phrasing by name. Cured with
a **total de-imperative map keyed on `status`** (the engine's enum, eleven values, 1:1
with the eleven headlines) so a reworded headline still lands on descriptive copy instead
of falling through to passthrough. An unmapped status falls back to a trend-derived state
line, never to the engine string. `headline` and `action` now reach the DOM at no tier.

**W4-R2 — the same defect, in the tooltip slot.** The Company-notes tip quoted
`alerts.pinned`, and 1,292 of the 1,611 names carrying a pinned note (80.2%) include a
banned token ("BUY ZONE", "BUY SETUP", "take profit", "half size"). The row now counts
and dates the trail and quotes none of it; the trail's canonical home is the dossier.

**W4-R3 — the ENB cure covered one of the three routes it named.** `shown` had no floor,
so the floored route printed "0.8" beside a whole number that said 1; and the capped
route (calm 9.0 / stress 7.0, six names) printed "6.0 … 6.0" under "tightens, but not by a
whole direction" — a false quantitative claim hiding two whole directions behind the
display cap. `shown` now carries the same floor as `bets`, and the two BOUND cases get a
sentence that names the bound and makes no numeric claim. All three routes tested.

**W4-R4 — the stance was a constant, not a partition.** Measured: Watch **93.5%** /
Get ready 3.6% / No action 2.9%, while this file's own prose claimed "No finding is the
most common" — false by ~32×. The cause is visible in the per-lane rates (`selling` runs
`elev` on 74% of the library, `estimates` on 55%), so "≥1 elevated lane → Watch" is very
nearly "has data". The fix is not a threshold: `roleBadge` **already grades severity into
three rungs** and an `if (role)` was flattening them. Watch is now the two severe rungs,
Get ready the review rung or any lane signal below it. Measured after:
**Watch 50.0% · Get ready 47.0% · No action 2.9%**.

**W4-R5 — ownership severity discriminated nothing.** `insider.cluster === true` fired on
1,133 of the 1,221 names carrying ownership data (92.8%). The row is now NEUTRAL, and not
because a better threshold was unavailable: the `selling` LANE already owns severity on
exactly this topic and is the calibrated surface for it. Ownership reports who and how
many, which the lane never states, and reports no severity at all.

**W4-R6 — past earnings dates read as forward-looking.** `earnings.next_date` is already
past on **1,197 of the 1,205** names carrying one, because the artifacts bake on a cadence
the calendar outruns. The chip was guarded for this; the state and the sentence were not,
so the lane read "reports Jul 30" in a confident `ok` about a date that had gone. Past
dates now report what happened and drop to `na`.

**W4-R7 — the harness overwrote committed evidence before judging it.** All 25 PNGs were
written straight into the committed directory and only then asserted over, so a failing
run replaced good evidence with bad — and a bare `main()` at module scope meant `--help`
did it too. It now shoots to a temp dir and promotes only on full success.

**W4-R8 — the old-HTML gate checked that a chevron EXISTED.** That is precisely the D1
defect state: a control that renders, rotates, and does nothing. It now clicks one and
asserts a drawer opened — and in doing so produced the receipt that **D1 is live in
production today**: the `all-old` control clicks production's own chevron and no drawer
opens.

**W4-R9 — `.wri-rail-chain` had no rule anywhere**, emitted since #3527. Styled, same
in-file law as the five classes W3 found.

**W4-R10 — three test-suite defects.** The job comment claimed the suite "skips loudly"
without node; it exited 0 with 35 of 45 skipped, so a missing node is now a FAILURE on
CI. The stamp test hardcoded `?v=7/5/5`, a wave-boundary latch that would red the next
legitimate bump; it now asserts a monotonic increase against `origin/main` and retires
itself on merge. The class-coverage test iterated a hand-written list while claiming
derivation; it now harvests the emitted class set from the source, which is what would
have caught `.wri-rail-chain`.

---

### Round 3 — the regression, and the rest

**W4-R11 — a machine-local absolute-path symlink reached a commit.** `site/stockdata` was
committed as a mode-120000 blob whose content is `/Users/<someone>/…`: it resolves on one
laptop and dangles on every other checkout, at the exact path four builders write into and
`scripts/audit_r2.py` reads as its freshness beacon. Four independent holes lined up —
`.gitignore` said `site/stockdata/`, and a **trailing-slash pattern matches directories
only**, so a symlink there was never ignored; `link_nightly_artifacts()` was called
OUTSIDE the harness's `try`, so an exception skipped the cleanup; the "already exists,
skip" branch returned before recording the path, so no later run would ever remove it
either; and a broad `git add -A` did the rest. All four fixed at their own layer, and
`tests/test_no_absolute_path_symlinks.py` closes the CLASS — no tracked symlink anywhere
in the repo may carry an absolute target (relative targets stay legal).

**W4-R12 — two oracles answer "is it stretched", and the drawer resolved the
disagreement in the reader's disfavour.** `ladder.alignment.overextended` and
`entry_signal.status === 'extended'` disagree on **820 of 1,629 names (50.3%)
symmetrically**, and in the direction that matters — the ladder flags it, the entry status
calls it clean — on **607 (37.3%)**. RIVN is exactly that shape, so all five committed
`03_degraded_RIVN` crops rendered "Stretched" eight rows above "not stretched" (in ZH a
flat self-negation), and the stance, which reads the LANE, printed "No action / Nothing
here needs a decision today." over it.

Reconciling the two oracles is an ENGINE question and is chipped as its own wave. Three
display-tier fixes landed here: a **one-way stance floor** (a name the ladder flags may
not be told nothing needs a decision — scoped to the all-clear branch only, because
clamping every tier moved 549 names and put Watch back to 83.7%); **label and vocabulary
disambiguation** (the row is now "Distance from trend" / 偏离度 and its values describe
DISTANCE — "Well above its own trend" — so one English word no longer names two
measurements); and the disclosure in the PR body.

**W4-R13 — the distance row moved into the shared composer.** It lived in `portfolio.js`,
so it appeared in the holdings drawer and not the watchlist one: the same name read
differently depending on which mode you opened it from, which is the exact drift a single
composer exists to prevent. It reads nothing but the per-ticker JSON, so there was no
reason for it to be caller-side.

**Stage remains holdings-only, and that is deliberate.** It is composed from
`portfolio_ctx.json`, which only the holdings path loads; the watchlist drawer would have
to fetch a second artifact to show it. Disclosed rather than silently asymmetric — if a
later wave wants parity, the cost is that fetch.

**W4-R14 — three coverage meanings rendered as one mark.** A coverage gap ("we could not
read it"), an evaluated negative ("we looked; there is none") and a structural
non-applicability ("a watchlist name has no weight") all printed `n/a`, which erases the
exact distinction the nulls-printed law exists to make. Three marks now: `n/a` dimmed
because it is an absence, `NONE` and `—` at full muted weight because they are answers.

**W4-R15 — the sibling harness kept the module-scope `main()`** that F4 removed from the
crop harness: importing `verify_w4_old_html_new_js.py` fired a live fetch to production,
three `git show` subprocesses, a chromium launch and a port bind. Guarded, with argparse.

**W4-R16 — the D1 receipt was ambiguous.** It collapsed "no chevron found" and "clicked,
nothing opened" into one boolean, and its selector spanned both tables so the click could
land on the never-broken watchlist path. Three named outcomes now, scoped per table, with
the watchlist path asserted separately as a non-regression. It reports
`clicked-no-open` on the holdings table under production's own scripts.

---

### Round 4 — the sentence that welded two measurements, and the counts that were wrong

**W4-R17 — the distance row offered a RAW number as a NORMALISED word's evidence.**
`Well above its own trend — about 8.9% above its 200-day line.` reads as one claim with
its own proof attached. It is two claims: `ext.grade` grades `ext_z`, the z-score of that
gap against the name's OWN 252-day history, so the word is volatility-normalised and the
number is not. Measured over the 1,621 artifacts carrying `tech.pct_vs_200dma`, **33.6%
of ordered pairs invert** — the name graded further out sits at the SMALLER raw gap — and
the committed crops are exactly such a pair (AAPL "in line" at +9.0%, RIVN "well above"
at +8.9%). The number now leads as a plain fact of its own and the word follows behind
the yardstick it was actually taken against.

**And the yardstick clause is branch-specific, because the two sources are not the same
measure.** `ext.grade` covers 1,260 of the 1,621; the other **361 fall back to
`ladder.alignment.overextended`**, which `engine/cycles.py::_overextended` reads off
daily/3-day StochRSI + RSI14 overbought or a >=30% gap — "how hard it has run lately",
not a normalised distance. **Both crop exemplars are in that 361: neither AAPL nor RIVN
carries an `ext` block at all.** Printing "against how far this name usually runs" over
the ladder branch would name a measure we did not take, so it says what it did measure
instead. (The round-3 review characterised the word as volatility-normalised full stop;
that is true of 78% of the library and of none of the crops.)

**W4-R18 — the *label* collision outlived the row-wording fix.** Round 3 disambiguated
the distance row's values and left `Stretch` on the lane, so drawers still rendered
"Stretch: OK — not stretched" a few rows from "Distance from trend: Well above its own
trend": one English word naming two measurements, in the place a reader meets first. The
lane is now **Entry stretch / 入场拉伸** and its sentences are phrased against the ENTRY
("entries here are not chasing a move that already ran"), so neither row reads as the
negation of the other. The lane's underlying read is untouched — label and copy only.
Its `hv20` fallback branch, which has no entry read at all, now says so before reporting
the swing size rather than filing a volatility answer under an entry label.

**The two rows can still disagree, and that is the disclosed engine state, not a copy
defect.** RIVN is the shape where the ladder says overextended and the entry status says
clean; the drawer now shows two rows that each name what they measured, instead of one
vocabulary contradicting itself. Reconciling the oracles is chipped as its own wave.

**W4-R19 — the row counts in this file were wrong in every scene, for three rounds.**
The composer emits 15 rows and a holdings drawer 16; this file said 15 everywhere and
"8 of 15" for a 16-row scene, and the sub-counts had drifted past the distance row and
past AAPL's Transmission row changing state. The cure is not a corrected number, it is
`drawer_rows()` + `print_inventory()` in the harness: the run now PRINTS the per-scene
inventory it measured, and every count in §1 and §2 is transcribed from that output. The
self-certifying sentence that outlived three reviews ("every figure here is per-scene and
matches the crop named beside it") is deleted and replaced by §2's explicit split of
machine-derived from hand-written.

**W4-R20 — the library sweep measured the PRE-floor stance.** `SWEEP_JS` called
`intelStance(L, roleBadge(L))` with two arguments after the function grew a third; the
flag argument is what applies the round-3 all-clear floor, so the printed receipt said
No action **48 (2.9%)** while the DOM rendered **16 (1.0%)**. Both sweeps SKIP in CI for
want of the nightly artifacts, so a local run is the only place this was visible — and
the same property means a stray `%` anywhere in that template raises `TypeError` before
the sweep runs. Both are recorded inline.

**Two nits considered and declined, with reasons.** (1) `In its setup zone now` is the
Tier-1 lead closest to entry timing, but "now" is doing contrastive work against the
map's five not-yet states ("no pullback yet", "not confirmed yet", "confirmation not in
yet") rather than urging anything, and no rewording keeps that contrast without losing
the state. (2) Scene 04 renders `DAY —` as its sole header metric and it does look like
an unfinished band — the round-3 brief permits suppressing it there. Declined: that dash
is a printed null with a tooltip explaining why the figure is absent, and removing a
disclosure so a screenshot looks tidier is the wrong trade in a codebase whose law is
nulls printed, not hidden. It is the sole metric only because this seeded row carries no
`sector` string; the drawer's own Sector & theme row has one.

---

## 4. One honest limitation, stated plainly

**Sector names render in English under `zh`.** `stockdata/<T>.json` carries `sector` as
an English string with no `_zh` sibling, and the watchlist table's own "Sector / theme"
column has always rendered it raw in both languages. The drawer matches the table rather
than diverging from it, because a drawer and a table disagreeing about one field is
worse than a known gap.

The remedy exists and is one wave's work, not this one's: `templates/options.html.j2`
already receives a build-time `sector_zh_json` context and does
`(window.OEW_SECTOR_ZH || {})[r.sector] || r.sector`. Injecting the same context into
`watchlist.html.j2` would fix the column and the drawer together. Recorded here rather
than taken, because it is a builder change in a presentation wave and it belongs to the
whole page, not to the drawer.

---

## 5. Two harnesses, and what each one can prove

`shoot_w4_crops.py` — the visual gate above. Hand-run: the CI packs install a minimal
dependency set, so a pytest wrapper would SKIP on a missing playwright and report green
while proving nothing.

`verify_w4_old_html_new_js.py` — the deploy split-brain (packet §11). Plain-copy JS goes
live on the VPS's 3-minute pull while `site/watchlist.html` waits for a render, so
production serves the currently-baked markup with this branch's scripts. It fetches the
live page, serves it locally, and swaps each W4 file between `origin/main` and this
branch, one at a time and then all together.

Unlike its W3 sibling it does not assume which markup is live — it reads the page and
asserts the property that matters for whichever it finds. **As of this build the live
page is the W2 workspace** (it was still the pre-W2 card grid when W3 ran), and the
result is clean under every swap: 3 rows and 3 affordances in all five cases, no page
errors, no drawer markup appearing without a host.

One thing it cannot see, recorded so nobody reads more into it than it says: served
locally the page has no Supabase config, so its auth bootstrap resolves to
`data-ws-state="signed"`. The anonymous branch is therefore not reachable in this
harness, and the anonymous drawer's evidence is scene 05 of the crop matrix, which shoots
it on a build with the four gated scripts genuinely removed.

The node-shelled half of the evidence — honest absence over an empty payload, attribute
escaping, the stance precedence, the glance-tier vocabulary, the dossier route — is
`tests/test_watchlist_drawer_js.py`, which **does** run in CI, in `wri-risk-core`.
