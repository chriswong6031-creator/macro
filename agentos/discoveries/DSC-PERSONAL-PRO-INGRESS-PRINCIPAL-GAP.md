---
key: PERSONAL-PRO-INGRESS-PRINCIPAL-GAP
claim: >
  As of 2026-08-27, the accepted PR #159 login-Keychain verifier bridge is
  production-exercised on the Chairman Mac and repeatedly reaches Slack but
  returns the allowlisted `METADATA_SCOPE_MISMATCH` refusal. The latest native
  admin evidence materially refines the earlier scope census: the Slack app
  configuration now requests exactly `chat:write` + `groups:history`, but
  Installed App -> Authorizations still shows one older broad authorization for
  `MMX S0 Fixture`, dated Aug 23, 2026. That authorization exposes a native
  Revoke control. Therefore the current defect is not the fixed verifier and is
  not evidence that the reduced configuration failed to save; the old broad
  installed authorization remains present. C1 remains independently
  nonterminal on its existing PR #155 carrier.
falsifier: >
  Revoke the sole Aug 23 installed authorization for the existing disposable
  fixture app, then freshly install the same app `A0BS2DMVDC4` under the already
  reduced two-scope bot configuration. If a newly issued bot credential is
  produced, place it only into the fixed login-Keychain item through a
  Chairman-native secret-safe boundary. Then stop for Sol before any verifier
  rerun. Do not weaken the verifier, edit scopes again, create S0-R2, create a
  replacement fixture, or send another source probe. Slack first-party OAuth
  law states that scopes on an existing token are additive and cannot be
  downgraded without revocation/uninstall. C1 still requires its existing PR
  #155 return plus MAS-109 production proof.
so_what: >
  The previous `LIVE_FIXTURE_OVERGRANTED_TOKEN_REMEDIATION` diagnosis is refined
  to `OLD_BROAD_AUTHORIZATION_STILL_PRESENT`. The requested bot-scope
  configuration is correct, but the Aug 23 authorization has not been replaced.
  S0-R1 is not PASS and the 20-row framed-carrier kill gate has not yet run to a
  terminal result. MAS-112 remains In Progress; B2/C2 remain held; zero
  Executive mutation has occurred.
kind: runtime
verified_at: 2026-08-27
verified_by: >
  Chairman-native verifier receipts returning
  `{"error":"METADATA_SCOPE_MISMATCH","schema":"mastermind.slack_agent_dialogue.metadata_verification.v1","status":"ERROR"}`;
  Chairman-native Slack developer configuration showing exactly `chat:write` +
  `groups:history`; Chairman-native Installed App -> Authorizations evidence
  showing the sole broad `MMX S0 Fixture` authorization from Aug 23, 2026 and
  its Revoke control; Mastermind PR #159 / merge
  `7d160ff47df1bca0ac6312141e6e1134bbce6539`; Slack first-party OAuth docs
  `https://docs.slack.dev/authentication/installing-with-oauth/` and
  `https://docs.slack.dev/app-management/distribution/`; Linear MAS-112 current
  reconciliation comments; current Macro records ancestry through PR #6511 /
  merge `88a4e23df4b8a20aef1e7170a42c0dd6d49fd1ff`.
scope:
  - crypto-intelligence
  - executive-os
  - slack
confidence: verified
---

# Personal-Pro ingress principal gap

MAS-106 remains the immutable original whole-message S0 BLOCK. MAS-112 remains
the only authorized framed-carrier retry. The existing disposable fixture and
private test channel remain the only S0 fixture path; no S0-R2 or replacement
fixture is authorized.

## S0-R1 current delta

Mastermind PR #159 merged the fixed login-Keychain -> credential-safe metadata
verifier bridge as `7d160ff47df1bca0ac6312141e6e1134bbce6539`. Its live contract is exact:
team `T0BRD2AQXQV`, bot user `U0BST4WG996`, bot scopes exactly
`groups:history` + `chat:write`. The helper is intentionally fail-closed and
never emits arbitrary observed scope-header text on mismatch.

