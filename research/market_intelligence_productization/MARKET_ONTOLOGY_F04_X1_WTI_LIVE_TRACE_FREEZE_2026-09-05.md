# F04-X1 — WTI Live Trace: implementation freeze (Stage A)

`operation_key: marketontology-f04-explorer-x1-wti-live-trace-20260904-sol-001`
`carrier: C0BSBM78V1N/1788584226.926809` · `program: macro#6819` · `architecture: macro#6820 (eb833455)`
`base: origin/main 3cd4bd489ef567d86bbcf516b03f6d79062d67bb`
`status: PARTIAL / BUILT_NOT_PROVEN — one Draft/Hold PR, not Ready, not merged, not deployed`

## 1. What was built

A researcher opens `/ontology.html` and gets one truthful current read of a
single transmission path: the owner-observed sequence, which steps are met,
which step blocks it, what the owners have recorded, why it is dormant, the
evidence and clocks behind each step, and one next action.

| Layer | File | Owns |
|---|---|---|
| composer | `engine/ontology_explorer.py` | `ontology_explorer_snapshot.v1` — pure, request-time, read-only |
| transport | `app/ontology_explorer.py` | `GET /api/ontology/explorer/v1` behind `require_user → enforce_site_full(always=True)` |
| shell | `templates/ontology.html.j2` → `site/ontology.html` | public page with zero current values |
| assets | `templates/ontology.{css,js}` + byte-matching `site/` copies | the severed rail, and the only API consumer |
| builder | `scripts/build_ontology_explorer.py` | feature-owned; does not touch `build_site.py` |
| registration | `app/main.py` | one `include_router` hunk, nothing else |

69 tests across four files, written and observed RED before implementation
(commit `be5555bb`, "no implementation yet"), green at `HEAD`.

## 2. The three refusals

Each exists because the plausible alternative is false, and each is pinned by a
test rather than by prose.

**Downstream truth never activates a false upstream.** The frozen reference case
is real: on the live chain the terminal leg is met while all three upstream legs
are not. That is reported as `contradiction: downstream_true_without_upstream`,
never as partial activation, and `confirmed_hop_count` stays 0 — because a true
later leg has its own causes and licenses no attribution back to the root.

**An absent baseline is `comparison_unavailable`, not "nothing changed".** The
episode ledger holds zero rows for this chain. Zero rows is the absence of a
baseline, not evidence that conditions held still. `engine/transmission_context.py`'s
`diff_changes` returns `items=[]` for an absent baseline too, so it cannot
distinguish the two either.

**Freshness is never claimed.** This process reads the checkout it runs in and
cannot observe what the deployed canonical surface serves; the deployed checkout
may lag in either direction. It reports the age it can measure and marks the
comparison `verification_unavailable`.

## 3. K1 — scoped supersession of Amendment 3 §5, for X1 only

Ruled by Sol at `1788593425.474829`. Verified independently at
`contracts/evidence_foundation/vocabulary.v1.json@31e0dd0e`: `owner_stores`
admits **`txi.episode_transition`**; `excluded_derived_heads` lists
**`txi.chain_state`**. The current head this surface reads is therefore an
excluded derived head, and a dormant chain has no eligible transition to
reference instead.

So `evidence.k1` emits `status: unavailable_for_object` with
`reason_code: excluded_derived_head_no_eligible_transition`, `refs: 0`, and the
detail naming both the excluded head and the eligible store. A real
`EvidenceRef` is emitted only where a genuine eligible transition exists.

**A broader claim was withdrawn.** An earlier pre-source return argued K1 was
unsatisfiable because no producer exists and the closed field set forces
fabrication. That reasoning was wrong and is not recorded as a finding. The
narrower verified fact above is the ruling's basis. Root cause of the error: the
K1 census flagged `vocabulary.v1.json` as located-but-unread under a turn
budget, and a conclusion shipped without closing that gap.

## 4. Defects found by measurement, not by review

Four survived a careful read of my own code and were caught only by running the
thing. They are listed because each is a class, not an incident.

1. **A false zero.** `built` is stamped `"2026-09-05 02:10 UTC"`, which
   `fromisoformat` cannot parse. The first composer caught the failure and
   returned age `0` — rendering as *built just now*, the most reassuring
   possible reading of a stamp it had not understood. Now parsed properly, and
   an unparseable stamp reports `null` with `source_age_basis:
   unparseable_build_stamp`.
2. **Owner prose is not a user surface.** The live chain's second falsifier note
   reads `yield_rise with long-duration cohort RS>0 over 120d — the derating leg
   is falsified`. Rendered verbatim it put banned refutation vocabulary, a raw
   node id, and untranslated English (the note is a plain string, so the zh view
   got the English) onto the page at once. Notes now pass a screen in the
   composer — refutation terms, slug-like tokens, `zh == en` — and a withheld
   note is replaced by the *condition itself* as structured facts, which is what
   the reader needed anyway. `test_the_live_default_chain_composes_without_
   front_facing_violations` runs this against the real knowledge file.
