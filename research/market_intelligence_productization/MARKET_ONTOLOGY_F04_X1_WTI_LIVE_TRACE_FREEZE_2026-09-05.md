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
