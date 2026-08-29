---
workstream: WS:CHAIRMAN-CONTROL-ROOM
session: sol/web-sol-surface-adapter-s0s1-20260829-sol-001
model: sol
ended_because: blocked
mission: >
  Preserve the current Web-Sol S0/S1 exact-surface child pickup and pre-implementation ruling so a
  fresh Sol can resume the same operation without reconstructing it from chat: prove the current
  source/collision boundary, distinguish documented managed-browser extension support from still-
  unproven native-messaging behavior, and hold all runtime implementation until the accepted #214
  organizational-continuity release gate is protected/merged.
state_before: >
  The direct WS:CHAIRMAN-CONTROL-ROOM workstream record still ended at the older P0B/ASD frontier and
  did not name the later WSX S0/S1 child. Mastermind PR #188 had frozen the Web-Sol architecture,
  PR #212 had frozen the implementation sequence, Linear MAS-198 projected the child as Todo, and
  Slack #agent-dispatch carried an OPEN_PICKUP packet requiring a live Chairman delivery to one exact
  CEO Sol session. Mastermind PR #214 remained the explicit runtime release gate.
changed:
  - path: agentos/handoffs/CHAIRMAN-CONTROL-ROOM-2026-08-29-web-sol-s0s1-preflight.md
    what: >
      Add this records-only continuation checkpoint. It does not create a new workstream, wave,
      lifecycle, browser controller, watcher registry or implementation carrier and deliberately does
      not rewrite the existing P0B/ASD workstream next_action while those independent lanes remain live.
verified:
  - claim: The selected CEO Sol session has the current live receiver assignment for operation web-sol-surface-adapter-s0s1-20260829-sol-001.
    command: >
      Current Chairman delivery plus exact Slack #agent-dispatch parent 1787974242.878569 and the
      same-thread SOL PICKUP receipt were read/written through the connected Slack transport.
    result: >
      The outer live Chairman directive delivered `take web-sol-surface-adapter-s0s1-20260829-sol-001`;
      the canonical pickup packet names MAS-198/#188/#212/#214 and states that this delivery selects
      the one action-authoritative Sol. No prior worker reply or competing same-child action edge was
      present on that thread at pickup.
  - claim: Current protected Mastermind source for this preflight is c653c8e810ad91e8f1224df828d60c242c3aaf2f with compatible mastermind.sol_skillpack.v1 v1.0.1 / bootstrap major 1.
    command: >
      GitHub protected-master branch read followed by same-SHA reads of docs/sol_skills/INDEX.md,
      COLD_START.md, COMMISSION_WAVE.md, WORKER_AVENUE_ROUTING.md and WATCHER_ACTION_LOOP.md.
    result: >
      Protected master resolved to c653c8e810ad91e8f1224df828d60c242c3aaf2f and the loaded Skillpack
      declares minimum_bootstrap_major 1.
  - claim: PR #214 is still a hard execution gate and no Web-Sol runtime implementation has started from this child.
    command: >
      GitHub PR #214 and workflow-run 33231472055 reads at the preflight checkpoint.
    result: >
      #214 was OPEN / unmerged at head 35a2ea893cd57da38d12662ccb3ccd78619e964e;
      its exact-head CI run was still in_progress. The Sol receipt therefore classified the child as
      PREFLIGHT ONLY and did not create or modify Web-Sol runtime code.
  - claim: The planned Tasks 1-4 are additive relative to protected runtime source and known active WP-TW1 / Company Dialogue carriers.
    command: >
      Protected integrations/chairman_surfaces directory plus PR #209/#210/#188/#212/#214 file-list reads.
    result: >
      No protected web_sol_protocol.py, web_sol_native_host.py or web_sol_extension surface exists.
      PR #209 changes integrations/slack_agent_dialogue; PR #210 changes integrations/mastermind_company_mcp;
      #188/#212/#214 are records-only. The first deliberate shared runtime seam is later Task 5 in
      integrations/chairman_surfaces/chatgpt.py and must receive a fresh collision check before edit.
  - claim: Existing ChatGPT managed-seat behavior is fail-closed and exact conversation identity is already constrained by surface_bindings.
    command: >
      Same-SHA reads of integrations/chairman_surfaces/chatgpt.py and control_plane/surface_bindings.py.
    result: >
      open_surface() refuses all navigation/actuation paths today; surface_bindings remains
      navigation-only and permits exact HTTPS conversation URLs only on chatgpt.com or chat.openai.com,
      including normal /c/<id> and exact Project-chat deep-link forms.
  - claim: Custom/profile-local Chrome-compatible extension loading is currently documented by both managed-browser vendors, but native-messaging execution inside the installed Mimic/Orbita cores is not yet production-proven.
    command: >
      Current official Multilogin, GoLogin and Chrome extension/native-messaging documentation review.
    result: >
      Multilogin documents custom/team-built extensions in Mimic profiles; GoLogin documents unpacked
      custom Chrome-compatible extensions per profile. Chrome documents MV3 nativeMessaging with a
      registered host, exact allowed_origins, stdio framing and service-worker invocation. Neither
      vendor source reviewed here explicitly guarantees its product-specific native-host discovery
      path, so that predicate remains unverified until a disposable installed-browser proof.
  - claim: Native-host trust requires a stable exact Web-Sol extension identity.
    command: >
      Current Chrome native-messaging and manifest-key documentation review.
    result: >
      Native host allowed_origins cannot use a wildcard and the Chrome manifest key can hold a
      consistent extension ID during development. The first implementation must therefore pin one
      deterministic public extension identity rather than allow an unpacked-path-dependent ID to drift.
