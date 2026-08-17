- fix a stale server projection;
- fix a stale frontend expectation;
- introduce a versioned additive contract;
- deploy the already-correct bytes.

Incorrect remedies:

- catch the validation error and render anyway;
- delete the validator;
- make required fields optional because production is failing;
- turn malformed content into `[]`.

### B5. API 503: public-projection branch

`_read_bundle()` is now the suspect. Before touching source collection:

1. read `current.json` from `/var/lib/macro-biocatalyst/public`;
2. verify the generation directory exists;
3. inspect the generation manifest;
4. run `PublicGenerationPublisher(...).read_trial_projection()` in the **macro-api venv and namespace-equivalent environment**;
5. record the exact `PublicationError.code` or exception;
6. inspect `journalctl -u macro-api` for the matching warning;
7. confirm the macro-api service can read the public root and cannot read the private state root, as designed;
8. compare public root path in loaded unit with repository unit (`BIOCATALYST_PUBLIC_ROOT=/var/lib/macro-biocatalyst/public`).

If the generation itself is invalid, do **not** “repair” evidence bytes in place. Determine whether:

- the pointer references a missing/incomplete generation;
- deploy/runtime path is stale;
- publisher and reader versions disagree;
- publication was interrupted;
- a prior valid generation can be restored through the existing rollback mechanism;
- remediation would alter the still-open source soak.

### B6. Auth branch

If a real session fails before the API reader:

Check in this order:

1. served `theme.js` contains a non-null `SUPABASE_CFG` and correct project `ref`;
2. `supabase.js` loads 200;
3. `window.MDXAuth.enabled()` is true;
4. `window.MDXAuth.client()` resolves;
5. `client.auth.getSession()` returns a session;
6. token expiry is future;
7. BioCatalyst request actually carries `Authorization: Bearer ...`;
8. server `require_user` accepts it;
9. `enforce_site_full` returns paid tier.

Only after identifying the failing step should code change.

---

## C. Safe production diagnostic commands

These are templates. Do not paste secrets into command history, logs, PR descriptions, or handoffs.

### C1. Repository and deployment identity

```bash
git fetch origin main
git rev-parse origin/main
git status --short

gh pr list --state open --search 'biocatalyst' --json number,title,headRefName,updatedAt,url

ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
cd /opt/macro
git rev-parse HEAD
curl -fsS https://www.mastermind-x.com/api/health | python -m json.tool
```

### C2. Service identity without dumping secret environments

```bash
systemctl is-active macro-api.service
systemctl show macro-api.service -p FragmentPath -p ActiveState -p SubState -p ExecMainStartTimestamp
systemctl cat macro-api.service

systemctl is-active macro-biocatalyst.timer macro-biocatalyst-history.timer macro-biocatalyst-fixed-cohort.timer
```

**Do not run `systemctl show -p Environment` and paste the result into a session report.** The service has secret-bearing environment files.

### C3. Public generation read using the same Python estate as macro-api

```bash
/opt/macro-api/.venv/bin/python - <<'PY'
from engine.biocatalyst.publication import PublicGenerationPublisher
root = '/var/lib/macro-biocatalyst/public'
p = PublicGenerationPublisher(root)
proj = p.read_trial_projection()
health = p.read_operational_health()
print('generation=', proj.generation.generation_id)
print('trials=', len(proj.trials))
print('configured=', proj.generation.configured_nct_count)
print('observed=', proj.generation.observed_nct_count)
print('last_success_at=', proj.generation.last_success_at)
print('health_state=', health.get('state'))
print('health_error=', health.get('last_error_code'))
PY
```

If this fails, preserve the exception type/code. Do not modify the generation by hand.

### C4. Relevant server journal

```bash
journalctl -u macro-api.service --since '30 minutes ago' --no-pager \
  | grep -E 'BioCatalyst|biocatalyst|projection|Publication'
```

### C5. Entitled request without echoing the token

Prefer an operator-supplied protected file descriptor or `read -s`. Example:

```bash
read -s BC_TOKEN
printf '\n'
curl -sS -D /tmp/bc-local.headers \
  -H "Authorization: Bearer ${BC_TOKEN}" \
  -H 'Accept: application/json' \
  http://127.0.0.1:8000/api/biocatalyst/v1/health \
  -o /tmp/bc-local.json

curl -sS -D /tmp/bc-edge.headers \
  -H "Authorization: Bearer ${BC_TOKEN}" \
  -H 'Accept: application/json' \
  https://www.mastermind-x.com/api/biocatalyst/v1/health \
  -o /tmp/bc-edge.json

unset BC_TOKEN
```

Sanitize headers/body before attaching anything to a handoff. Authorization must never be captured.

---

## D. Minimal code changes the rescue is allowed to make

### D1. Frontend: stop silent auth downgrade

Target: `templates/biocatalyst.js` and paired `site/biocatalyst.js` only if the repository's pairing/render law requires it.

Replace the “auth failed -> anonymous headers” behavior with typed failure.

Desired semantics:

- auth runtime missing -> `AUTH_RUNTIME_MISSING`;
- auth disabled -> `AUTH_DISABLED`;
- SDK/session boot failed -> `AUTH_BOOTSTRAP_FAILED`;
- no session -> `SIGN_IN_REQUIRED`;
- session present -> bearer must be attached;
- 401/403 after a bearer -> server access result, not a retry as anonymous.

