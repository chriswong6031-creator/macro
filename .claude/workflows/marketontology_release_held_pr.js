export const meta = {
  name: 'marketontology-release-held-pr',
  description: 'Meta-CEO Wave 0: take over Sol-held program PRs one at a time (takeover comment -> rebase -> opus review -> fix -> Ready + merge-on-green -> merge -> live proof)',
  whenToUse: 'args = {ceo:"A"|"B", prs:[6873, 6872], repo:"macro"|"terminal"}; PRs are processed SEQUENTIALLY in the given order (put base-healing / collision-winning PRs first)',
  phases: [
    { title: 'Takeover', detail: 'fresh-read the PR, post the Chairman-override takeover comment, rebase onto fresh base' },
    { title: 'Review', detail: 'opus reviewer attacks the rebased diff against fresh base' },
    { title: 'Fix', detail: 'builder repairs blockers/majors on the same branch, then one re-review' },
    { title: 'Ship', detail: 'strip the hold, Ready, merge-on-green, wait CONCLUDED checks, merge, live proof' },
  ],
}

// Charter: research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md §4 (takeover
// procedure) and §5 (Wave 0). Chairman override 2026-09-05 PDT relieved Sol; a
// HOLD-FOR-SOL is released by Meta-CEO review + concluded-green CI, not by Sol.

const CEO = (args && args.ceo) || 'A'
const PRS = (args && Array.isArray(args.prs)) ? args.prs : null
if (!PRS || PRS.length === 0) throw new Error('marketontology-release-held-pr: args.prs (non-empty array of PR numbers) is required')
const REPO_KEY = (args && args.repo) || 'macro'
const REPO = REPO_KEY === 'terminal' ? 'mastermindx-market-intelligence/mastermind-terminal' : 'mastermindx-market-intelligence/macro'
const BASE = REPO_KEY === 'terminal' ? 'master' : 'main'
const LOCAL = REPO_KEY === 'terminal' ? '/Users/chriswong/Documents/Cluade/charting-app' : '/Users/chriswong/Documents/Cluade/macro-main'

const S = (extra) => ({
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['COMPLETE', 'PARTIAL', 'BLOCKED'] },
    result: { type: 'string' },
    evidence: { type: 'object', properties: extra.props, required: extra.required },
    gaps: { type: 'array', items: { type: 'string' } },
    deviations: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'result', 'evidence', 'gaps', 'deviations'],
})
const TAKEOVER_SCHEMA = S({
  props: {
    pr_state: { type: 'string' }, head_before: { type: 'string' }, head_after: { type: 'string' },
    branch: { type: 'string' }, base_sha: { type: 'string' }, rebased: { type: 'boolean' },
    conflicts: { type: 'array', items: { type: 'string' } }, takeover_comment_url: { type: 'string' },
    hold_text_found: { type: 'string' }, files: { type: 'array', items: { type: 'string' } },
  },
  required: ['pr_state', 'head_before', 'head_after', 'branch', 'base_sha', 'rebased', 'conflicts', 'takeover_comment_url', 'hold_text_found', 'files'],
})
const REVIEW_SCHEMA = S({
  props: {
    verdict: { type: 'string', enum: ['PASS', 'FIX_REQUIRED', 'REJECT'] },
    blockers: { type: 'array', items: { type: 'string' } }, majors: { type: 'array', items: { type: 'string' } }, minors: { type: 'array', items: { type: 'string' } },
    checked_head: { type: 'string' }, checked_base: { type: 'string' },
  },
  required: ['verdict', 'blockers', 'majors', 'minors', 'checked_head', 'checked_base'],
})
const FIX_SCHEMA = S({
  props: { head_after: { type: 'string' }, tests_run: { type: 'string' }, files_changed: { type: 'array', items: { type: 'string' } } },
  required: ['head_after', 'tests_run', 'files_changed'],
})
const SHIP_SCHEMA = S({
  props: {
    merged: { type: 'boolean' }, merge_sha: { type: 'string' }, checks_summary: { type: 'string' },
    live_verified: { type: 'boolean' }, live_proof: { type: 'string' }, issue_comment_url: { type: 'string' },
  },
  required: ['merged', 'merge_sha', 'checks_summary', 'live_verified', 'live_proof', 'issue_comment_url'],
})
const RET = 'RETURN: call StructuredOutput with STATUS, RESULT, EVIDENCE, GAPS, DEVIATIONS exactly as the schema names them.'
const QUOTA = 'Quota law: preflight `gh api rate_limit --jq .resources.core.remaining` before any watch; ONE watcher per endpoint; `--interval 150` or slower; never `--paginate` check-runs; an empty/403 answer is not green.'

