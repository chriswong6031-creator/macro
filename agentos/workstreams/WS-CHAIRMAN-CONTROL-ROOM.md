---
key: CHAIRMAN-CONTROL-ROOM
title: Chairman Control Room — cross-session organizational navigation
objective: >
  Remove Chris from manual session discovery and project-to-tab routing. Done means
  one private local Control Room on the Chairman's Mac composes canonical Executive
  OS, Agent OS and GitHub active-build truth for real current work, exposes explicit
  degraded/unbound states, and one-click opens the exact bound Sol, Fable, worker
  and evidence surfaces without creating another lifecycle/control plane.
status: active
program: project-active-build-control
p0: EXECUTIVE_OS
repos: [macro, mastermind]
owner: ceo-sol
class: build
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: F0
    title: Architecture freeze and FABLE-00 commission
    status: done
  - id: P0A
    title: Control Room compositor, local UI, Fable/worker/PR navigation and managed-seat discovery
    status: done
    depends_on: [F0]
  - id: H0
    title: P0A post-merge hardening and persistent-8787 adoption
    status: in_progress
    depends_on: [P0A]
    next_action: >
      Replace the stale persistent Chairman port-8787 process with a process launched from
      merged Mastermind 0f319c79a7b3373a96d4866412c734de12cbf701 and a maintained current
      Macro root, then verify the persistent instance reports the merged Mastermind SHA,
      serves the cached API/UI, preserves the real binding store, and surfaces degradations honestly.
  - id: P0B
    title: Vendor-supported managed-browser Open Sol actuator
    status: todo
    depends_on: [P0A]
    next_action: >
      Establish a current vendor-supported exact-seat/exact-conversation attach/open contract,
      or a documented persistent automation-launch mode that preserves the same seat state;
      only then run a bounded non-seat canary before real-seat proof.
decisions:
  - DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED
discoveries:
  - DSC:CCR-MANAGED-BROWSER-RUNNING-SEAT-ACTUATOR-MISSING
  - DSC:CCR-PROCESS-SNAPSHOT-OUTPUT-CAP-CAN-HIDE-RUNNING-SEATS
artifacts:
  - agentos/decisions/DEC-CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED.md
  - agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-22-sol-architecture.md
  - agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-22-p0a-partial-release.md
  - agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-22-h0-release.md
landmines:
  - "Surface bindings are local navigation addresses only; they are not runtime, role, workstream, completion, liveness or authority records."
  - "A tab/window/process title may be a candidate locator but never proves work ownership or execution."
  - "Open actions may focus/resume a surface only; P0 may not type prompts, send messages, dispatch work or wake a CEO."
  - "Linear remains projection. A Linear assignee or status never proves a provider session claimed the work."
  - "Missing exact joins stay UNKNOWN/UNBOUND; title or objective similarity may not manufacture identity."
  - "The Chairman's Personal-Pro seats live in persistent GoLogin/Multilogin environments; ordinary Chrome profiles are superseded for this program."
  - "Installed Multilogin/GoLogin surfaces do not currently provide a documented lawful attach/open primitive for a GUI-started already-running seat; ChatGPT navigation must remain unsupported_surface rather than use an unofficial fallback."
  - "Managed-browser process argv can carry proxy credentials; observation may reduce it only to non-secret booleans/known ids and must never log/store raw argv."
  - "X-CCR-Token is a per-process browser-origin/CSRF capability nonce, not authentication against another same-user local process; GET / intentionally bootstraps that nonce."
  - "The M3 Ultra MASTERMIND_MACRO_ROOT environment override has been observed pointing at a stale Aug-13 macro-agentos-canon checkout; production use must select a maintained current Macro read path without silently changing Executive root semantics."
  - "Agent OS brief cost on the M3 Ultra is highly variable: H0 measured about 166s on one run and more than the 240s compose ceiling minutes later; H0 serves honest degraded last-good state, but the Macro-side git_dates/brief cost remains a separate performance problem."
  - "The persistent Chairman :8787 process was observed running superseded pre-correction code; H0 is merged but MAS-114 is not operationally done until that process is relaunched from the merged hardened master/current Macro root and verified."
  - "The committed project_active_builds.json projection was observed stale since Aug-11; merged Macro #6225 provides the reviewed fresh no-write JSON stdout path."
  - "MAS-113 was double-dispatched once; the duplicate session reverted its transient edit and stood down."
