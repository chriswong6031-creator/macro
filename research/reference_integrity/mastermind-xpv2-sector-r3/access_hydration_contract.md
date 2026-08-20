# XPV2-SC-R3A — Access & Hydration Contract (Deliverable 5)

Frozen ruling: `ADJUDICATIONS.md` §A9. Source lanes: A §8 (premium mechanism),
D §8 (end-to-end access trace), F State 7 (401/403 trace), D §6(a) (nightly
ledger law).

## 1. The page's ONLY premium wall

`site/premiumdata/sector_central.json` gates the **Overview Act-Now board**
and nothing else. Switch: `config.yml:7204-7206`:
```yaml
sector_central_gate:
  gated: true
  preview_rows: 3
```
read by `scripts/build_sector_central.py::_gate_cfg()` (defaults to
`{"gated": False, "preview_rows": 3}` only on a missing/malformed block —
current production state is **gated, preview=3**). Live freeze-time split at
capture (2026-08-20): `preview=3, locked=29, total=44` — this panel object is
computed off the full board, not the preview slice; with `gated:false` (or
nothing withheld) `split_actnow` returns no count object at all
(`scripts/build_sector_central.py:106-107,124-125`) — an ungated or
nothing-withheld page ships byte-identical to the pre-gate one, not a panel
with zeroed-out counts. (This is distinct from the lane HEADER counts —
`.acth-count` — which really are computed off the full `action_board` list
unconditionally regardless of gate state; see Deliverable 2's Overview rows
for that separate mechanism.)

**Every other view's payload is ungated**: Explore (`basketdata/baskets.json`,
`basketdata/narrative_emergence.json`, `oracledata/tm_manifest.json` +
episode/chunk files), Confluence (all four `marketdata/subsector_confluence*.json`
+ `marketdata/basket_confluence.json`), Map (`basketdata/baskets.json`,
`sectordata/sector_central.json`), Moving (five nightly artifacts per the
routing/binding deliverables), Money (`basketdata/si_handoff.json`,
`marketdata/sp500_heatmap.json`, `marketdata/index_leadership.json`, etc.) —
none of these paths appear under `config/site_access.yml`'s
`premium.enforced_early` prefix list. **GAP**: this is confirmed by grep of
the config file, not by a live HTTP curl against an anonymous session — lane
D flags this explicitly (§8) and it is carried forward here unresolved.

## 2. Full-count source vs preview-row source (Overview Act-Now board only)

- **Full counts** (`.acth-count`, lane header numbers): computed
  IN-TEMPLATE, off the FULL (ungated) `action_board` dict —
  `templates/_us_act_now_board.html.j2:524-528`. "The lane headings, and the
  '+N more' links, are honest totals a Free reader keeps. Only the ROW LISTS
  below are cut down." Counts are NEVER gated, only row bodies.
- **Preview rows** (the shell that ships to every reader including
  anonymous): the SAME `action_board` dict, sliced in-template at
  `_us_act_now_board.html.j2:535-541` (`_bn_rows = action_board.buy_now[:_ab_pv] if _ab_gate else …`).
  The split is computed TWICE — once in Python (`split_actnow()`) for the
  payload, once in Jinja for the shell render — from the identical source
  list, "so shell and payload can never disagree about which rows are
  visible vs withheld" (`scripts/build_sector_central.py:99-102` docstring
  intent).
- **Withheld rows**: written UNCONDITIONALLY (even when nothing is withheld)
  to `site/premiumdata/sector_central.json` by `write_payload()`
  (`scripts/build_sector_central.py:136-165`). Payload shape:
  ```json
  {"schema": "tier_payload.v1", "page": "sector_central", "gated": true,
   "required_tier": "essential", "built": "<iso ts>",
   "panels": {"actnow": {"preview": 3, "locked": 29, "total": 44}},
   "actnow_html": "<...>"}
  ```
  `actnow_html` is server-rendered from the SAME `_us_act_now_board.html.j2`
  include (rows-only shape) — shell and payload share one template path by
  construction, cannot drift.
- **Disclosures**: `_us_act_now_board.html.j2:27-28` macro `ab_more()`
  renders, per lane, e.g. "N more here — sign in to see the full lane" — this
  disclosure line IS the access-locked UI. There is no separate "access
  denied" banner anywhere on the page.

## 3. Authenticated hydration flow (client, end-to-end)

`templates/sector_central.html.j2`, tier-hydration `<script>` near EOF
(≈`:3543-3612`):

1. `PGATE = {{ pgate|tojson }}`; `SRC = PGATE && PGATE.payload`; `if (!SRC) return;`
   — no gate configured → script no-ops entirely, byte-identical to a
   pre-gate page.