unverified:
  - claim: The Chairman host's installed Multilogin Mimic core discovers and launches a registered native-messaging host using the expected product-specific macOS manifest location.
    what_would_verify: >
      A disposable non-sensitive Mimic profile with the exact reviewed extension identity sends one
      closed INSPECT request through chrome.runtime.sendNativeMessage/connectNative and receives one
      bounded receipt from the local host; no Chairman seat is installed or changed.
  - claim: The Chairman host's installed GoLogin Orbita core discovers and launches the same closed native-messaging bridge shape.
    what_would_verify: >
      Equivalent disposable Orbita proof if GoLogin is selected for canary coverage; vendor-specific
      host registration must be observed rather than inferred from Chromium ancestry.
  - claim: Exact S0 observation and S1 foreground behavior work against a real disposable ChatGPT conversation without content leakage.
    what_would_verify: >
      After the #214 release gate and implementation, run the accepted disposable canary matrix:
      exact target, duplicate-looking tab, binding drift, extension/native-host absent, auth/provider
      error, restart and foreground postcondition, plus leakage scan.
unresolved:
  - "Mastermind PR #214 remains open, so WSX runtime START is forbidden at this checkpoint."
  - "Managed-browser custom-extension support is documented, but native-messaging host discovery in actual Mimic/Orbita installations remains an installed-product falsifier rather than a proven capability."
  - "Before Task 5 touches chatgpt.py, re-run open-PR/path collision review on then-current protected master."
  - "The direct Agent OS workstream record does not yet enumerate WSX; this handoff records the child without overwriting the independent P0B/ASD next_action. A later accepted organizational reconciliation may add the explicit wave projection."
next_actions:
  - "Keep the existing hourly condition watch on #214 bound to this exact child; it is attention only and grants no implementation authority."
  - "When #214 becomes protected/merged, re-pin current protected Mastermind and the compatible Skillpack before any modification, then reconcile #188/#212/current Agent OS/GitHub/Linear/Slack state and all candidate runtime paths."
  - "If no collision or newer authority conflict exists, commission/drive the already-frozen bounded sequence: closed protocol -> MV3 state-only extension -> native-messaging bridge -> exact S1 foreground -> explicit existing chatgpt.py seam -> disposable managed-browser proof -> OCR-6 protocol/receipt handoff."
  - "Pin a deterministic public extension identity so native-host allowed_origins is exact and stable; refuse unknown extension ids/actions/schema/binding revisions."
  - "Do not install on or mutate Chairman chatgpt1/2/3 seats in the first carrier."
do_not_redo:
  - "Do not create a second WS:CHAIRMAN-CONTROL-ROOM workstream, OCR-6 owner, browser-state owner election, surface-health database, lifecycle, queue, retry plane or watcher registry."
  - "Do not weaken or replace the existing fail-closed chatgpt.py open_surface path; Web-Sol is an explicit reviewed seam only."
  - "Do not scrape transcript/model output, arbitrary DOM text, cookies, storage, clipboard, proxy/fingerprint state or credentials."
  - "Do not add debugger/CDP V1, click/type/send/arbitrary JavaScript, generic browser MCP, Wake, OpenClaw, S2 repair or S3 Web-Sol message wake to this child."
  - "Do not infer nativeMessaging support merely because a vendor says its browser is Chromium/Chrome-compatible; prove the native-host boundary on a disposable profile."
danger_areas:
  - "A native host manifest that accepts a drifting unpacked extension ID breaks the intended exact allowlist. Keep the extension identity deterministic and public; never solve this with wildcard allowed_origins."
  - "Chrome's documented native-host locations are browser-product specific. Mimic/Orbita may use a vendor-specific application/profile path; product behavior must be measured on the disposable host rather than guessed."
  - "Content scripts are less trusted than the extension service worker. Treat every content-script message as attacker-controlled input and keep privileged native actions closed and revalidated in the service worker/native host."
  - "Surface health is ephemeral observation only and must never become work/lifecycle truth or elect the Sol owner."
  - "Green CI/extension install/native-host launch/foreground success are distinct from production proof and final Chairman acceptance."
prs: [188, 209, 210, 212, 214, 215]
decisions:
  - DEC:CHAIRMAN-CONTROL-ROOM-P0-ARCHITECTURE-ACCEPTED
  - DEC:CCR-SOL-IDENTITY-IS-NOT-A-CHAT
discoveries:
  - DSC:CCR-MANAGED-BROWSER-RUNNING-SEAT-ACTUATOR-MISSING
---

# Return point

`web-sol-surface-adapter-s0s1-20260829-sol-001` is picked up by the selected Sol and is in
**PREFLIGHT ONLY** while Mastermind #214 is unmerged. Protected Mastermind is pinned at
`c653c8e810ad91e8f1224df828d60c242c3aaf2f`. The additive Tasks 1-4 have no known collision with
#209/#210; legacy `chatgpt.py` remains deliberately fail-closed and becomes a later explicit seam only.

Vendor documentation establishes that profile-local custom extensions are a plausible substrate in
both Mimic and Orbita, but actual native-messaging host discovery remains unproven on the installed
managed-browser cores. The first implementation must also pin a deterministic extension ID because
Chrome native messaging requires exact non-wildcard `allowed_origins`.

Resume the same child only after #214 is protected/merged and a fresh current-source/collision re-pin
passes. No Chairman seat mutation is authorized by this checkpoint.
