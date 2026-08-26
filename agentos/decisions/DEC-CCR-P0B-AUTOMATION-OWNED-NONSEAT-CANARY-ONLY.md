---
key: CCR-P0B-AUTOMATION-OWNED-NONSEAT-CANARY-ONLY
question: >
  Does current GoLogin/Multilogin vendor evidence justify changing the Chairman's existing
  GUI-started seats or declaring exact URL navigation sufficient for P0B Open Sol, and what
  next proof is lawful before any real-seat operation?
answer: >
  No current supported contract adopts the Chairman's already-running GUI/manual managed-browser
  process, and exact background URL navigation is not sufficient to complete Open Sol because
  intended-seat foreground activation remains part of the Chairman's anti-hunting user journey.
  Accept the documented automation-owned persistent lifecycle only as a candidate substrate for
  a bounded disposable NON-SEAT canary. No real-seat lifecycle migration, private ChatGPT URL,
  Chairman vendor credential, stop/restart, cross-seat fallback or P0B completion is authorized.
rationale: >
  Current official vendor contracts support exact profile launch and exact URL navigation when
  the profile is started under vendor automation ownership. GoLogin's Local Agent Browser keeps
  an SDK/CDP-owned profile session; Multilogin exposes an automation port only for profiles started
  in automation mode. Neither vendor currently documents adopting a manual GUI-started process.
  Neither provides an accepted programmatic OS-window foreground contract; Multilogin's supported
  Bring to front is a human GUI operation while RPA is unsupported. The smallest useful next proof
  is therefore disposable lifecycle/navigation falsification, not real-seat migration. The MAS-125
  token-isolation incident also establishes that any vendor credential used by the canary must
  stay outside model-visible settings/browser tooling and use a human-controlled secure boundary.
alternatives:
  - option: Declare exact URL navigation sufficient and complete P0B after a navigation canary
    why_not: >
      Narrows the Chairman outcome. A correctly navigated conversation hidden in an unfocused
      managed window still leaves the Chairman hunting for the session.
  - option: Attach to the current GUI-started Chairman process using inferred CDP ports or GUI/RPA automation
    why_not: >
      No supported vendor contract was established and the existing program explicitly forbids
      ordinary-Chrome fallback, GUI scripting, undocumented repeat-start and hidden credential use.
  - option: Migrate a real Chairman seat immediately to automation-owned lifecycle
    why_not: >
      Skips the required non-seat falsifier and risks duplicate processes, session/state drift,
      auth leakage, focus failure or disruptive seat restart without disposable evidence.
  - option: Keep the current GUI lifecycle immutable and stop all P0B work permanently
    why_not: >
      The current automation-owned launch contracts are credible enough to justify a bounded
      disposable canary; the negative claim should remain falsifiable rather than permanent.
evidence:
  - "MAS-115 research packet: ruling B — partial contract / architecture decision required, 2026-08-23"
  - "Linear MAS-115 Sol architecture review, 2026-08-23"
  - "DSC:CCR-MANAGED-BROWSER-RUNNING-SEAT-ACTUATOR-MISSING remains true for GUI-started seats"
  - "Mastermind PR #110 / H0 program boundary: managed-seat Open Sol remains unsupported_surface"
  - "Mastermind PR #125 A0 token-isolation falsifier establishes model-visible settings are not a safe credential boundary"
affects:
  - WS:CHAIRMAN-CONTROL-ROOM
  - MAS-113
  - MAS-115
  - mastermind/integrations/chairman_surfaces/**
  - macro/agentos/**
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

## Accepted non-seat proof boundary

A disposable profile canary may prove only the supported substrate:

- exact pre-authorized profile identity;
- one supported automation-owned launch;
- exact benign-URL navigation;
- same-owner reuse without repeat-start or duplicate process;
- supported close/sync and benign state persistence;
- owner-loss, missing profile, expired/missing auth and conflict refusal;
- zero cross-seat fallback;
- zero click/type/fill/send/login/profile mutation/unlock/clone/delete behavior;
- secret-safe receipts containing no raw URL, credential, proxy, cookie, fingerprint or process argv.

Any disposable credential must be provisioned through a human-controlled secure source into a
narrow helper without entering model-visible browser/settings surfaces, argv, environment, temp
files, shell variables, logs or receipts. The reviewed Mastermind Keychain-to-stdin pattern is the
precedent; this decision does not create a generic credential service.

Observed foreground behavior may be recorded during the canary but cannot satisfy the P0B focus
gate unless a current supported vendor contract makes programmatic foreground activation explicit.
A real-seat canary remains a separate Chairman-authorized operation after non-seat proof and focus
adjudication.