const takeoverPrompt = (n) => `ROUTE: build
MISSION: Take over held PR #${n} in ${REPO} for Meta-CEO ${CEO} under the Chairman override, and bring its branch onto fresh origin/${BASE}.
WHY: the PR was frozen by a Sol HOLD; Sol is relieved for this program (charter §0) and the Meta-CEO now owns it to merge + live proof.
SCOPE: fresh-read; takeover comment; rebase/merge-forward; push. No code changes beyond conflict resolution.
OUT OF SCOPE: reviewing the content (next stage); marking Ready; merging.
FROZEN SPEC: procedure below. OWNED FILES: only conflict resolutions. TESTS: run the test files touched by any conflict resolution.
PROCEDURE:
1. Work in a fresh sparse worktree of ${LOCAL}'s repo: cd "${LOCAL}" && git fetch origin ${BASE} && git worktree add --no-checkout "$TMPDIR/mo-release-${n}" origin/${BASE} 2>/dev/null || true; if that path already exists reuse it. In that worktree: git sparse-checkout init --cone && git sparse-checkout set $(git ls-tree --name-only origin/${BASE} | grep -v -E '^(data|site|mockups|verify_shots)$' | tr '\\n' ' ') && git checkout -q origin/${BASE}. (If sparse setup fails, fall back to python3 scripts/worktree_sparse.py auto from inside the worktree; never check out data/ or site/ unless the PR touches them, then add them explicitly.)
2. Fresh-read the PR: gh pr view ${n} -R ${REPO} --json state,isDraft,title,body,headRefName,headRefOid,baseRefName,labels,mergeable,mergeStateStatus,reviewDecision,comments,files. Record the HOLD text (title/body/comments grep -i 'HOLD'), the last comment time/author, the files list. If state is MERGED or CLOSED: return COMPLETE with pr_state and do nothing else.
3. Post ONE takeover comment: gh pr comment ${n} -R ${REPO} --body "Meta-CEO ${CEO} taking PR #${n} under the Chairman override of 2026-09-05 (charter research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md). The recorded HOLD-FOR-SOL is released to Meta-CEO review: opus review -> fixes -> Ready -> merge-on-green -> merge -> live proof. Prior owner session may stop; do not push to this branch after this comment." Record the comment URL.
4. Bring the branch current: git fetch origin <headRefName> && git checkout -B <headRefName> origin/<headRefName>; git rebase origin/${BASE} (preferred). On conflicts: resolve minimally in favor of keeping BOTH main's landed fixes and the PR's intent (read both sides; never drop a main-side change), run the touched tests, continue. If the rebase is unsafe (>15 conflicted files or generated artifacts), abort the rebase and instead git merge origin/${BASE} with the same resolution rule. Push: git push --force-with-lease origin <headRefName> (rebase) or git push (merge). Record head_before/head_after/base_sha.
5. ${QUOTA}
NOT DONE UNLESS: the takeover comment exists, the branch head is a descendant of fresh origin/${BASE} (git merge-base --is-ancestor origin/${BASE} HEAD), the push succeeded, and every conflict resolution is listed.
${RET}`