The Chairman has exercised that helper from clean protected Mastermind
checkouts. It repeatedly returned:

```json
{"error":"METADATA_SCOPE_MISMATCH","schema":"mastermind.slack_agent_dialogue.metadata_verification.v1","status":"ERROR"}
```

The first reconciliation correctly established that the currently effective
OAuth grant was broader than the verifier contract. The subsequent native admin
inspection provides a more precise current diagnosis and supersedes only the
older assumption about what the 19-scope screenshot represented.

### Configuration is now correct

The current Slack developer configuration for the same historical disposable
app `A0BS2DMVDC4` requests exactly two **Bot Token Scopes**:

- `chat:write`
- `groups:history`

Do not modify this requested bot-scope set again. App-level Socket Mode authority
such as `connections:write`, where required by the frozen fixture law, is a
separate app-token capability and is not part of this bot-token equality check.

### Installed authorization is still old and broad

Slack Installed App -> Authorizations still shows exactly one authorized member
entry for `MMX S0 Fixture`, dated **Aug 23, 2026**, with the older broad
permission set. The same native page exposes a **Revoke** control for that
authorization.

This corrects the prior records phrasing that treated the 19-scope screenshot as
direct telemetry for the newly configured token. The 19-scope view established
that the app had a broad authority history; the latest evidence establishes the
more important current fact: the old Aug 23 installed authorization itself is
still present even though the app's requested configuration has been reduced to
the exact two scopes.

The second verifier mismatch after the attempted reinstall is therefore
consistent with Slack continuing to use that unreplaced authorization. It does
not justify weakening the verifier or changing the requested scopes.

### Provider-law consequence

Slack's current first-party OAuth documentation states that authorization scopes
on an existing token are additive and cannot be downgraded. Slack's app
lifecycle documentation likewise states that removing scopes from app
configuration does not remove those grants from already-issued tokens; those
tokens retain the removed scopes until revoked/uninstalled.

Therefore the smallest lawful remediation is now narrower and explicit:

1. keep requested **Bot Token Scopes** exactly `groups:history` and `chat:write`;
2. on Installed App -> Authorizations, revoke the sole Aug 23, 2026 authorization
   for the existing `MMX S0 Fixture` app;
3. freshly install/authorize that same app `A0BS2DMVDC4` under the already
   reduced two-scope configuration;
4. if the revoke/reinstall removes bot `U0BST4WG996` from private fixture channel
   `C0BRUL9F2V7`, re-invite only that existing fixture bot to that channel;
5. if Slack issues a fresh bot credential, replace only the fixed login-Keychain
   item's password through a Chairman-native secret-safe boundary; never paste
   the credential into chat, Slack, Linear, GitHub, shell argv, logs or repo
   files;
6. then stop for Sol before any metadata-verifier rerun;
7. only after current protected Mastermind/Skillpack plus app/bot/channel
   identity are rechecked may Sol authorize one fresh metadata requalification;
8. only an allowlisted PASS may release the remainder of the existing MAS-112
   three-seat / 20-row S0-R1 experiment.

This is remediation of the same authorized fixture, not S0-R2 and not a
replacement fixture. Do not send another Slack source-message probe while this
preflight gate is open.

Linear MAS-112 remains In Progress and contains the native verifier/admin
reconciliation. B2/C2 remain held.

## C1 current delta

Private `#sol-runtime` channel `C0BSGABKBFY` still lacks accepted production
Relay proof. Mastermind PR #155 remains the singular C1 implementation carrier;
no duplicate carrier is authorized. C1 must become production-proven before B2
may be released under the current Autonomy V1 sequencing.

None of these records creates an Executive Job, Attempt, Worker, operation key
or CEO intent. Slack remains transport; GitHub evidence; Agent OS durable
organizational truth; Linear projection. B2 and C2 remain held.
