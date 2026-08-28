# XPV2-SC-R3B — Access-State Evidence (commission §21 deliverable 10)

Candidate under test: `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`.
Surface under test: the Overview "What to act on now" board (`#actnow`), the
only surface the R3 REFERENCE HARNESS drawer's `Access state` control drives
(`REF.setAccessState()` → `REF.renderActNow(state)`, registered by the
Overview view partial on `DOMContentLoaded`).

## Method

Fresh browser context per state (1440×1000, `deviceScaleFactor:2`, dark/en).
Drawer opened via `#ref-harness-head`, state set via the real `<select>`
controls (`#ref-access`, `#ref-failfetch`) — no direct DOM mutation. The
drawer chrome itself (self-labelled "R3 REFERENCE HARNESS — not product UI")
is hidden with `display:none` immediately before each screenshot only — all
state changes above are applied to the live page before that hide, so
hiding it changes nothing about the measured state, only keeps the
fixed-position test chrome from bleeding into the crop.

Lane counts read directly from the DOM:
`#<lane-fold-id> > a, #<lane-fold-id> > div[data-theme-id]` per lane, in the
producer order Buy now / Almost ready / In favour / Take profits / Stand
aside. `.pg-more` = the number of "N more here — sign in" / "+N more"
disclosure notes rendered inside `#actnow`.

## Measured lane counts

| state | Buy now | Almost ready | In favour | Take profits | Stand aside | `.pg-more` count | screenshot |
|---|---|---|---|---|---|---|---|
| `gated` (boot default) | 3 | 3 | 3 | 3 | 3 | **5** | `overview-access-gated.png` |
| `hydrated` (real fetch succeeds) | 4 | 5 | 5 | 3 | **27** | **0** | `overview-access-hydrated.png` |
| `ungated` | 4 | 5 | 5 | 3 | **27** | 1 | (not separately captured — same board fully open; ungated is the un-gated ceiling both other successful states converge toward) |
| `hydrated` + simulate-fetch-fail ON | 3 | 3 | 3 | 3 | 3 | **5** | `overview-access-fetchfail.png` |

These match the commission's expected figures exactly: **gated 3/3/3/3/3 + 5
disclosures; hydrated 4/5/5/3/27 with the hydrate insert working; ungated
4/5/5/3/27.**

**Ledge totals (`#ov-ledge` cell numbers, e.g. "BUY NOW 4") are IDENTICAL
across all four states** — 4/5/5/3/27 always. This is intentional producer
behavior, not a bug: `laneCount()`'s own comment reads *"ALWAYS the full
board — state and totals are free, names are paid"*. Only the row DETAIL
(names, scores, why-lines) is gated; the honest totals are never hidden.

## The QA2-07 regression — confirmed FIXED in this candidate

`build/QA_ATTACK_REPORT.md` recorded QA2-07 (CRITICAL) against an earlier
build of this candidate: `hydrated` performed the gated-style preview paint
but never actually inserted the fetched rows, leaving the board frozen at
3/3/3/3/3 with a dead "Show more (24)" control — *worse* than `gated`,
because it silently dropped the sign-in disclosure while still not showing
the real rows.

Live-verified against the current candidate: `hydrated` now reaches the
full 4/5/5/3/27 counts, `.pg-more` drops to 0 (the disclosure notes are
`.remove()`d by `hydrate()` once the real rows land), and "Show more (1)" —
the *unrelated* `abPlus()` "+N more — full list on Sector Intelligence"
control, not the fixed disclosure — remains genuinely clickable. QA2-07 is
resolved in this build.

## `tier_payload.v1` schema check

Lives in `hydrate()` (the function `REF.renderActNow()` calls at its own
tail when `state === 'hydrated'`):

```js
function hydrate(){
  return REF.fetchJSON('premiumdata/sector_central.json').then(function(payload){
    if(!payload || payload.schema !== 'tier_payload.v1' || payload.page !== 'sector_central'){
      throw new Error('invalid payload');
    }
    ...
```

A payload failing either the schema tag or the page tag is treated
identically to a network failure — it falls into the same `.catch()` that
keeps the baked gated preview in place ("fail-soft: 401/403/5xx/offline/
schema-mismatch all collapse to a no-op").

## fetch-fail + hydrated — keeps the baked shell

Sequence: open drawer → click `#ref-failfetch` (turns `REF.simulateFetchFail`
on) → select `#ref-access` = `hydrated` (fires `REF.setAccessState('hydrated')`
→ `REF.renderActNow('hydrated')`, which repaints the gated-style 3-row
preview synchronously, THEN calls `hydrate()`, which now genuinely rejects).

Confirmed via `window.REF.log` tail after the sequence:

```
#8  [fetch] marketdata/nasdaq_internals.json — hit
#9  [fetch] basketdata/pulse.json — recorded-not-executed
#10 [fetch] premiumdata/sector_central.json — simulated-fail
#11 [boot ] (access-state) — hydrated
```

`REF.simulateFetchFail === true`, `REF.accessState === 'hydrated'`, and the
DOM lane counts are still 3/3/3/3/3 with all 5 disclosures present —
**identical to the plain `gated` state**, confirming the code comment's
claim verbatim: *"the GATED-looking preview … is also exactly what a
hydrate failure leaves in place, 'nothing to undo'."* Screenshot:
`overview-access-fetchfail.png`.

## Screenshot cross-reference

| file | state | what it shows |
|---|---|---|
| `overview-access-gated.png` | boot default (`gated`) | `#actnow`, 3-row preview per lane, "1 more here — sign in…" / "N more here…" disclosures |
| `overview-access-hydrated.png` | `hydrated`, fetch succeeds | `#actnow`, full lanes (4/5/5/3/27), "Show more (1)" (the unrelated `abPlus` control) |
| `overview-access-fetchfail.png` | `hydrated` + simulate-fetch-fail ON | `#actnow`, visually identical to `gated` — the baked shell, confirmed above |

No `overview-access-ungated.png` was separately commissioned; `ungated`'s
board is visually a strict superset of `hydrated`'s (same row counts, one
extra `.pg-more` from the unrelated `abPlus` "+N more" control) and its
counts are confirmed numerically in the table above.
