# Mastermind-X Linear PR linkage and semantic-completion amendment

**Status:** operating amendment · 2026-08-20
**Authority:** Sol CEO portfolio-projection adjudication
**Parent contract:** `research/MASTERMIND_LINEAR_PORTFOLIO_PROJECTION_CONTRACT_2026-08-20.md`
**Linear rollout/configuration gate:** `MAS-67`
**Scope:** native Linear↔GitHub relationship mechanics only; records, not runtime

## 0. Why this amendment exists

The parent portfolio contract correctly froze two principles:

1. Linear is a selective projection, never canonical work/lifecycle truth.
2. Merge is not automatically completion.

Live use exposed a lower-level mechanical hole in the original branch/PR join guidance.
Linear natively treats issue identifiers in Git branch names as relationship inputs. When a
PR is auto-linked to an issue, the team's configured PR workflow can move that issue as the
PR opens, enters review, or merges. Therefore a neutral-looking convention such as
`<seat>/mas-123-<slug>` is **not neutral metadata** when the PR is architecture, research,
source law, evidence, or another contributing artifact whose merge does not satisfy the
referenced issue's acceptance condition.

Two live regressions proved the failure mode:

- **MAS-48 / Mastermind #91:** records-only Slack-ingress architecture merged; Linear
  transiently projected the still-unimplemented/still-unproven program as `Done`.
- **MAS-75 / Mastermind #96:** records-only PR-A implementation law merged with zero runtime
  code; Linear moved the actual implementation issue to `Done` until Sol repaired it to
  `Todo`.

The issue is not that Linear is unsuitable. The issue is that GitHub relationship semantics
must encode **what the PR means**, not only which issue it mentions.

## 1. Native Linear facts that are load-bearing

Primary source: `https://linear.app/docs/github` as reviewed on 2026-08-20.

Current native behavior relevant to Mastermind-X:

- A Linear issue identifier in a Git branch name can auto-link the resulting PR to that issue.
- Team GitHub workflow automation can project linked PR lifecycle into Linear status,
  including merge-time completion when configured.
- Linear distinguishes relationship vocabulary:
  - closing relationships use words such as `close`, `fix`, `resolve`, `complete`, or
    `implement` and are eligible for the team's merge-completion transition;
  - non-closing relationships use `ref`, `refs`, `references`, `part of`,
    `contributes to`, `toward`, or `towards`; they may retain earlier PR lifecycle
    projection but do not apply the merge-status transition;
  - relation relationships use `relates to` or `related to`; they create issue relation
    context without status changes.
- Manually unlinking a PR is not a durable repair when its branch name still contains the
  issue identifier; later pushes or merge can re-link it.
- Linear documents `skip <ISSUE>` or `ignore <ISSUE>` in the PR description to suppress
  branch-name auto-linking for an issue that must not be controlled by that PR.

These are native application behaviors, not Mastermind runtime state. Mastermind-X should
use them rather than building another PR-status database.

## 2. Semantic-completion invariant

```text
GitHub merge = exact implementation/evidence fact
Linear Done   = this Linear object's acceptance condition is complete
```

Those facts may coincide. They are not synonyms.

A PR may drive a Linear issue to `Done` **only** when both are true:

1. the GitHub↔Linear relationship is intentionally completion-bearing; and
2. the merged PR itself satisfies that Linear issue's explicit acceptance/stop condition.

A branch identifier, PR title mention, attachment, or records-only architecture merge never
substitutes for condition 2.

## 3. Four PR relationship classes

### 3.1 Merge-is-done implementation PR

Use when the PR itself completes the bounded Linear deliverable.

Preferred mechanics:

- use the Linear implementation issue's generated branch/identifier;
- PR metadata says `Completion: merge-is-done`;
- a native closing relationship is permitted;
- merge may transition that **implementation issue** to `Done` after required review/CI.

Do not use this class for a program, production-proof gate, CEO/operator gate, architecture
freeze, or source-law record merely because the PR is important.

### 3.2 Contributing PR where pre-merge progress projection is useful

Use when the PR contributes to a larger delivery object but its merge is not that object's
completion.

Preferred mechanics:

- give the PR's own independently complete deliverable its own Linear issue when warranted;
- link the larger delivery issue with a **non-closing** relationship (`references`,
  `contributes to`, etc.);
- the larger issue may reflect useful open/review progress under configured Linear workflow,
  but merge does not apply its completion transition.

### 3.3 Architecture / source-law / research / evidence PR

Use when the PR should be visible from a delivery/program issue but should not mutate its
status at all.

Preferred mechanics:

- branch name uses the architecture/evidence issue's own identifier, or no Linear identifier
  when the records amendment is tracked only as relation evidence;
- reference the delivery/program issue using **relation-only** wording (`Relates to MAS-123`);
- do not use a closing relationship to the delivery/program issue;
- do not reuse that delivery issue's generated branch merely for convenient traceability.

