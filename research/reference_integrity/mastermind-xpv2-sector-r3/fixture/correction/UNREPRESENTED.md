# Correction / revision — UNREPRESENTED IN PRODUCTION

This entry exists so the state matrix's tenth state (State 8 — Correction/
revision) has a fixture-side artifact too, instead of silently having no row
in `fixture/` at all. There is nothing to freeze: no code path on either
Overview or Confluence renders a "this value was corrected/restated" marker,
a diff-from-yesterday callout specifically tied to a correction (as opposed
to an ordinary day-over-day change), or any concept of amending a past
printed value.

## Source

`archaeology/lane_F_state_matrix.md`, State 8:

> **UNREPRESENTED IN PRODUCTION on both Overview and Confluence.** No code
> path in any file read (`sector_central.html.j2`, `build_sector_central.py`,
> `_us_act_now_board.html.j2`, `subsectors.js`, `si_workspace.js`) renders a
> "this value was corrected/restated" marker … Grep across those files for
> `correct(ion)?|revision|restat(e|ement)|amend` returned no functional hits
> … **Verdict: correction/revision has NO production representation on this
> page family.**

`ADJUDICATIONS.md` §A6 confirms the ruling ("Correction/revision:
UNREPRESENTED in production (both surfaces). Ledger: `BLOCKED_DATA`.") and
the capability ledger's priors fix the disposition
(`capability_disposition_ledger.md` #92, `BLOCKED_DATA`).

## What this means for R3

**Do not invent a correction affordance without a producer.** There is no
producer contract to mirror — inventing one here (or in the R3 design) would
fabricate authority, exactly the failure mode `ADJUDICATIONS.md` and the
capability ledger exist to prevent. If a future wave decides Sector Central
needs a correction/revision UI, that is a new producer requirement to route
through a new `ADJUDICATIONS.md`-style ruling first, not something to sketch
around in the frontend or backfill into this fixture.

This file is intentionally the ONLY thing under `fixture/correction/` — an
empty directory would not survive `git add`, and a directory that silently
doesn't exist is indistinguishable from "nobody thought about this state."
This file is the fixture-side record that somebody did.
