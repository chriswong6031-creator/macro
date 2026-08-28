---
key: TERMINAL-SAVED-LAYOUT-CONTRACT-V2
question: >
  A Terminal "Saved Layout" claims to restore the chart workspace it was saved from, but the
  shipped config stored ten fields while the workspace has more — so loading reproduced part of
  it and left the rest at whatever happened to be on screen. Which state does a layout OWN, and
  how are older configs read?
answer: >
  A versioned contract, `schemaVersion: 2`, frozen in terminal/lib/layoutConfig.ts and owning
  exactly: panes, paneTfs, split, activePane, sync, chartType, inds, indParams, hidden, compare,
  compareCfg, lockedVLine. `indParams` and `compareCfg` are stored RESTRICTED to what the layout
  activates, so a layout owns the parameters of the studies it enables and nothing else.
  Explicitly NOT owned, each ruled out rather than omitted: timeframe favourites, drawings,
  drawing style preferences, watchlist state, and Day Trade Mode.
  Every config is normalised on read. A field a v1 config never owned reads as `null`, meaning
  "this layout makes no claim, leave the current value alone" — never a reset to defaults.
  `sync` takes a FIXED compatibility default (on) gated on the config actually carrying a
  workspace, so corruption claims nothing. Unknown fields from a future version are ignored and
  malformed values fall back per field; a bad row never makes the menu unusable.
rationale: >
  The four unstored fields each produced a wrong-but-plausible restore, and the worst was
  `indParams`: a layout re-enabled its indicators but ran them on whatever parameters were
  current, so an EMA(20) layout loaded as EMA(50) after the user edited the input — the right
  studies computing different numbers, with nothing on screen to say so. `sync` was stored by
  the LOCAL workspace key (`mm.ws`) but not by the layout, so the account-backed feature
  persisted strictly less than the device did.
  The exclusions are not tidiness. Timeframe favourites are a device/toolbar personalisation
  and v1 re-applied them on load, silently rewriting the user's timeframe bar from a layout.
  Drawings have their own per-symbol, owner-keyed persistence plane; the `config` column comment
  in 0001_init.sql still says layouts hold "drawings", but that comment predates the drawing
  plane, and two owners for one drawing is a last-writer-wins conflict. Day Trade Mode has its
  own snapshot/restore state machine (`mm.dtm`, `mm.dtmSnapshot`); a layout that also flipped
  the mode flag would race it and could strand the pre-mode snapshot, leaving toggle-off unable
  to restore the swing workspace.
  Reading a missing field as the LIVE value is the subtle trap the `null` rule closes: it would
  make the same layout restore differently depending on when it was loaded, so an old layout
  would never be stable. Capture/normalize/apply are pure functions, which is what lets the
  round trip be a unit test — capture a non-default workspace, mutate every field, load it back,
  require the normalized snapshot to equal the saved contract — rather than a pile of DOM checks.
alternatives:
  - option: Dump every Terminal state atom into the layout config
    why_not: >
      The packet explicitly warned against it, and it is wrong on the merits: it would give
      drawings and Day Trade Mode a second owner, and make a layout silently overwrite device
      preferences the user set outside it. "Saved Layout" is a workspace ARRANGEMENT, not a
      snapshot of the whole client.
  - option: Leave the config unversioned and just add the four missing fields
    why_not: >
      Without a schemaVersion the read boundary cannot tell "this layout predates the field"
      from "this layout chose the falsy value", so old layouts would either be reset to defaults
      or silently inherit the live workspace — the exact instability the null rule exists to
      prevent.
  - option: Store the full device-wide indParams map rather than the layout's own keys
    why_not: >
      Loading would then overwrite the parameters of studies the layout does not even enable,
      and the payload would grow with the indicator registry rather than with the layout.
  - option: Keep storing favTF, for backward compatibility with existing layouts
    why_not: >
      There are no existing layouts — DSC:TERMINAL-CHART-LAYOUTS-TABLE-IS-EMPTY measured the
      table at zero rows — so the compatibility cost is nil and the behaviour was a defect.
evidence:
  - "terminal/lib/layoutConfig.ts — the frozen contract, the exclusion rulings, the null-means-no-claim rule"
  - "terminal/lib/__tests__/layoutConfig.test.ts — round trip, idempotence, legacy stability, fail-soft"
  - "terminal/e2e/layout-integrity.spec.ts — the same round trip driven through the real UI"
  - "supabase/migrations/0001_init.sql:51-59 — the stale 'drawings' column comment this overrules"
  - "#430 — the PR that freezes the contract; #427 — the storage contract it sits on"
affects: ["terminal/lib/layoutConfig.ts", "terminal/components/TerminalShell.tsx", "terminal/app/api/layouts/**"]
confidence: high
reversibility: costly
decided_by: opus-terminal-handoff-c
decided_at: 2026-08-19
---

## Grounds

Reversibility is `costly` rather than `easy` because `schemaVersion` is written into stored user
data. Changing what a layout owns later means either a new version plus a migration path in the
normalizer, or accepting that layouts saved under v2 restore differently than they were saved.
The mitigation is that the normalizer already exists and already has the shape for it: adding v3
is adding one branch, not inventing a mechanism.

The exclusions are the part most likely to be re-litigated by a future session, so they are
recorded as rulings with reasons rather than as an omission list. In particular, a session that
reads `0001_init.sql`'s "panes, indicators, drawings, timeframe favs" column comment and
concludes that drawings and favourites belong in the layout would be reading a comment that
predates both the drawing persistence plane and this decision.
