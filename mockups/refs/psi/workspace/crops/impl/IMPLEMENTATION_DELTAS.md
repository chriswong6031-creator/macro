# W2 implementation — crops, and every delta from the pinned design

The pinned design is `mockups/refs/psi/workspace/workspace.html` + `DESIGN_NOTES.md`
(PR #5464, still open at the time of this build — read from that branch). This file is
the implementation's side of the record: what the crops show, how they were taken, and
every place the build departed from the pinned artifact or resolved something it left open.

**DESIGN_NOTES.md is not edited here on purpose.** It lives in #5464 and would fork if
this PR carried a second copy. Sections 2 and 3 below are written to be folded into its
§7 (Builder inheritance) once that PR lands.

---

## 1. How the crops were taken

`crops/impl/` — 32 full-page PNGs at 2× device scale, viewports 1440×900 and 390×844.
Six states are shot in all five variants; the 100-name state is shot in two, because its
design is identical to the 55-name state — it is a LOAD gate, and the load law is
asserted programmatically at every width instead (§4).

Every shot loads `templates/watchlist.html.j2` rendered through the same three globals
`scripts/build_site.py` injects, and runs **the page's own scripts** against the **real
nightly artifacts** in `site/` — the stockdata index, per-ticker JSON, and
`factor_betas.json`. Nothing is staged: the seeds put a BOOK in `localStorage`, which is
the same store a real visitor's book lives in, and every figure on screen is the page
computing over that book.

The anonymous shots (`01_`, `02_`) load a build with the four account-gated scripts
**removed**, which is exactly what production does — `config/site_access.yml` keeps
`stockdata.js`, `watchlist_risk.js`, `risk_core.js` and `factor_exposure.js` off the
public plane, so their tags 401 and never execute. The wall is reproduced, not simulated.

| # | state | proves |
|---|---|---|
| 01 | anonymous, empty | entry panel, no borrowed counts, "Local to this browser" |
| 02 | anonymous, analyzed (8 names) | real structure read; money rail real, risk rail locked (A9) |
| 03 | signed-in Portfolio, 12 positions | Book Seam over real risk shares; modeled-subset headline |
| 04 | Watchlists, 55 names | dense table, Δ-since-visit, 390 reduction |
| 05 | save-state chip | all four states side by side |
| 06 | Watchlists, 100 names | large-list law at the top of the range |
| 07 | multi-market book, HK filter active | chips filter the TABLE only; book read stays whole-portfolio |

**One honest limitation.** The per-ticker artifacts present in this environment are a
mix of real and fixture data (several names carry a placeholder close of exactly
`100.00`). The crops are the real page over the artifacts it was given — the figures are
computed, not authored — but they are not production values.

---

## 2. Deltas from the pinned design

**D1 — Watchlists mode gains an add-a-name field.** The pinned mockup is a static
artifact, so it shows no control for adding a name; the real page must have one. A
`.srch`-styled input sits in `.wl-head` after the list picker, with the existing
suggestion dropdown. No new grammar — it is the same `.srch` the toolbar filter uses.

**D2 — Scenario Lab ships as a labelled shell.** The pinned mockup writes out the
lab's copy; the packet scopes the pre-trade check to a later wave. The `<details>` row is
present in the pinned position with its pinned summary line, and its body says what it
will do and that it lands next wave, rather than presenting a control that does nothing.

**D3 — Risk Center: Concentration is live, the other five tabs are labelled shells.**
Per the W2 scope. Each shell states the one question its tab will answer, in plain words,
plus "Being built — this tab lands in the next wave". No fake panels.

**D4 — The regime read moved from a rail to the book read's subline.** The pinned design
gives BOOK READ a `sec-sub` ("Quiet tape · nothing crossed a line overnight"); the
pre-existing `#wri_rail` was a separate tinted strip. The rail's own state tint was
dropped with it: the subline is quiet muted text, and a state ramp there would introduce
a fifth reserved hue on a page whose palette decision allows four.

**D5 — The condition-count line is retired, not ported.** It answered "how much of the
book is this summary about"; the pinned design answers the same question better with the
attention stack's "5 of 12 positions" section header. Two sentences answering one
question, one line apart, was the defect.

**D6 — Coverage disclosure splits into two sentences on a multi-market book.** The seam
can only draw ONE currency (the page's own toolbar states that law), so when the book
spans markets the rails describe the LEAD book and the line says which: "The two lines
above read your US stocks book — 12 of 15 positions." The uncovered count is then over
exactly the set the rails drew. The pinned single-market mockup had no occasion for this.

**D7 — The engine-state → plain-word stage map is a build decision the mockup did not
specify.** The mockup names the seven stage words; the engine emits nine states plus a
`LIMITED` sentinel. The map is fixed, lives in `templates/watchlist.js`, and only ever
de-escalates: `BOTTOM WATCH` (a downtrend near a low) becomes *Broke down*, not *Early
sign*; `COUNTERTREND BOUNCE` (an unconfirmed turn) becomes *Early sign*, not
*Confirming*; anything unknown becomes *Not covered*. Pinned by
`tests/test_watchlist_workspace_js.py`.

**D9 — The pinned "Sort: Value" toolbar button is absent; sorting moved to the column
headers.** The mockup shows a `Sort: Value` button beside "Add position". The built table
has sortable column headers instead (`aria-sort`, click to toggle) — the same affordance
in the place a reader already looks for it, and it sorts by any column rather than
cycling one. The button would have been a second control for a subset of what the headers
already do. If the commissioning session wants the pinned control back, it is additive.

**D10 — The anonymous entry panel persists above the analysis; the mockup replaced it.**
In the pinned state (b) the paste box is gone once the book is read. Built, it collapses
to a compact single-line header plus the textarea and the weighting control, and stays.
Reason: the weighting mode is the visitor's most likely SECOND action ("what if these are
percentages?"), and re-deriving the whole read is one click from there. Removing the panel
would mean re-entering the book to change one control. Recorded as a deliberate departure,
not an oversight — the commissioning session may rule it back.

**D8 — The anonymous headline uses weight and market concentration, not sector.** The
A9 ruling allows "via public metadata, else weight-only concentration". A name's sector
is only on this page via the gated `stockdata/index.json`, so the build takes the stated
fallback. Recorded in full in packet §14 A9.

---

## 3. Rulings inherited and honoured

- **§7(a) theme mechanism** — dark is the bare `:root` plane theme.css already defines;
  light is `html[data-theme="light"]`. There is no `[data-theme="dark"]` selector
  anywhere in `watchlist.html.j2`. Verified in the light crops, which are shot by setting
  the attribute the real page sets.
- **§7(b) stance vocabulary** — Watch · Get ready · No action only, plus "Nothing here
  needs a decision today." Neither "Act" nor "Protect gains" appears. The stance line
  only claims "worth a look" when a row actually carries Watch or Get ready.
- **§7(c) the 390px column set** — Day, Since entry, Risk share and Sector are
  `display:none` in the row and reachable in the drawer; the watchlist keeps its own
  template so Δ-since-visit survives. Zero page-level horizontal scroll at 390 verified
  at 55 and 100 names.
- **§7(d) book-chip semantics** — the strip is the second line of the holdings toolbar;
  chips filter the holdings table view only; the book read, attention stack and Risk
  Center always describe the whole portfolio; the disclosure line reads "Showing 2 of 15
  — Hong Kong book"; the currency law is the strip's trailing subline.
- **§1 the signature** — one Book Seam, drawn in one function (`WS.seam` in
  `watchlist.js`), fed by both the anonymous path and the signed-in path. No second
  renderer exists, which is why a row's risk share and the seam's rail cannot disagree.
- **§4 honest data** — Day is always "—" with its Tier-2 cue; anonymous Since-entry is
  "—" with a cue rather than a fabricated 0.0%; the anonymous Value column collapses to
  weight; mode-switch counts are absent for a visitor with nothing saved.
- **§6 ZH** — zero `title=` attributes in the workspace markup; placeholders use the
  `data-ph-en`/`data-ph-zh` pair; ZH dates drop `.fig` because they contain words.

---

## 3a. Round-2 rulings absorbed

**zh stage word for `BOTTOM WATCH` (supersedes D7's zh half).** EN *Broke down* stands —
it describes the completed break. The zh word became **已破位** (describes the break)
instead of **已失效** (declares the read invalid). 已失效 is an engine-verdict word, and a
display tier may only ever de-escalate; it leaves the glance tier entirely.

**Δ-since-visit down marker (zh collision).** The marker and the *aging* stage word both
rendered **转弱**, so a movement marker and a stage read were indistinguishable in Chinese.
The marker is now **转跌** ("turned down", matching its EN); the stage keeps 转弱.

**The seam is capped at 24 segments with a disclosed tail.** One segment per position
overflowed the PAGE at 100 names on 390px — measured 86px, the large-list law broken by
the device meant to explain the book. The rail now draws the 23 largest and folds the
rest into one labelled segment; both denominators and both brackets are still computed
over ALL positions, so capping moves pixels and never arithmetic.

**Share counts never speak as money.** Anonymously there is no price plane, so Shares mode
now carries a `unit` through every derived figure: headline, because-line, seam label,
bracket, segment tooltips, the Weight column header and the coverage line all say *share
count*, and one line states plainly that turning share counts into position sizes needs
prices — which arrive with the free account. Previously a book of "BRK-A 1, F 5000, AAPL
100" announced "98% of the money sits in F" while printing its largest holding at 0.0%.

**Non-directional uses of `--down` were repainted to `--act`.** Found while auditing the
zh flip: the remove-hover, the modal error line and the failure toast painted from the
DIRECTION token, so under 红涨绿跌 an error message turned GREEN. Health tokens do not
swap, which is exactly why they exist.

---

## 4. What is asserted rather than eyeballed

A crop shows one moment. These run in a real browser over the real page and fail loudly,
so the gate rows below are regressions-with-a-name rather than things a reviewer has to
re-check by eye. 33 assertions, all passing at the head of this PR:

- **Large-list law** at 55 and 100 names × desktop and 390: DOM row count equals list
  count; `scrollWidth - clientWidth == 0` (zero page-level horizontal scroll); a filter
  keystroke narrows the table; the scope line discloses the reduction with both numbers;
  per-name detail has hydrated into the rows.
- **One unreadable ticker degrades exactly one row** — the row stays, the list does not.
- **The persisted book filter is disclosed, never silent** — "Showing 2 of 15 — Hong
  Kong book", with the book read still describing all 15.
- **The save chip reaches all four states**, each bilingual and each carrying its Tier-2
  receipt.
- **The Account Sync panel is gone** — all seven of its element ids are absent.
- **Zero `title=` attributes** in the workspace markup.
- **No banned glance-tier vocabulary** in the rendered copy.
- **The anonymous boundary**: the four gated scripts never execute; the money rail draws
  8 real segments and is NOT hatched; the risk rail is a lock shell; every Signal cell is
  a lock; the free CTA and the Risk Center lock shell are present; **the effective-bets
  claim is not made**; and the analysis survives a refresh.
- **No page errors** anywhere in the run.

### The scripts are committed, beside these crops

| script | what it proves | when it runs |
|---|---|---|
| `verify_w2_workspace.py` | the 33 assertions above | by hand (needs a browser) |
| `verify_b2_old_html_new_js.py` | the OLD-HTML + NEW-JS window, per file, against **live production markup** | by hand (needs network + a browser) |
| `render_preview.py` + `preview_seed.js` | renders the signed-in and anonymous-wall previews the other two drive | by hand |
| `shoot_crops.py` | the crop matrix | by hand |

They are hand-run on purpose. The CI packs install a minimal dependency set, not
`requirements.txt`, so a `pytest.importorskip("playwright")` would SKIP in CI and report
green while proving nothing (house trap: *ci-packs-install-minimal-deps-not-requirements*).
The precedent is `mockups/refs/breathing-platform/verify_wl1.py`. Everything checkable
WITHOUT a browser — the absent `#wl_auth` ids, zero `title=`, the banned-vocab sweep, the
stance set, the four chip states, the seam cap and its denominators, the unit law, the
legacy fall-through, watchstore dormancy, and a regression pin for each defect this PR
fixed — is asserted in `tests/test_watchlist_workspace_js.py`, which **is** wired into
the packs.

### zh directional colour — the answer to the round-2 visual finding

**Neither side was wrong; the implementation already participates correctly, and this is
now measured rather than eyeballed.** `.pos`/`.neg` paint from `var(--ink-up)`/
`var(--ink-down)`, which derive from `--up`/`--down`, which `theme.css:155-156` swaps
under `html[data-lang="zh"]`. Computed style, same harness that shoots the crops:

| | `+48.3%` | `-15.5%` |
|---|---|---|
| EN | `#45b873` green | `#e06464` red |
| ZH | `#e06464` **red** | `#45b873` **green** |

红涨绿跌 holds. The four named traps were each checked and are clean: no direction is
painted from a hard literal anywhere in this page's CSS or JS; `var(--red)`/`var(--green)`
are not used; there are no charts, so `__CHART_SWAP__` is not involved; and the page-local
`<style>` block defines **no** direction token, so nothing local can lose to the global
swap. The crop harness does set the attribute — it writes `localStorage.lang` and reloads,
and the pre-paint head script stamps `data-lang="zh"`, verified present in the probe above.

The audit did find a real fault in the *opposite* direction, now fixed: three
NON-directional surfaces (remove-hover, modal error, failure toast) painted from `--down`
and therefore turned green in Chinese. They use `--act` now.