do_not_redo:
  - "Do not create a Session OS, task database, tmux lifecycle registry, second Executive service, mutable seat inbox or new active-build compiler."
  - "Reuse Mastermind control_plane.executive_inbox, control_plane.ceo_boot_packet and Macro scripts/build_project_active_build_map.py."
  - "Do not absorb MAS-48 B1/C1/B2/C2, generic agent dispatch, automatic return routing, CEO wake, provider credentials or multi-host capacity routing."
  - "Do not commit private ChatGPT URLs, browser target IDs, credentials, chat text or local surface_bindings.json."
  - "Do not use ordinary Chrome as a fallback for the Chairman's managed-browser seats."
  - "Do not perform xcli/cloud login, hold raw vendor credentials, or experiment with undocumented repeat-start on a real seat to make Open Sol look complete."
  - "Do not treat the H0 merge as proof that the persistent :8787 user path was replaced; verify the live process after relaunch."
next_action: >
  Relaunch the persistent Chairman :8787 Control Room from merged Mastermind
  0f319c79a7b3373a96d4866412c734de12cbf701 using a maintained current Macro root and
  verify the merged SHA, binding persistence, cached state path and honest degraded behavior.
  Keep MAS-113 nonterminal; MAS-115/P0B may continue independently; do not start P1.
---

## Capability state

`PARTIAL` overall. P0A plus H0 implementation is merged and real-M3 proven on the accepted
head, but the persistent Chairman :8787 process still needs adoption proof. P0B remains
`DARK_OR_DISCONNECTED` / `unsupported_surface`.

### Immutable P0A + H0 receipts

- Macro PR #6225 merged as `5603972754e5320f06c04b08c24ed143bd30b2a2`.
  It adds the no-write `project_active_builds.v1` JSON stdout seam and no new lifecycle
  authority or persistence.
- Mastermind PR #110 merged as `90db9baf5bcc5f2221e3c9870c2aa09a95293c99`
  from exact reviewed head `98c8834aca28fa8d7e0ba5113836edd062e11425`.
- Mastermind PR #113 H0/H1 hardening merged as
  `0f319c79a7b3373a96d4866412c734de12cbf701` from exact accepted head
  `d0c649d9f99b52a1b0f80c8757bc65e1951fc40c` after CI `32599272414` and CodeQL
  `32599271255` succeeded and Sol review `5001161545` accepted the implementation.

H0 moves expensive organization composition off the request path into a process-memory
last-good cache with single-flight background refresh, makes the browser-origin nonce contract
truthful, prevents stale background composition from overwriting newer explicit refresh state,
and updates the operator guide. Real M3 proof covered restart recovery, desktop/narrow UI,
no-secret/no-canonical-write behavior and named degraded-source rendering.

### What is still false

1. The persistent Chairman :8787 process has not yet been proven relaunched from the merged
   H0 master/current Macro root. MAS-114 remains nonterminal until that live user path is replaced.
2. The original one-click `Open Sol` requirement remains incomplete for persistent managed-browser
   seats. The installed GoLogin/Multilogin surfaces have not proven a documented lawful exact-seat
   exact-conversation actuator; the adapter therefore refuses closed.
3. Agent OS brief latency remains variable enough to exceed the 240s H0 compose ceiling. H0 handles
   that failure honestly; it does not solve the Macro-side performance root cause.

## Completion boundary

MAS-114 reaches Done only after the persistent :8787 process is verified on merged H0 code/current
Macro input. MAS-113 remains nonterminal until P0B proves the vendor-supported managed-seat Open Sol
journey with zero cross-seat fallback, zero message send, zero managed-environment state mutation,
and required restart/failure proof. Neither condition authorizes P1 by itself.