3. **Fill tokens used as text.** `--act` measured 4.32:1 and `--ok` 3.60:1 at
   12.5px on the light canvas — both under 4.5. `theme.css` already ships the
   text-safe rungs (`--ink-*`, mixed toward `--text` per theme). Now 4.84 and
   4.82; zero failures in either theme.
4. **A semantic lie in the DOM.** The terminal station carried
   `data-link="true"` — a confirmed outbound link that does not exist. It was
   invisible because CSS hides the last connector. Now `data-link="none"`.

Also fixed: a run-on where the mechanism note (no trailing full stop) collided
with the caution sentence; a dead `/login.html` link (the house entry point is
`/?signin=1`), now guarded by a test that walks every internal link this feature
adds, because one 404 has previously frozen a whole site publish.

## 4b. Independent non-author review — 16 defects, all fixed

Two Opus reviewers with no write access attacked the branch. The first review
commissioned was lost to a turn limit before reporting, which is itself worth
recording: a broad commission that cannot finish returns nothing at all, so the
work was re-cut into two narrow, turn-budgeted passes and both returned.

**One BLOCKER.** `_walk_path` follows a single successor chain from one root.
That is the correct reading of a simple path and a silently wrong reading of
anything else. A hop list of `n1->n2` and `n3->n4`, with `n3` and `n4` observed
FALSE, composed as `state: active` over a two-leg path — the surface answering
"the path is active" about a path it had not read. Branching did the same thing
more quietly, because the second out-edge was dropped when the successor map was
built. Latent today (every live chain is a simple path, and the nightly's
`validate_chain` enforces continuity) but this module deliberately does not call
that validator, it is a request-time reader, and a hop edit that does not bump
`rev` reaches a reader before any nightly runs. `_require_simple_path` now
refuses branching, undeclared nodes and disconnection.

**Majors.** The bound was measured against the walk, not the file, so a file with
80 declared nodes and 40 disjoint hop pairs composed as "2 of 12 legs" while
returning 40 hop rows. `confirmed_hop_count` counted hops that were not on the
path. A contradiction was asserted from a leg that was never READ rather than
one that was false — while the note it published says "a later leg reads true
while an earlier one does not". An `unresolved` node was counted as observed, so
one snapshot said all four legs were observed while its own blocking-leg block
said that leg had no reading. A `built` stamp in the FUTURE rendered as age zero
— `max(0, ...)` had re-opened the exact defect the stamp parser was written to
close. Duplicate chain rows resolved silently to the first, which also defeated
the rev-coherence check, because that check only ever saw row 0. And an
unhandled exception escaped to Starlette's outermost middleware with NONE of the
private header set, bypassing this route class and `app/main.py`'s no-store
middleware together.

**Also fixed.** A 405 and a HEAD are decided by Starlette's router before the
route class is entered, so neither could ever be stamped by it — both are now
registered explicitly and headered, hidden from the schema so the documented
surface stays GET-only. `^...$` accepted a slug with a trailing newline (Python
matches `$` before a final newline), which reached the composer and split one log
call across two lines; both slug guards now use `fullmatch`. An episode row
written under a foreign `rev` was presented as the current change. A hop to an
undeclared node was diagnosed as an unpublished reading, inventing a positional
title for the phantom and telling the researcher to wait for a reading that can
never arrive. A zero-hop chain was typed as an absent source when the file was
present and parsed. `chain=` (empty) silently served the default while every
other malformed value was refused. And the builder's `return 0` on a missing
paired asset made a broken build a silent success that also skipped every later
asset.

Tests: 69 → 127 (with the site-wide `test_api_no_store` and `test_api_paywall`
guards). Every finding above has a test that fails without its fix.

## 5. Collision position