const reviewPrompt = (n, t) => `ROUTE: review
MISSION: Adversarially review PR #${n} (${REPO}) at head ${t.head_after} for release under the Chairman override.
ARTIFACT TO ATTACK: gh pr diff ${n} -R ${REPO} (after git fetch origin ${BASE}; base sha ${t.base_sha}); the PR body's claims and evidence; tests; the HOLD text ("${(t.hold_text_found || '').slice(0, 300)}") — decide whether the hold's release condition is a genuine defect that must be fixed before merge or Sol-era ceremony that no longer binds.
REVIEW STANDARD: correctness vs the PR's stated scope; no proprietary Market Ontology copying; lane do_not_redo from the lane's agentos handoff respected; nulls printed not hidden; no LLM-originated signals/scores; only the two nav families; for UI both theme treatments (dark/light) and EN/ZH present with evidence; tests exercise the change; no data/ or site/ truncation artifacts (a site/ or data/ file shrinking to a few KB in a sparse tree is a truncation, not an edit); no writes outside the PR's lane; annotations start the line; Supabase DDL only through reviewed migration files.
SCOPE: this PR only. Read-only: no edits, comments, labels, merges. Work from ${LOCAL} (git fetch is fine).
NOT DONE UNLESS: each blocker/major names file:line + the fix; PASS only with zero blockers and zero majors; the verdict states explicitly whether the HOLD condition is satisfied, obsolete, or still a blocker.
EVIDENCE REQUIRED: quoted hunks per finding.
${RET}`

const fixPrompt = (n, t, r) => `ROUTE: build
MISSION: Repair PR #${n} (${REPO}, branch ${t.branch}) so the reviewer's blockers and majors are resolved.
WHY: Wave 0 releases held work only when it is actually correct; the Meta-CEO's review replaces Sol's hold.
SCOPE: the findings below. OUT OF SCOPE: scope creep; merging; changing unrelated files.
FROZEN SPEC: the PR's own stated scope; findings:
BLOCKERS:${(r.blockers || []).map(b => `\n- ${b}`).join('') || ' none'}
MAJORS:${(r.majors || []).map(b => `\n- ${b}`).join('') || ' none'}
OWNED FILES: the PR's files plus tests. TESTS: re-run touched tests + any checker a finding names (python -m pytest <files> -q; never the full suite in a sparse tree).
PROCEDURE: reuse the worktree "$TMPDIR/mo-release-${n}" (git fetch origin ${t.branch} && git checkout -B ${t.branch} origin/${t.branch}); add site via python3 scripts/worktree_sparse.py add site if the PR touches site/templates; fix; test; commit with "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"; fresh-read gh pr view ${n} --json state,headRefOid before pushing; git push origin ${t.branch}. Append a "## Meta-CEO ${CEO} review fixes" section to the PR body (gh pr edit --body-file) listing each finding and its fix; never delete existing body text.
NOT DONE UNLESS: every blocker and major is fixed and pushed, or listed in GAPS with the reason.
${RET}`

const shipPrompt = (n, t) => `ROUTE: build
MISSION: Release PR #${n} (${REPO}, branch ${t.branch}) to MERGED and LIVE-VERIFIED and report on macro#6819.
WHY: DONE is merged + live (fleet law); the Chairman wants built work live, not parked.
SCOPE: title/label/Ready edits, waiting, merging, live verification, the wave comment. OUT OF SCOPE: code changes (a genuinely red check on this head -> return BLOCKED with job name + log excerpt).
FROZEN SPEC: n/a. OWNED FILES: none. TESTS: none.
PROCEDURE:
1. Fresh-read: gh pr view ${n} -R ${REPO} --json state,isDraft,title,headRefOid,labels,mergeable,mergeStateStatus,statusCheckRollup. If already MERGED, skip to step 5.
2. Strip the hold from the title (remove the leading "HOLD-FOR-SOL" / "[HOLD]" marker, keep the rest): gh pr edit ${n} -R ${REPO} --title "<clean title>". Append to the body a section "## Released under the Chairman override (Meta-CEO ${CEO}, 2026-09-06)" naming the review verdict and the charter path; never delete prior body text. If Draft: gh pr ready ${n} -R ${REPO}. Remove merge-blocked if present; add merge-on-green: gh pr edit ${n} -R ${REPO} --add-label merge-on-green.
3. ${QUOTA} Wait for CONCLUDED checks with ONE watcher: gh pr checks ${n} -R ${REPO} --watch --interval 150 (foreground; a macro ci.yml run takes 30-45 min; "Workers Builds: macro" red is known-spurious and ignorable; a pending check is not a pass). If the head has no fresh run 5 minutes after the push, read the PR's checks once more before assuming; do not dispatch workflows.
4. Fresh-read again (state, headRefOid, mergeStateStatus). If the sweeper already merged: record the sha. Else on concluded green (spurious Workers X excluded): gh pr merge ${n} -R ${REPO} --squash --delete-branch. On a merge conflict: return BLOCKED naming the paths. Never --admin past a real red; never close/reopen; never rename the branch.
5. Live verification (${REPO_KEY}): ${REPO_KEY === 'terminal'
    ? 'merge to master runs /opt/terminal/terminal-build.sh; poll https://app.mastermind-x.com every 120s up to 20 min (curl -sI, then curl -s a route the diff changed) until a marker from the diff is served; record status + marker.'
    : 'the VPS pulls main every 3 min; paired plain-copy assets are live after that. Template/engine changes need the shared render lane: gh run list -R mastermindx-market-intelligence/macro --workflow render.yml --branch main --limit 3 --json databaseId,status,conclusion,headSha,createdAt; watch the run whose head is at/after the merge sha with gh run watch <id> --interval 120 (never cancel/re-run); then curl -s the live page(s) the PR adds/changes and grep a marker from the diff; curl -sI for status. If the PR adds a page that must be reachable, curl the nav entry page and grep the link.'}
6. Post ONE comment on issue macro#6819: gh issue comment 6819 -R mastermindx-market-intelligence/macro --body "[Meta-CEO ${CEO}] Wave 0: PR #${n} merged as <sha>; live proof: <url> <status> <marker>; released under the Chairman override (charter research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md)." Record its URL.
NOT DONE UNLESS: merged is true with the exact sha and live_verified is true with URL + status + marker (records-only PRs: say "no live surface" and set live_verified true with the merge readback as proof), and the #6819 comment exists.
${RET}`

