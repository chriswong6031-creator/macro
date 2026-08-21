# XPV2-SC-R3B — State Matrix Evidence (commission §21 deliverable 7)

State × where demonstrated × evidence file, for the candidate
`proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`.

| state | where demonstrated (view + mechanism) | evidence file | notes |
|---|---|---|---|
| **loading** | static-shell law — the shell before boot-time population runs | *(not captured — see below)* | attempted, not reliably catchable; documented honestly, not faked |
| **zero / empty** | Confluence, Nasdaq-100 tab, Entry-now bucket (0 population) | `confluence-empty-lane.png` | `emptyLane()` render: "No subsectors is firing a fresh entry tier right now." |
| **zero / empty (search)** | Confluence, S&P 500 tab, `#cf-q` filter matching nothing | `confluence-search-zero.png` | count reads **`0 / 65`** exactly |
| **stale** | Overview, board as-of stamp | `overview-1440-dark-en.png` (and every other overview primary/additional crop) | `#ov-asof` carries class `r3-stale`, `#ov-staleline` visible: *"This board's clock is more than 12 hours old."* Fixture `as_of=2026-08-19` trips the 12h absolute-clock guard against every capture's real wall-clock time. |
| **partial** | Money — searched for a null-guarded `—` placeholder | *(none found — see below)* | documented honestly, not fabricated |
| **error** | Overview Act-Now board, simulate-fetch-fail ON + hydrated | `overview-access-fetchfail.png` | `REF.log` shows `fetch … premiumdata/sector_central.json — simulated-fail`; board stays at the baked 3/3/3/3/3 gated shell (`access_evidence.md`) |
| **access-shell (gated)** | Overview Act-Now board, boot default | `overview-access-gated.png` | 3/3/3/3/3 + 5 disclosures |
| **access-hydrated** | Overview Act-Now board, `hydrated` access state, fetch succeeds | `overview-access-hydrated.png` | 4/5/5/3/27, `.pg-more` → 0 (QA2-07 confirmed fixed — `access_evidence.md`) |
| **long names** | Confluence, Russell-2000 tab, filtered to the longest EN label at 390px | `long-name-proof.png` | "Drug Manufacturers - Specialty & Generic" (41 chars, longest of all 4 universes) wraps to 3 lines, **unclipped**, no ellipsis, no horizontal overflow of the cell itself |
| **cardinality-extreme** | Confluence, Russell-2000 tab, "Show all" expanded | `confluence-russell-showall.png` | DOM-verified **93 rows** (`#cf-cnt` reads `93 / 93`), button reads "Show fewer" post-expand |

## `loading` — why not captured

Attempted via CDP-throttled navigation (`Network.emulateNetworkConditions`,
~2 Mbps / 20ms latency) plus `page.goto(url, {waitUntil:'commit'})` and an
immediate DOM probe, across 8 attempts. Every attempt found
`document.getElementById('actnow')` returning `null` at the `commit`
lifecycle point — i.e. the navigation has *started* but the parser has not
yet reached the Overview section's markup, so there is no in-between DOM
state where the section exists but reads as an unpopulated skeleton.

The underlying reason: this candidate's population is **synchronous with
`DOMContentLoaded`**, not deferred to a later frame. `route()` (the
router's own initial dispatch) executes inline at parse time (`route();` at
the very end of the document body, not inside any listener), and the
per-view population (`REF.renderActNow()`, `paintClock()`, etc.) is wired
to `document.addEventListener('DOMContentLoaded', …)` — which, for
listeners registered earlier in the document, fires only after the *entire*
5.4MB file (including its ~4MB of embedded JSON fixtures near the end) has
finished parsing. There is no `requestAnimationFrame`/microtask gap between
"skeleton visible" and "fully painted" that a screenshot could land inside
on a local, low-latency `http.server` — by the time any content is on
screen at all, DOMContentLoaded has typically already fired or is about to
in the same task. This is a property of the reference artifact's
single-file, inline-script assembly (correctly reproducing a `document.write`-
style synchronous boot, not production's actual async chunked delivery),
not a bug to work around by patching the page.

**Not fabricated**: no `loading-static-shell.png` file exists in this
evidence set. If a reviewer needs this state demonstrated, it would require
either network-level response throttling on the *individual* embedded
fixture reads (not applicable — they are inline, not separate requests) or
an intentional artificial delay inserted into the candidate itself, which
is out of scope for evidence capture (frozen spec: capture the artifact
AS IS).

## `partial` (null-guarded `—`) — none found in this fixture

Searched Money view's rendered DOM for standalone `—` placeholders (pattern
`>—<`, i.e. a cell/span whose entire content is the null-guard dash) after
opening every disclosure the view exposes (`#hm-alt`). Result: **0
occurrences.** The two most likely candidate fields were checked directly:

- `#mkt-hilo` ("new highs / new lows"): renders `22 / 0` — `nl=0` is a real
  value, not `null` (the guard is `mc.nl==null?'—':mc.nl`, and 0 is not
  `null`).
- `#mkt-ad-sub` ("A/D ratio"): renders `A/D 1.31`.

Every sub-field this fixture's `marketdata/sp500_heatmap.json`,
`marketdata/index_leadership.json`, `marketdata/nasdaq_internals.json`, and
`marketdata/rotation_events.json` feed into Money's rendering appears
populated. The `numOrDash`-style guards (`fmtPc`, `sgn`, the several
`v==null?'—':…` inline ternaries at `mny` §D/E, cited in the candidate's own
comments) exist in the code and are exercised correctly for `null`/`NaN`
inputs generically (per the code's own `NaN`/`Infinity`→`null` JSON-parse
sanitization, `REF.parseJSON`), but this specific fixture does not happen to
carry a null value on any Money sub-field this pass checked. Reporting this
honestly rather than fabricating a null field or claiming a placeholder
that is not there.
