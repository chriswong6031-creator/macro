---
key: PERSONAL-PRO-INGRESS-PRINCIPAL-GAP
claim: >
  As of 2026-08-27, the accepted PR #159 login-Keychain verifier bridge has been
  exercised on the Chairman Mac against the live disposable fixture credential
  from a clean protected Mastermind checkout at
  `e4e44867ace335ac9208a3990a10c163e199492d`. It returned the allowlisted
  `METADATA_SCOPE_MISMATCH` refusal. Chairman then inspected only the non-secret
  Slack Bot Token Scopes and reported 19 installed bot scopes. Both frozen
  required scopes, `groups:history` and `chat:write`, are present; the token has
  17 additional bot scopes and is therefore over-privileged. Current protected
  Mastermind has since advanced to
  `be68ec881460aa60d7d77cdb69f7c1cae81f6310` via records-only PR #168. PR #168's
  S0 predecessor snapshot does not override this later live runtime receipt;
  its own law preserves existing component security rules. C1 remains
  independently nonterminal on the existing PR #155 carrier.
falsifier: >
  Remediate only the existing disposable fixture's OAuth grant under a new
  bounded Sol-authorized fixture-qualification ceremony. Keep the app/fixture
  identity and frozen minimum authority; do not weaken the verifier, create
  S0-R2, create a replacement fixture, or send another source probe. Slack's
  current first-party OAuth law says scope grants are additive and an existing
  access token cannot be downgraded: removing requested scopes from app config
  does not strip them from the already-issued token. Therefore the current
  over-granted token must be revoked/uninstalled through a credential-safe human
  admin boundary and the same fixture app freshly authorized with only the
  frozen bot scopes before the Keychain credential can be replaced and the
  verifier requalified. C1 still requires its existing PR #155 return plus
  MAS-109 production proof.
so_what: >
  `LIVE_KEYCHAIN_VERIFIER_RECEIPT_REQUIRED` is closed. The active gate is
  `LIVE_FIXTURE_OVERGRANTED_TOKEN_REMEDIATION`: 19 observed bot scopes versus 2
  allowed, with 17 excess grants. S0-R1 is not PASS and the 20-row framed-carrier
  kill gate has not yet run to a terminal result. MAS-112 remains nonterminal;
  B2/C2 remain held; zero Executive mutation has occurred.
kind: runtime
verified_at: 2026-08-27
verified_by: >
  Chairman-native verifier receipt
  `{"error":"METADATA_SCOPE_MISMATCH","schema":"mastermind.slack_agent_dialogue.metadata_verification.v1","status":"ERROR"}`;
  Chairman non-secret Slack admin scope census; Mastermind PR #159 / merge
  `7d160ff47df1bca0ac6312141e6e1134bbce6539`; current protected Mastermind PR
  #168 / merge `be68ec881460aa60d7d77cdb69f7c1cae81f6310`; Slack first-party OAuth docs
  `https://docs.slack.dev/authentication/installing-with-oauth/` and
  `https://docs.slack.dev/app-management/distribution/`; live Slack channel
  census confirming bot `U0BST4WG996` in `C0BRUL9F2V7`; Linear MAS-112 corrected
  from false-green Done to In Progress.
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

The Chairman ran that helper from a clean protected Mastermind checkout at
`e4e44867ace335ac9208a3990a10c163e199492d`. It returned:

```json
{"error":"METADATA_SCOPE_MISMATCH","schema":"mastermind.slack_agent_dialogue.metadata_verification.v1","status":"ERROR"}
```

Because the verifier validates Slack response shape and team/bot identity before
exact scope equality, this narrowed the live defect to the OAuth grant rather
than a generic Keychain/auth failure. Slack channel census independently showed
fixture bot `U0BST4WG996` still present in private channel `C0BRUL9F2V7`.

### Exact non-secret scope census

The Chairman then inspected the fixture's Slack **Bot Token Scopes** without
exposing any credential. The observed set contains 19 scopes:

- `app_mentions:read`
- `assistant:write`
- `bookmarks:read`
- `bookmarks:write`
- `calls:read`
- `calls:write`
- `canvases:read`
- `canvases:write`
- `channels:history`
- `channels:join`
- `channels:manage`
- `channels:read`
- `channels:write.topic`
- `chat:write`
- `files:read`
- `files:write`
- `groups:history`
- `groups:read`
- `groups:write`

Required and present: `chat:write`, `groups:history`.

Excess and forbidden for this disposable fixture: the other 17 scopes. This is
not a missing-scope problem; it is an over-granted-token problem.

App-level Socket Mode authority such as `connections:write`, where required by
the frozen fixture law, is a separate app-token scope and is not part of this
Bot Token Scope equality check.

### Provider-law consequence

Slack's current first-party OAuth documentation states that installations are
additive: later authorization can add scopes but an already-issued access token
cannot be downgraded. Slack's app lifecycle documentation likewise states that
removing scopes from app configuration does not remove those grants from
existing tokens; those tokens retain the removed scopes until revoked/uninstalled.

Therefore **do not** repair this by changing the verifier to accept the broad
scope set, and do not assume deleting 17 rows then pressing Reinstall will make
the existing token least-privilege.

The smallest lawful remediation is a separate bounded fixture-qualification
ceremony under the **same disposable fixture app identity**:

1. configure requested **Bot Token Scopes** to exactly `groups:history` and
   `chat:write`;
2. preserve only separately-required app-level Socket Mode authority under the
   existing fixture law;
3. revoke/uninstall the currently over-granted installation/token through a
   credential-safe Chairman Slack-admin boundary;
4. freshly authorize/install the same fixture app with the reduced grant;
5. if uninstall removed the bot from `C0BRUL9F2V7`, re-invite only that fixture
   bot to that private test channel;
6. replace the fixed login-Keychain item's password with the newly issued bot
   token through a human/native secret-safe boundary; never paste the token into
   chat, Slack, Linear, GitHub, shell argv, logs or repo files;
7. only after current protected Mastermind/Skillpack and app/bot/channel identity
   are rechecked may Sol authorize one new metadata-verifier requalification;
8. only a PASS may release the remainder of the existing MAS-112 three-seat / 20-row
   S0-R1 experiment.

This is fixture remediation, not S0-R2 and not a replacement fixture. The failed
PR #159 verifier operation remains closed; do not blind-rerun it before the grant
has actually changed.

Current protected Mastermind advanced after the verifier run to PR #168 / merge
`be68ec881460aa60d7d77cdb69f7c1cae81f6310`. PR #168's records-only ledger called
S0-R1 an accepted predecessor based on prior Linear/Git history, but its own
supersession law preserves component source/security laws. This later native
receipt and admin census therefore correct current capability state without
rewriting the historical #168 snapshot: S0 is nonterminal until the exact-scope
fixture is requalified.

Linear MAS-112 has been repaired from false-green Done to In Progress and records
the verifier refusal. B2/C2 remain held.

## C1 current delta

Private `#sol-runtime` channel `C0BSGABKBFY` still lacks accepted production
Relay proof. Mastermind PR #155 remains the singular C1 implementation carrier;
no duplicate carrier is authorized. C1 must become production-proven before B2
may be released under the current Autonomy V1 sequencing.

None of these records creates an Executive Job, Attempt, Worker, operation key
or CEO intent. Slack remains transport; GitHub evidence; Agent OS durable
organizational truth; Linear projection. B2 and C2 remain held.