This amendment itself follows that pattern: branch
`chatgpt1/linear-pr-linkage-completion-law` deliberately contains no `MAS-67` identifier.
Its future PR may say `Relates to MAS-67`; merging these records must not complete MAS-67,
whose operator/admin configuration and canary proof remain owed.

### 3.4 Gate/program object that no one PR should close

Production proof, operator action, CEO acceptance, and multi-wave program issues normally
remain open across several PRs.

- implementation PRs close their own merge-complete implementation children;
- parent/gate issues receive relation or non-closing context;
- the gate/program reaches `Done` only when its canonical acceptance evidence exists.

MAS-48 is the reference example: PR-A, PR-B, and PR-C may each produce implementation
artifacts, but MAS-48 itself closes only after its real Pro-Sol→Slack→Executive→ACK→MCP
production canary succeeds.

## 4. Existing branch already contains the wrong issue ID

Do not assume manual unlinking is durable.

When a PR must **not** control an issue but its branch already contains that issue ID:

1. add Linear's documented `ignore MAS-123` or `skip MAS-123` suppression to the PR
   description for that issue;
2. use the correct non-closing/relation relationship to any issue that should remain visible;
3. push again and verify the unwanted auto-link does not reappear;
4. verify merge does not transition the suppressed issue;
5. record the result in MAS-67's native-integration acceptance receipt.

Do not rename/rewrite history solely to make Linear green when suppression can safely express
the intended relationship.

## 5. Updated branch and PR join contract

The parent contract's generic preferred branch shape is narrowed as follows.

### Completion-bearing implementation object

```text
<seat-or-worker>/mas-123-<short-slug>
```

is preferred **only when MAS-123 is the actual merge-complete implementation object**.

### Non-completion-bearing records/evidence work

Do not embed the delivery/program issue ID in the branch merely as a join key. Use either:

- the records/evidence work's own Linear issue ID; or
- a descriptive branch without a Linear issue ID, then native relation-only linkage.

PR metadata remains useful:

```text
Workstream: WS:<KEY>
Linear: <owning deliverable or none>
Relates to: MAS-123
Wave: <wave-id|maintenance|records>
Authority: <build|research|records|repair>
Completion: <merge-is-done|BUILT_NOT_PROVEN|needs-sol|needs-operator|records-only>
```

But custom `Completion:` text is documentation, not a substitute for native relationship
semantics. The native link itself must match that stated meaning.

## 6. Projector / validator behavior

The future one-way projector and report-only linkage validator must distinguish at least:

- completion-bearing implementation relationship;
- non-closing contribution;
- relation-only evidence/context;
- branch-ID auto-link that conflicts with declared completion semantics;
- explicitly suppressed auto-link (`skip` / `ignore`).

A useful report-only discrepancy is:

`portfolio_linkage_completion_mismatch`

Emit it when a PR declares `records-only`, `BUILT_NOT_PROVEN`, `needs-sol`, or
`needs-operator` but its native GitHub↔Linear relationship can still drive the referenced
issue to `Done` on merge.

The repair should name the smallest native correction: own implementation issue, non-closing
relationship, relation-only relationship, or skip/ignore suppression. Do not auto-edit PR
relationship semantics until report-only false-positive behavior is measured under MAS-67.

## 7. Linear state correction law

If native automation produces a false status:

1. read the canonical acceptance/Agent OS/GitHub evidence;
2. repair Linear to the truthful lifecycle state;
3. record the discrepancy on the owning Linear integration/config issue when systemic;
4. do **not** rewrite canonical Agent OS or production proof to agree with the dashboard.

A transient false `Done` is a projection defect, not evidence the feature completed.

## 8. MAS-67 acceptance extension

MAS-67 must demonstrate four harmless native flows:

1. **closing implementation** — open/review lifecycle works and merge completes the intended
   merge-is-done child;
2. **non-closing contribution** — desired pre-merge lifecycle may project, but merge does
   not complete the larger delivery issue;
3. **relation-only architecture/evidence** — linkage is visible and causes zero status changes;
4. **branch auto-link suppression** — a branch containing an issue ID plus documented
   `skip/ignore` does not re-link or change that issue on a later push or merge.

Historical regression fixtures:

- MAS-48 / Mastermind #91;
- MAS-75 / Mastermind #96.

MAS-67 remains `Todo` until the native workspace/team configuration and these canaries are
actually proven. Merging this records amendment does not complete MAS-67.

## 9. No-rebuild boundary

This amendment authorizes no new:

- Linear lifecycle database;
- GitHub webhook service;
- duplicate PR registry;
- Agent OS task store;
- merge controller;
- Executive OS mutation;
- Slack runtime behavior.

Use native Linear↔GitHub relationship semantics plus the existing one-way projector/linkage
validator program. The product rule is semantic completion; native Linear is the projection
mechanism.