2. `freshSession()` (`:3556-3564`) refreshes the Supabase session cookie
   first (long-idle token repair).
3. `whenAuthSettled()` (`:3567-3576`) waits for the first `mdx-auth`
   broadcast or a 3000ms timeout, so a slow/broken auth layer still lets the
   request proceed — **the server re-decides regardless of client auth
   state**; this wait is purely to avoid a race, never the actual gate.
4. `fetch(SRC, {credentials:'same-origin', cache:'no-store'})` against
   `premiumdata/sector_central.json`.
5. `hydrate(payload)` (`:3588-3603`) THROWS if
   `payload.schema !== 'tier_payload.v1' || payload.page !== 'sector_central'`
   — a schema/page mismatch is treated as a hydration failure, same bucket
   as a network 401.
6. On success: `insertAdjacentHTML('beforeend', …)` per lane, keyed by
   `data-ab-lane` id into the matching `#<fold-id>` element (`ab-buy-fold`,
   etc. — the SAME ids `_ACTNOW_LANES` names); `restoreFold(col)` rebuilds
   the "Show more (N)" control for any lane now over 3 rows; `.pg-more`
   disclosure lines are removed.

## 4. The 401/403/offline collapse (page-identity validation as coded)

```js
fetch(SRC, {credentials:'same-origin', cache:'no-store'})
  .then(r => { if (!r || !r.ok) throw new Error('locked'); return r.json(); })
  .then(hydrate)
  .catch(function(){ /* Locked (or offline): the shell stays exactly as
    rendered, disclosure lines and all. Nothing to undo — the withheld
    rows were never here. */ })
```
- `!r.ok` covers **401/403/5xx alike**, collapsing all of them (plus offline
  network failure, plus a schema/page mismatch from step 5 above) into ONE
  no-op catch. The visible result on any of these is: the shell renders
  exactly as server-baked — `preview_rows` rows + the `ab_more()` disclosure
  line, UNCHANGED.
- The actual authorization DECISION is made server-side: `/premiumdata/` is
  one of the prefixes under `premium.enforced_early` in
  `config/site_access.yml:648`, 403'd for anonymous/Free readers ahead of the
  site-wide paywall switch (`config/site_access.yml:618-648`) — "the SERVER
  decides who sees the board — nothing below is load-bearing, we simply ask
  and keep the shell when the answer is 401/403/offline" (in-code comment,
  `sector_central.html.j2:3538-3541`).
- Page-identity validation as coded: `hydrate()`'s `payload.schema`/`payload.page`
  check (step 5 above) is the only page-identity guard found — it is a
  content-shape check on the FETCHED payload, not a separate page-origin or
  CSRF-style check; a mismatch is folded into the same catch as a 401.

## 5. Nightly-sole-advancer rule (Track Record ledger)

Source ledger: `data/sector_central/calls.parquet`, append-only, keep-FIRST
per `(date, id)` (`engine/sector_central_grader.py:6-8`). Advanced ONLY via
`append_central_log(data)`, gated by
`engine.ledger_lane.nightly_advance_enabled()`
(`engine/sector_central_grader.py:25,109`) — **nightly-only**, consistent
with the house law "nightly is the sole advancer of forward ledgers."
`grade()` joins matured calls to realized forward returns (SPDR close for
sectors, PIT-frozen equal-weight basket level for baskets via
`_basket_levels()`, "to kill the look-ahead / survivorship leak"). "The log
is NEVER read back into a live score" (doc-level guarantee,
`engine/sector_central_grader.py:15`). This rides the SAME
build-time-embedded `window.SECTOR_CENTRAL` object the Overview cycle/regime
reads use — a build-time embed, not a client fetch, unlike Explore's
table/chart.

## 6. Summary — what R3 must preserve

| Question | Answer |
|---|---|
| Which artifact is the ONLY gate? | `premiumdata/sector_central.json`, gating the Overview Act-Now board rows (not counts) |
| Are Map/Moving/Money/Explore/Confluence gated? | No — all ungated (with the HTTP-verification GAP noted in §1) |
| What happens on 401/403/5xx/offline? | Silent no-op; shell stays exactly as server-baked with its disclosure line |
| Is there a distinct "access denied" state? | No — the disclosure line ("N more — sign in…") IS the access-locked UI |
| Who decides eligibility? | The server, always, via the `/premiumdata/` URL-level 403; client JS only asks and reacts |
| Can the Track Record ledger advance intraday? | No — nightly-sole-advancer, gated by `engine.ledger_lane.nightly_advance_enabled()` |