const out = []
for (const n of PRS) {
  log(`PR #${n}: takeover`)
  const t = await agent(takeoverPrompt(n), { label: `takeover:${n}`, phase: 'Takeover', schema: TAKEOVER_SCHEMA, agentType: 'builder', effort: 'medium' })
  if (!t || t.status === 'BLOCKED' || /MERGED|CLOSED/i.test(t.evidence.pr_state)) {
    log(`PR #${n}: stop after takeover (${t ? t.evidence.pr_state + ' / ' + t.status : 'null'})`)
    out.push({ pr: n, stage: 'takeover', takeover: t && t.evidence, result: t && t.result })
    continue
  }
  const te = t.evidence
  log(`PR #${n}: review at ${te.head_after}`)
  let review = await agent(reviewPrompt(n, te), { label: `review:${n}`, phase: 'Review', schema: REVIEW_SCHEMA, agentType: 'reviewer', effort: 'high' })
  let fix = null
  if (review && review.evidence.verdict === 'FIX_REQUIRED') {
    log(`PR #${n}: fix (${review.evidence.blockers.length} blockers, ${review.evidence.majors.length} majors)`)
    fix = await agent(fixPrompt(n, te, review.evidence), { label: `fix:${n}`, phase: 'Fix', schema: FIX_SCHEMA, agentType: 'builder', effort: 'medium' })
    const te2 = { ...te, head_after: (fix && fix.evidence && fix.evidence.head_after) || te.head_after }
    review = await agent(reviewPrompt(n, te2), { label: `rereview:${n}`, phase: 'Fix', schema: REVIEW_SCHEMA, agentType: 'reviewer', effort: 'high' })
  }
  if (!review || review.evidence.verdict !== 'PASS') {
    log(`PR #${n}: NOT released (verdict ${review ? review.evidence.verdict : 'null'})`)
    out.push({ pr: n, stage: 'review', takeover: te, review: review && review.evidence, fix: fix && fix.evidence })
    continue
  }
  log(`PR #${n}: ship`)
  const ship = await agent(shipPrompt(n, te), { label: `ship:${n}`, phase: 'Ship', schema: SHIP_SCHEMA, agentType: 'builder', effort: 'low' })
  out.push({ pr: n, stage: 'ship', takeover: te, review: review.evidence, fix: fix && fix.evidence, ship: ship && ship.evidence, ship_status: ship && ship.status })
}
const merged = out.filter(o => o.ship && o.ship.merged).map(o => o.pr)
log(`Wave 0 (${CEO}): merged ${merged.length}/${PRS.length} -> ${merged.join(', ') || 'none'}`)
return { ceo: CEO, prs: PRS, merged, details: out }