The carrier's stated nav collision does not exist: neither #6828 nor #6834
touches `templates/_navlinks.html.j2`. #6828 owns `_public_nav.html.j2`; #6834
touches no nav template. The real four-way contention is
`.github/ci/legacy-jobs.yml` (#6828 / #6834 / #6842 / #6514) and this branch
does not touch it.

Shared surfaces deliberately untouched: `legacy-jobs.yml`, `build_site.py`, all
nav templates, `Caddyfile`, `site_access.yml`, `page_registry.json`. D2C #6809
and K3-D #6514 protected path sets remain disjoint from this branch's paths.

## 6. What is NOT proven

- **Production authentication.** The rendering path was exercised with the
  entitlement dependency overridden by a local harness. A real Supabase session
  with a real `site_full` entitlement against the deployed app has not been run.
  Status codes, headers and bodies were captured from the real router.
- **Deployed behaviour.** Nothing is deployed. No public-shell caching,
  telemetry, or correction/failure transition has been observed in production.
- **Discovery.** `/ontology.html` is reachable by direct URL only. Build
  registration, a discoverable entry, registry rows and CI test selection are
  owed inside this vertical and return to F00 as the Stage B integration-hunk
  packet — accepted, not deferred to a future product.

## 7. Stage B packet (returns to F00)

Small, shared-owner hunks only: register `scripts/build_ontology_explorer.py` in
the site build; add the nav entry once #6828/#6834 reconcile; add the page
registry row; add the four test files to CI selection.

---

# Repair round 2 — Sol REQUEST_REPAIR / CONTINUE (2026-09-05)

Sol's review of head `7fbdc0a0` returned five truth blockers plus a product
completion order. What follows is what each one actually was in the code, not a
restatement of the instruction.

## The five truth blockers, and the shape of each defect

**B1 — K1 reported AVAILABLE with no reference.** `_evidence()` counted any JSON
object whose chain matched and set `status=available` with `refs_count=N`, while
constructing and validating **zero** `EvidenceRef`s. A recorded transition is a
transition; a reference is a reference. The counts are now separate fields
(`recorded_transitions` vs `refs_count`), status stays `unavailable_for_object`
until an actual unchanged-K1 resolution succeeds, and the reason is machine
readable (`eligible_transition_not_k1_resolved` when transitions exist but none
resolved, `excluded_derived_head_no_eligible_transition` when the head itself is
excluded). No second evidence library was built.

**B2 — UNKNOWN collapsed into FALSE/TRUE.** The reader took `confirmed`
truthily, so `"false"`, `0`, `""` and a missing key all became a market verdict.
`_read_leg_verdict()` now enforces typed Boolean/null semantics and separates
*observed* from *resolved* from *complete*: a non-Boolean is `node_unreadable`, a
missing `resolved` is `node_incomplete`, an unresolved node is
`node_unresolved`, and a resolved node with a null verdict is `node_unjudged`.
Every one of them stays UNKNOWN and is named in `gaps`.

**B3 — an incomplete path could render as a complete ACTIVE one.** Length of the
selected walk was the only check, so a fork, a duplicate identity, a hop into an
undeclared node, and a disconnected component beside a cycle all survived.
Topology is now validated before a simple path is rendered: branches, undeclared
nodes and disconnected walks raise; a cycle degrades with the unreached nodes
named; duplicate rows fail closed. `run()` is still never invoked and the ledger
is never written.

**B4 — the wrong change and the wrong clock.** Transition identity is now bound
to the owner-native revision and cutoff, and rows from another revision, rows
after the cutoff, malformed rows and unreadable rows are each counted and
disclosed rather than silently dropped. Generation age and observation age are
now distinct fields with distinct bases: a freshly rendered old observation is
reported as an old observation. Where the comparison cannot be observed, the
answer is a typed limitation (`verification_unavailable`), never an invented
clock.

**B5 — `rights` was the wrong object.** The YAML's `exposure_screens` are
valuation / refinancing / capex / FCF exposures. Presenting them as `rights`
invented a license status the owners never granted. The key is gone; the payload
carries `exposure_screens` and a separate `display_permission` whose status is
`not_determined_here`. Permission unknown stays unknown. No rights registry was
created.

**Plus the manifest.** `manifest_hash_for()` now folds `COMPOSER_METHOD` into the
digest alongside the read bytes, so the receipt identifies the method that
produced the answer as well as the inputs. It is still called a read receipt,
never an owner generation.

## RED → GREEN, in this repo

The witness tests were run against the pre-repair engine at HEAD `3d118196`
(the commit Sol's reviewed head became), with the repaired app module kept in
place so transport failures could not be counted as collateral:

```
48 failed, 101 passed      # pre-repair engine, current tests
151 passed                 # repaired engine
```

The witness sets: B1 → 3 tests, B2 → 9, B3 → 3, B4 → 4, B5 → 3, manifest → 1,
the action contract → 4, gap reachability → 4. The remaining 17 are the
parametrized vocabulary suites, which fail pre-repair because they read
`snap["exposure_screens"]` — B5 collateral, not an independent regression. That
distinction is stated because attributing all 48 to the five blockers would
overstate the result.

## Product completion

**The action is now an action.** `renderNextAction()` rendered a paragraph; a
card reading "Open the evidence" with nothing behind it is a caption. Every
`next_action` branch now names a `handler` the client implements and a `target`
that resolves to something on the page. `focus_leg` opens the step section,
scrolls the named step into view and moves focus onto it (`tabindex="-1"`, so it
is a destination and not a tab stop); `open_transmission` links the canonical
`/transmission.html`. The `compare_inverse_path` branch was **deleted** — an
inverse comparison needs a proven inverse path, and none is defined, so it is not
advertised. A test asserts no branch can ever offer it.

Two things the browser caught that reading could not:

* Opening a `<details>` and scrolling in the same tick measures the pre-open
  layout, and the step landed ~200px below the fold with the focus ring on
  something invisible. The scroll now waits for the frame that includes the
  revealed content.
* `requestAnimationFrame` and smooth scrolling are both animation-clocked, and a
  hidden or throttled tab runs neither — the action silently did half its job.
  A timeout races the frame callback, and the destination is verified and
  corrected without animation. Motion is the enhancement; arriving is the
  requirement.

**Product admission is not slug syntax.** The composer stays chain-generic
because it is a library, but the route now serves only `ACCEPTED_CHAINS`; any
other slug is a typed 404 (`chain_not_admitted`) even when it exists and composes
cleanly.

**Disclosure.** The first viewport carries three compact facts — coverage, how
old the readings are, and what cannot be verified — instead of a state and a date
with the limitation collapsed inside Study. Study now exposes the full digest
(not a 23-character prefix), every read receipt with path, sha256 and byte
count, and the composer method, contract, revision and owner state schema.
Withheld and missing details are listed individually with a reader-facing
location and reason; a count is not reachability. `aria-busy` is cleared on
every terminal state — success, 401, 403, 503 and a malformed 200 — because a
screen reader parked on a finished error is otherwise still told the region is
updating.

**One trap worth carrying forward.** Making the gaps reachable initially printed
`falsifiers[0].note` on the page: an internal field path *and* the refutation
vocabulary this product forbids on a reader surface. Reachability traded one law
for another. The machine path stays in the payload for machine consumers, and a
`where_label` / `reason_label` pair carries the reader-facing location — named by
family, never by node id, and for steps by ordinal ("Step 2 · Oil supply shock").

## Measured on the built page

Driven in a real browser against the real shell and the real router, with
synthetic fixture data so every measurement is shareable:

* action: section opens, scroll 0 → 688, target centred and fully visible, focus
  on the target
* terminal states: 401 / 403 / 503 / malformed-200 all render their own honest
  gate, all clear `aria-busy`, none falls back to a stale reading
* contrast: worst text class 5.07:1 dark, 4.72:1 light, measured against each
  element's actual painted ancestor
* bilingual: 301 visible `.l-en` / 0 `.l-zh` in EN, exactly inverted in ZH; no
  Latin prose leaks into the ZH reader surface
* mobile 375px: rail turns vertical, meta stacks, 44px action target, zero
  horizontal overflow

A measurement note: the first contrast pass reported 1.1:1 on two classes and the
design was fine — `color-mix()` resolves to `color(srgb 0.87 …)`, whose 0–1
floats the parser was reading as 0–255. The measuring instrument failed before
the thing being measured did.

## Two continuations the first repair pass still got wrong

**Sign-in did not come back.** The 401 gate linked a bare `/?signin=1`, so a
reader who followed a link to one specific trace signed in and landed on the
hub. The house convention is `?signin=1&ret=<root-relative path>`, consumed by
`templates/onboard.js:2624` (`retTarget()`), which accepts same-origin `/…`
only — and the server-side regwall sets the same param when it bounces, so a
returning visitor with a live session is silently refreshed rather than
re-prompted. The gate now carries it, applies the consumer's own `//` guard
before handing the path over, and preserves the deep link's query. Verified by
re-running `retTarget()`'s acceptance test against the href this page produces.

**The canonical surface was reachable from one rare branch.** `open_transmission`
only fires when nothing blocks and nothing is unobserved. In every ordinary
reading the link to `/transmission.html` existed solely inside `<noscript>` —
exactly where a reader who can see the page never looks. It is now a quiet
secondary line in the Next card in every state, beneath whatever the primary
action is: 7.12:1 dark, 5.59:1 light, target resolves, default view still four
cards.

Both are the same mistake in different clothes: a continuation that exists in
the code is not a continuation the reader can reach.

## What is still not proven, named rather than implied

* **Production authentication.** The 401/403/503/malformed proofs use FastAPI
  dependency overrides. That is local proof, not deployed auth. What *is* proven
  is that the route depends on the real `app.main.require_user` →
  `app.paywall.enforce_site_full(always=True)` chain rather than a stub
  (`app/ontology_explorer.py:112-117`).
* **CI coverage of these suites.** `grep -rn "ontology_explorer" .github/`
  returns nothing. The 153 tests pass locally and do not run in CI, so a green
  PR says nothing about them until the Stage B job lands.
* **No review stands on the current head.** `#6872` carries no GitHub review at
  all (`reviews: []`, `reviewDecision: ""`). The consumed review was two
  commissioned Opus `reviewer` subagents against head `7fbdc0a0`; that cannot
  approve a repaired successor by implication.
