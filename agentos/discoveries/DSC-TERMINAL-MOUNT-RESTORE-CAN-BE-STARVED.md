---
key: TERMINAL-MOUNT-RESTORE-CAN-BE-STARVED
claim: >
  A `setState` scheduled from a passive mount effect in `terminal/components/TerminalShell.tsx`
  can be STARVED for seconds — not delayed by slow work, but repeatedly rendered and DISCARDED
  while other renders commit ahead of it. Measured on the owner-scoped watchlist restore: the
  effect ran at +700ms, immediately after hydration, with `userId` already resolved (it is a
  SERVER-resolved prop from `app/terminal/page.tsx` — this path makes no `/api/me` or Supabase
  call) and the saved payload found; its `setLists`/`setActiveList` did not reach the DOM until
  +1.9s. A per-render/per-commit probe showed the restored state rendered and thrown away twice,
  with five base-state commits going out in front of it, all under ONE component instance (checked
  with a per-instance id — it is not a remount). Because every restart costs a full render of this
  5,500-line shell while the interrupting sources keep their own cadence, the delay is SUPERLINEAR
  in machine load: at 4x CPU throttle the correct list never appeared inside a 300s budget at all.
  The user-visible form is that a signed-in user on a loaded machine sees the guest/default
  watchlist — someone else's data — for the whole session.
falsifier: >
  Any of: the restore landing in a `useLayoutEffect` (mastermind-terminal PR #457 does this, so on
  current master the window is zero and the ordering guard in
  `terminal/e2e/watchlist-ownership.spec.ts` holds); a trace showing the restored state RENDER
  followed immediately by its own COMMIT with no interleaved base-state commit; two distinct
  instance ids in that trace, which would make it a remount and not starvation; or the rail
  reading the owner's list at `E2E_CPU_THROTTLE=4` with the restore back on a passive effect.
so_what: >
  Three things a future session should carry. (1) "The effect ran on time" does NOT mean "the state
  is on screen" — in a tree that re-renders continuously during boot, effect-scheduled updates are
  a scheduling question, not a latency one, and a passive effect buys you "usually fast". State
  that decides WHOSE data is displayed must land in a layout effect, which React flushes
  synchronously before paint and therefore cannot starve. Same reasoning already forced the
  owner swap in that file to be adjusted DURING RENDER rather than in an effect. (2) Diagnose this
  shape by instrumenting RENDER and COMMIT separately plus a per-instance id: renders going
  BACKWARDS with one instance id and no commit between them is discarded concurrent work, and
  reads exactly like a remount if you only sample the DOM. Sampling `.wl-select` from the test side
  cannot tell the two apart, which is why the symptom was mis-filed for weeks as a fixture-seeding
  race. (3) Guard the fix by ORDERING, never by a millisecond budget — a budget just re-times the
  race on the next machine. The shipped guard reads two DOM facts in ONE `page.evaluate` so no gap
  can open between them.
kind: landmine
verified_at: 2026-08-22
verified_by: >
  Instrumented `terminal/components/TerminalShell.tsx` with a per-render / per-commit trace and a
  `useRef` instance id, driven by a throwaway Playwright spec that seeds one owner through
  `e2e/watchlistStore.ts#seedOwnerWatchlists` and samples `.wl-select` / `.wl-row` / `.mm-ptag`
  from navigation commit. CPU throttling via CDP `Emulation.setCPUThrottlingRate`
  (`E2E_CPU_THROTTLE`). Passive effect: rail correct at +2.1s at 1x, and NOT within the 300s test
  budget at 4x. Layout effect: correct at the first sampled frame at 1x, 4x and 8x. The ordering
  guard folded into `terminal/e2e/watchlist-ownership.spec.ts` fails 6/6 on the old code across all
  three viewport projects and passes 3/3 on the new. Shipped in mastermind-terminal PR #457.
scope: [terminal]
confidence: verified
---

## Detail

The reported symptom pointed somewhere else entirely — a retry/backoff on whatever resolves the
account identity, since the delay grew superlinearly with load and that is what a backoff looks
like from the outside. It was worth checking and it was wrong: `/terminal` resolves the auth uuid
on the SERVER and hands it down as a prop, so by the time any client code runs there is nothing
left to retry. The first probe sample already carried the right owner key.

Two things made this expensive to see.

**The DOM cannot distinguish "not yet restored" from "restored and discarded".** Polling
`.wl-select` from the test side shows `Default` in both cases. The trace that settles it has to
come from inside the component, and it has to separate RENDER from COMMIT — a component that
renders `restored=true` and then renders `restored=false` again looks like a remount until you
confirm the instance id is unchanged and no commit happened in between.

**The failure had already been explained, plausibly and incorrectly.** It surfaced as
`watchlist-bulk-actions.spec.ts` going red on loaded CI runners at `.wl-select` reading `"Default "`
instead of the seeded list, and had been filed as a fixture-seeding race — the seeding helper in
that file genuinely does have a subtle guard (`addInitScript` re-runs on every navigation, so the
write must be conditional), so the story fit. The seed was landing every time. What the spec's
shared `boot()` was actually measuring is the default 5s expect budget after the chart paints, and
the restore was blowing through it. A wrong-but-plausible prior explanation is the expensive part
of this class of bug, not the scheduler behaviour.

**Scope note.** The sibling mount restore in the same file — `mm.inds` / `mm.ct` / `mm.tf`, i.e.
indicators, chart type and timeframe — is still a passive effect and still starves the same way.
It was deliberately left alone: it produces a visible flash of the wrong DEFAULTS, which is a
polish defect, not the wrong owner's data. If that surface is ever reported as "my indicators take
ages to come back on a slow machine", this is the cause and the fix is the same one line.