Use the already-existing `MDXAuth` seam. Avoid touching shared `theme.js` unless production evidence proves its contract is insufficient.

### D2. Frontend: introduce a typed transport error

The current `fetchJson()` discards nearly all response context. Replace the anonymous `Error('HTTP ' + status)` with a bounded error object carrying:

- stage: `auth | network | http | content_type | json | contract`;
- status;
- public error code/header when present;
- request ID when present;
- endpoint family;
- retryability.

Do **not** store the bearer, body, raw server traceback, or user identity on the error.

Check response `Content-Type` before `response.json()`. An HTML registration-wall or reverse-proxy body must classify as transport mismatch, not “registry unavailable.”

### D3. Frontend: preserve integrity-block state

When a `validate*Envelope()` or `validate*Page()` call throws:

- keep `contractFailed = true`;
- render the existing `integrity_block` precedence state prominently;
- say the **page/API versions disagree**, not that ClinicalTrials.gov is unavailable;
- retain a bounded request ID for support;
- do not render unvalidated rows.

### D4. API: add bounded machine-readable failure classes

Target: `app/biocatalyst.py` with focused API tests.

The API may continue to fail closed with 503. Add a public-safe code and request identifier, for example:

```json
{
  "detail": "trial intelligence temporarily unavailable",
  "code": "PROJECTION_UNAVAILABLE",
  "request_id": "..."
}
```

Potential public-safe classes:

- `PROJECTION_UNAVAILABLE`;
- `PROJECTION_INVALID` if the publication exception can safely distinguish it;
- `OPERATIONAL_HEALTH_UNAVAILABLE` for a degraded health subread that still permits data;
- `REQUEST_INVALID`;
- normal 401/403 access semantics.

Do not expose object keys, filesystem paths, hashes that are currently private, raw receipts, or internal tracebacks.

### D5. API: do not turn health degradation into data failure

The current code correctly allows projection data to serve if operational-health metadata alone cannot be read; it returns health state `unavailable` with `OPERATIONAL_HEALTH_UNAVAILABLE`. Preserve that distinction.

### D6. Add a separate hydration verifier; do not overload the design verifier

Proposed file:

`tools/` or `scripts/biocatalyst_hydration_verifier.py`

The verifier should accept an **operator-supplied, untracked authentication state** and produce a redacted receipt.

Required checks:

1. page 200;
2. `theme.js`, `supabase.js`, `biocatalyst.js`, CSS 200;
3. auth session resolves;
4. health API 200;
5. Milestones nonzero for the known proof cohort/window where records are expected;
6. Trial Screen nonzero;
7. Change Tape nonzero where history proof exists;
8. First-seen Tape: verify either nonzero **or the precise declared prospective coverage state** — do not require rows that the source contract legitimately cannot produce yet;
9. explicit Peer Matrix returns exactly the submitted NCTs in order;
10. dossier opens for a covered NCT;
11. source link points to expected ClinicalTrials.gov URL family;
12. no `pageerror`;
13. no unexpected console errors;
14. every private API response is JSON and `private, no-store`;
15. anonymous control resolves to locked, not unavailable;
16. receipt binds the served asset hashes and active generation identifier.

The verifier must redact:

- bearer tokens;
- cookies;
- full response bodies unless the body is already an approved browser projection;
- email/user IDs;
- internal R2 paths/receipts.

A CI fixture can test the verifier code; the real entitled acceptance run should be an operator/deploy gate, because GitHub CI should not need a reusable production account credential.

---

## E. Proposed P0 PR sequence

Keep these small. Do not make one 40-file “BioCatalyst rescue” PR.

### PR P0-A — `fix(biocatalyst): classify hydration failures instead of blaming the registry`

**Likely files:**

- `templates/biocatalyst.js`;
- paired client output if required;
- `tests/test_biocatalyst_page.py`;
- `tests/test_biocatalyst_d0b_ui.py` only for user-facing state wording.

**Changes:**

- typed transport error;
- content-type check;
- contract mismatch -> integrity state;
- no silent auth downgrade;
- no authority/source changes.

**Acceptance:** fixture tests prove 401 -> locked, 503 -> source/projection unavailable, 200+bad-contract -> integrity block, HTML response -> transport mismatch, valid zero -> empty.

### PR P0-B — `feat(biocatalyst-api): bounded failure codes and request correlation`

**Likely files:**

- `app/biocatalyst.py`;
- `tests/test_biocatalyst_api.py`;
- an assembled-app test if needed.

**Changes:** request ID + safe error code; preserve private headers and `site_full`.

**Acceptance:** anonymous remains 401; unentitled remains 403; invalid projection remains fail-closed 503; browser-visible reason carries no private path/receipt/hash.

### PR P0-C — `test(biocatalyst): entitled hydration verifier`

**Likely files:**

- new verifier;
- hermetic verifier tests;
- deployment/runbook note.

**Acceptance:** verifier fails when auth is stripped, payload schema mutates, one required endpoint becomes HTML, generation changes mid-run, dossier is missing, or console throws.

### PR P0-D — production proof receipt

No broad feature change. Run the verifier against production-equivalent deployment and attach:

- asset SHAs;
- production checkout;
- API checkout;
- generation ID;
- endpoint status/row counts;
- screenshots;
- sanitized network summary;
- pass/fail receipt.

Only after this may the project leave P0.

---

## F. Stop conditions that prevent another Codex rabbit hole

These should be pasted into the next session prompt verbatim.

