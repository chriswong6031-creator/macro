export const meta = {
  name: 'marketontology-vertical-build',
  description: 'Market Ontology Meta-CEO build lane: spec -> build -> review -> fix -> ship -> live proof for one wave batch of ledger packets',
  whenToUse: 'One Meta-CEO half runs one wave batch (<=6 packets). args = {ceo:"A"|"B", wave:"A1", packets:[{id, lane, title, repo, kind, ledger_rows, spec_sources, owned_paths, entry_points, acceptance, live_url}]}',
  phases: [
    { title: 'Spec', detail: 'designer (ui) or analyst (engine/data/records) freezes the packet into an implementable spec' },
    { title: 'Build', detail: 'builder implements in an isolated sparse worktree, tests, pushes, opens the PR, arms merge-on-green' },
    { title: 'Review', detail: 'opus reviewer attacks the diff against fresh origin/main' },
    { title: 'Fix', detail: 'builder repairs blockers/majors on the same branch' },
    { title: 'Ship', detail: 'wait for CONCLUDED checks, squash-merge, live-verify, return proof' },
  ],
}

// ---------------------------------------------------------------------------
// Charter: research/MARKET_ONTOLOGY_META_CEO_CHARTER_2026_09_06.md (Chairman
// override 2026-09-05 PDT). Meta-CEOs adjudicate; workers build. Every stage is
// routed per CLAUDE.md §Model routing (builder=sonnet, reviewer/designer/analyst=opus).
// No fable stage exists in this script on purpose.
// ---------------------------------------------------------------------------

const CEO = (args && args.ceo) || 'A'
const WAVE = String((args && args.wave) || '1')
const PACKETS = (args && Array.isArray(args.packets)) ? args.packets : null
if (!PACKETS || PACKETS.length === 0) {
  throw new Error('marketontology-vertical-build: args.packets (non-empty array) is required; see charter §6 for the packet shape')
}
if (PACKETS.length > 8) {
  throw new Error(`marketontology-vertical-build: ${PACKETS.length} packets; keep a wave batch at <=8 (charter §5 says <=6)`)
}

const MACRO_REPO = 'mastermindx-market-intelligence/macro'
const TERMINAL_REPO = 'mastermindx-market-intelligence/mastermind-terminal'
const MACRO_LOCAL = '/Users/chriswong/Documents/Cluade/macro-main'
const TERMINAL_LOCAL = '/Users/chriswong/Documents/Cluade/charting-app'

const repoOf = (p) => (p.repo === 'terminal' ? TERMINAL_REPO : MACRO_REPO)
const localOf = (p) => (p.repo === 'terminal' ? TERMINAL_LOCAL : MACRO_LOCAL)
const defaultBranchOf = (p) => (p.repo === 'terminal' ? 'master' : 'main')
const branchOf = (p) => `claude/mo-${CEO.toLowerCase()}-${WAVE.toLowerCase()}-${String(p.id).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`

const PACKET_BLOCK = (p) => `PACKET ${p.id} (lane ${p.lane}, wave ${WAVE}, Meta-CEO ${CEO})
Title: ${p.title}
Repo: ${p.repo} (${repoOf(p)}; default branch ${defaultBranchOf(p)}); branch for this packet: ${branchOf(p)}
Kind: ${p.kind}
Ledger rows to close: ${(p.ledger_rows || []).join(', ') || 'none named'}
Spec sources (read these first): ${(p.spec_sources || []).join(' | ') || 'none named'}
Owned paths (only these may change; anything else is a DEVIATION to report): ${(p.owned_paths || []).join(', ') || 'to be proposed in the spec'}
Entry points (must be reachable from the existing nav family / product route): ${(p.entry_points || []).join(', ') || 'none named'}
Expected live URL after merge: ${p.live_url || 'to be named in the spec'}
Acceptance (NOT DONE UNLESS every line holds): ${(p.acceptance || []).map((a, i) => `\n  ${i + 1}. ${a}`).join('') || '\n  (charter §6 gates apply)'}
Standing gates (charter §6/§7): FRONT-END CLARITY LAW (Chairman, 2026-09-06; supersedes nothing in the design doctrine, sharpens it): every user-facing surface must be clear and user-friendly for a fintech SaaS customer — plain words, one-line stance per module (what it means and what to do, even if that is watch, do not chase), technicals and internal names demoted to hover/details, no machine text (no raw slugs, internal state names, untranslated stat names, timestamps without meaning), no walls of text, honest nulls in plain words ("Not available yet" + why), bilingual EN/ZH. Reviewers REJECT a surface a non-quant customer could not read in 10 seconds. Also: fresh end-to-end happy path with zero manual workarounds; nulls printed not hidden; no LLM-originated signals/scores/escalations; no trading authority; no proprietary Market Ontology code/text/data/assets copied; each lane handoff's do_not_redo binds; only the two existing nav families (no third header); K1 EvidenceRef/EvidenceBlock/EvidenceRecipe for evidence; corrections are typed states; identity only via Stock Identity + Data OS + Supabase auth.`

const BUDGET = (n, note) => `HARD BUDGET: workflow subagents are cut off at exactly 30 tool calls with NO return (measured 2026-09-06). You have at most ${n} tool calls including the final StructuredOutput. Plan them first; batch shell work into single Bash calls (one heredoc script beats five commands); write long outputs to a file ONCE and read them with sed -n ranges; append progress notes to $TMPDIR/mo-progress-<packet>.md after every 4 calls. At call ${n - 2} STOP and return — PARTIAL with exact remaining_steps is acceptable, silence is not. ${note || ''}`

const SPEC_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['COMPLETE', 'PARTIAL', 'BLOCKED'] },
    result: { type: 'string', description: 'Two-sentence summary of the frozen spec' },
    evidence: {
      type: 'object',
      properties: {
        spec_markdown: { type: 'string', description: 'The full frozen spec: files to touch, exact markup/CSS or data contract, tests to add, entry-point wiring, live URL, dark+light treatment for UI' },
        owned_paths: { type: 'array', items: { type: 'string' } },
        sources_read: { type: 'array', items: { type: 'string' } },
      },
      required: ['spec_markdown', 'owned_paths', 'sources_read'],
    },
    gaps: { type: 'array', items: { type: 'string' } },
    deviations: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'result', 'evidence', 'gaps', 'deviations'],
}

const BUILD_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['COMPLETE', 'PARTIAL', 'BLOCKED'] },
    result: { type: 'string' },
    evidence: {
      type: 'object',
      properties: {
        pr_number: { type: 'integer' },
        pr_url: { type: 'string' },
        branch: { type: 'string' },
        head_sha: { type: 'string' },
        tests_run: { type: 'string', description: 'exact command(s) and pass/fail counts' },
        files_changed: { type: 'array', items: { type: 'string' } },
        remaining_steps: { type: 'array', items: { type: 'string' }, description: 'Empty when COMPLETE; when PARTIAL, the exact steps a continuation builder must do next' },
      },
      required: ['pr_number', 'pr_url', 'branch', 'head_sha', 'tests_run', 'files_changed', 'remaining_steps'],
    },
    gaps: { type: 'array', items: { type: 'string' } },
    deviations: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'result', 'evidence', 'gaps', 'deviations'],
}

const REVIEW_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['COMPLETE', 'PARTIAL', 'BLOCKED'] },
    result: { type: 'string' },
    evidence: {
      type: 'object',
      properties: {
        verdict: { type: 'string', enum: ['PASS', 'FIX_REQUIRED', 'REJECT'] },
        blockers: { type: 'array', items: { type: 'string' } },
        majors: { type: 'array', items: { type: 'string' } },
        minors: { type: 'array', items: { type: 'string' } },
        checked_against_main: { type: 'string', description: 'origin/main (or master) sha the diff was compared to' },
      },
      required: ['verdict', 'blockers', 'majors', 'minors', 'checked_against_main'],
    },
    gaps: { type: 'array', items: { type: 'string' } },
    deviations: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'result', 'evidence', 'gaps', 'deviations'],
}

const SHIP_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['COMPLETE', 'PARTIAL', 'BLOCKED'] },
    result: { type: 'string' },
    evidence: {
      type: 'object',
      properties: {
        merged: { type: 'boolean' },
        merge_sha: { type: 'string' },
        checks_summary: { type: 'string' },
        live_verified: { type: 'boolean' },
        live_proof: { type: 'string', description: 'URL + HTTP status + readback line or screenshot path; render/deploy run id' },
      },
      required: ['merged', 'merge_sha', 'checks_summary', 'live_verified', 'live_proof'],
    },
    gaps: { type: 'array', items: { type: 'string' } },
    deviations: { type: 'array', items: { type: 'string' } },
  },
  required: ['status', 'result', 'evidence', 'gaps', 'deviations'],
}

const RETURN_LINE = 'RETURN: call StructuredOutput with STATUS, RESULT, EVIDENCE, GAPS, DEVIATIONS exactly as the schema names them.'

// ---------------------------------------------------------------------------
// Stage prompts
// ---------------------------------------------------------------------------
// A packet may carry a pre-frozen spec on disk (written by a sub-orchestrator); the
// spec stage then only copies it verbatim instead of re-designing (extractor, low effort).
const frozenSpecPrompt = (p) => `ROUTE: extract
MISSION: Return the pre-frozen spec for packet ${p.id} verbatim as the StructuredOutput.
SCOPE: Read the file ${p.spec_path} in full (use the Read tool with offset/limit until the whole file is covered; it may be 400-1400 lines). Put its complete, unmodified markdown into evidence.spec_markdown. Fill evidence.owned_paths with every repository path the spec names as a file the builder touches (its "files the builder touches" / OWNED FILES / files-to-touch section), evidence.sources_read with [${JSON.stringify(p.spec_path)}], status "COMPLETE", result with the spec's own one-line summary, gaps and deviations as empty arrays. Do not summarize, reorder, or edit the spec.
NOT DONE UNLESS: evidence.spec_markdown is the byte-for-byte file content and owned_paths is non-empty.
RETURN: the StructuredOutput call only.`

const specPrompt = (p) => {
  const ui = p.kind === 'ui'
  return `ROUTE: ${ui ? 'design' : 'analysis'}
MISSION: Freeze packet ${p.id} into an implementable spec a Sonnet builder can execute without redesigning anything.
${BUDGET(20, '')}
${ui ? 'USER JOB' : 'DECISION SUPPORTED'}: ${p.title} — the user must be able to reach it from ${(p.entry_points || []).join(', ') || 'the existing nav family'} and get a true answer, with nulls disclosed in plain words.
SCOPE: read the spec sources and the current owner code/templates; decide files, exact ${ui ? 'markup + CSS (tokens from theme.css only; dark = command center, light = research workspace; both named)' : 'data contract, function signatures, and receipts'}; name the tests; name the live URL.
OUT OF SCOPE: writing product code; touching git; anything outside the packet's lane.
${ui ? 'FROZEN CONSTRAINTS: docs/DESIGN_DOCTRINE.md + research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md (archetype per route, canonical components in mockups/design_system/specimen.html, density budgets); CLAUDE.md §Navigation (two nav families only); §Theme art direction (DARK TREATMENT, LIGHT TREATMENT, evidence matrix dark/light x EN/ZH x 1440/390); bilingual EN/ZH; glance tier plain words, technicals demoted.\nREFERENCES: the spec sources below plus the nearest existing page in the same nav family.\nOWNED FILES: propose the exact list (templates/*.j2, site pairs, engine/*, tests/*).\nVISUAL VERIFICATION: state which crops the builder must produce.' : 'ASSUMPTIONS: state every assumption about data availability; if a required source does not exist, the spec says so and scopes the packet to what exists (a null is printed, never fabricated).'}
${PACKET_BLOCK(p)}
Work in the checkout at ${localOf(p)} (read-only for you): fetch nothing, edit nothing. Use grep/sed with capped output; never cat files longer than 300 lines whole.
NOT DONE UNLESS: the spec names every file to touch, the exact contract/markup, the tests, the entry-point wiring, the live URL, and (for UI) both theme treatments; every claim about existing code cites file:line.
EVIDENCE REQUIRED: file:line citations for every existing owner you build on.
${RETURN_LINE}`
}

const buildPrompt = (p, spec) => `ROUTE: build
MISSION: Implement packet ${p.id} exactly as specified, ship it as a PR, and arm merge-on-green.
${BUDGET(26, 'If the packet cannot finish inside the budget: commit + push what exists as WIP on the branch, open the PR as Draft if not yet open, and return PARTIAL with remaining_steps — a continuation builder resumes on the same branch.')}
WHY: Market Ontology ledger rows ${(p.ledger_rows || []).join(', ') || '(see packet)'} close only when this is merged and live.
SCOPE: the frozen spec below; tests; PR body with acceptance evidence.
OUT OF SCOPE: redesigning the spec; touching files outside OWNED FILES (report as DEVIATION instead); merging (the ship stage merges); editing the F00C ledger CSV.
FROZEN SPEC:
${spec}
OWNED FILES: ${(p.owned_paths || []).join(', ') || 'the spec\'s file list'}
TESTS: add/extend pytest (macro) or the repo's test runner (terminal) for every new behavior; run the touched test files and the relevant checkers.
${PACKET_BLOCK(p)}
PROCEDURE (fleet law, CLAUDE.md):
1. You are in an isolated sparse worktree. Run: git fetch origin ${defaultBranchOf(p)} && git checkout -B ${branchOf(p)} origin/${defaultBranchOf(p)}. If the packet touches site/ or templates/ or a paired plain-copy asset in macro, run: python3 scripts/worktree_sparse.py add site (then data if needed).
2. Implement. For macro template edits that have paired site copies run: python -m scripts.check_template_site_sync --fix. For UI: python3 scripts/check_design_system.py --mode enforce-added, python3 scripts/check_runtime_style_injection.py, python3 scripts/check_ui_visual_evidence.py (read their usage first); produce the evidence crops (dark/light x EN/ZH x 1440/390) with headless Chrome into a scratch dir and reference them in the PR body. Bilingual EN/ZH; no translated text in title= attributes; GitHub annotations start the line.
3. Run the touched tests: python -m pytest <files> -q (macro) — never the full suite in a sparse tree.
4. Commit (message ends with "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"), push -u origin ${branchOf(p)}, then: gh pr create -R ${repoOf(p)} --base ${defaultBranchOf(p)} --title "[MO-${CEO}${WAVE}] ${p.id}: ${p.title}" --body-file <file> (body: what/why, ledger rows, acceptance evidence per gate, crops, tests, live URL, and the line "Generated with Claude Code"), then gh pr edit <n> --add-label merge-on-green.
5. Preflight gh quota before any watch (gh api rate_limit --jq .resources.core.remaining); never gh run watch under --interval 60; never --paginate check-runs.
NOT DONE UNLESS: PR exists as Draft, tests pass locally, the PR body carries the acceptance evidence, and every acceptance line is addressed or listed in GAPS. It must NOT be armed with merge-on-green yet.
${RETURN_LINE}`

const reviewPrompt = (p, build) => `ROUTE: review
MISSION: Adversarially review PR #${build.pr_number} (${build.pr_url}) for packet ${p.id} before it merges.
${BUDGET(22, 'Write the diff to a file once; at most 6 range reads.')}
ARTIFACT TO ATTACK: the PR diff vs fresh origin/${defaultBranchOf(p)} (gh pr diff ${build.pr_number} -R ${repoOf(p)}; git fetch origin ${defaultBranchOf(p)} first and note its sha), the PR body's evidence, the tests.
REVIEW STANDARD: the FRONT-END CLARITY LAW above is a blocker-level standard for any UI change; correctness against the frozen spec and acceptance lines; nulls printed not hidden; no LLM-originated signals/scores; no proprietary copying; lane do_not_redo respected; both nav families untouched unless owned; for UI both theme treatments judged as designs (hierarchy, material, semantic color, EN/ZH parity) with the evidence matrix present; tests actually exercise the new behavior; no writes outside OWNED FILES; no data/ or site/ truncation artifacts from a sparse tree; annotations start the line.
SCOPE: this PR only. Read-only: do not edit, comment, label, or merge.
${PACKET_BLOCK(p)}
NOT DONE UNLESS: every blocker names file:line and the failing acceptance line; verdict is PASS only when zero blockers and zero majors remain.
EVIDENCE REQUIRED: quoted diff hunks for each finding.
${RETURN_LINE}`

const fixPrompt = (p, build, review) => `ROUTE: build
MISSION: Repair PR #${build.pr_number} (${build.pr_url}) on branch ${branchOf(p)} so every blocker and major from the review is resolved.
${BUDGET(24, 'If the fixes cannot fit, commit + push what is done and list the rest in GAPS.')}
WHY: the packet cannot ship with the reviewer's findings open.
SCOPE: the findings below; keep the frozen spec intact.
OUT OF SCOPE: new features; files outside OWNED FILES; merging.
FROZEN SPEC: unchanged (see PR body); findings to fix:
BLOCKERS:${(review.blockers || []).map(b => `\n- ${b}`).join('') || ' none'}
MAJORS:${(review.majors || []).map(b => `\n- ${b}`).join('') || ' none'}
OWNED FILES: ${(p.owned_paths || []).join(', ') || 'the PR\'s file list'}
TESTS: re-run the touched tests and any checker the finding names.
${PACKET_BLOCK(p)}
PROCEDURE: you are in an isolated sparse worktree: git fetch origin ${branchOf(p)} && git checkout -B ${branchOf(p)} origin/${branchOf(p)} (add site via python3 scripts/worktree_sparse.py add site if the PR touches site/templates). Fix, test, commit (Co-Authored-By line), push. Do not edit the PR body except to append a "Review fixes" section. Fresh-read the PR state before pushing (gh pr view ${build.pr_number} -R ${repoOf(p)} --json state,headRefOid,labels).
NOT DONE UNLESS: every blocker and major is fixed and pushed, or explicitly listed in GAPS with the reason.
${RETURN_LINE}`

const shipPrompt = (p, build) => `ROUTE: build
MISSION: Take PR #${build.pr_number} (${build.pr_url}) to MERGED and LIVE-VERIFIED, returning proof.
${BUDGET(20, 'Checking checks is a bounded poll loop (see step 2), not a single long watch call.')}
WHY: DONE for a packet is merged + live (fleet law); an open PR is abandoned work.
SCOPE: waiting on checks, merging, live verification, proof.
OUT OF SCOPE: code changes (if a check is genuinely red on this head, return BLOCKED with the failing job name and log excerpt so the Meta-CEO can commission a fix).
FROZEN SPEC: n/a. OWNED FILES: none. TESTS: none to write.
${PACKET_BLOCK(p)}
PROCEDURE:
1. Preflight: gh api rate_limit --jq .resources.core.remaining (stop and return BLOCKED if < 300). This stage runs only after review verdict PASS: mark the PR Ready (gh pr ready ${build.pr_number} -R ${repoOf(p)} if it is still Draft) and arm the sweeper now: gh pr edit ${build.pr_number} -R ${repoOf(p)} --add-label merge-on-green.
2. A Bash call is capped at 10 minutes, so \`gh pr checks --watch\` on a 30-45 min macro ci.yml run will be killed before it concludes: do NOT use a single foreground watch. Instead poll in bounded rounds, each its own Bash call (each \`sleep\` >=90s to satisfy quota law): \`for i in $(seq 1 3); do gh pr checks ${build.pr_number} -R ${repoOf(p)} --json name,state,conclusion --jq '.[] | [.name,.state,.conclusion] | @tsv'; sleep 170; done\`. Repeat across multiple such calls until every check has CONCLUDED ("Workers Builds: macro" red is known-spurious and ignorable; PENDING/QUEUED is not a pass). If checks are still pending when this stage's budget wall is reached, return PARTIAL naming the armed merge-on-green sweeper as the eventual merge performer and live verification as still owed.
3. Fresh-read state: gh pr view ${build.pr_number} -R ${repoOf(p)} --json state,mergedAt,mergeCommit,headRefOid,labels,isDraft,reviewDecision. If the merge-on-green sweeper already merged it, record the sha. Otherwise, on all-concluded-green: gh pr merge ${build.pr_number} -R ${repoOf(p)} --squash --delete-branch. If merge-blocked by a conflict: return BLOCKED naming the conflicting paths.
4. Live verification (${p.repo}): ${p.repo === 'terminal'
    ? 'merge to master triggers /opt/terminal/terminal-build.sh; poll https://app.mastermind-x.com (curl -sI, then curl -s the packet route) every 120s up to 20 min until the new build serves the change (a markup/text marker from the diff); record HTTP status and the matched marker.'
    : 'a template/engine change needs the shared render lane: gh run list -R mastermindx-market-intelligence/macro --workflow render.yml --branch main --limit 3 --json databaseId,status,conclusion,headSha,createdAt; watch the run whose head is at/after the merge sha with gh run watch <id> --interval 120 (never cancel or re-run it). The VPS pulls main every 3 min. Then curl -s the live URL and grep a marker from the diff; also curl -sI for the HTTP status. Paired plain-copy assets are live after the VPS pull without a render.'}
5. Never dispatch or cancel production workflows; never close/reopen the PR; never rename the branch.
NOT DONE UNLESS: merged is true with the exact merge sha, and live_verified is true with a URL + status + marker (or the packet is records-only and no live surface exists: say so).
${RETURN_LINE}`

// ---------------------------------------------------------------------------
// Pipeline: each packet flows independently through the stages.
// ---------------------------------------------------------------------------
log(`Meta-CEO ${CEO} wave ${WAVE}: ${PACKETS.length} packet(s) -> ${PACKETS.map(p => p.id).join(', ')}`)

const results = await pipeline(
  PACKETS,
  // 1. Spec
  (p) => (p.spec_path
    ? agent(frozenSpecPrompt(p), { label: `spec(frozen):${p.id}`, phase: 'Spec', schema: SPEC_SCHEMA, effort: 'low', agentType: 'extractor' })
    : agent(specPrompt(p), {
        label: `spec:${p.id}`, phase: 'Spec', schema: SPEC_SCHEMA, effort: 'high',
        agentType: p.kind === 'ui' ? 'designer' : 'analyst',
      })
  ).then(s => ({ p, spec: s })),
  // 2. Build
  async ({ p, spec }) => {
    if (!spec || spec.status === 'BLOCKED') { log(`${p.id}: spec BLOCKED — ${spec ? spec.result : 'null'}`); return { p, spec, build: null } }
    const specText = spec.evidence.spec_markdown
    const pp = { ...p, owned_paths: (p.owned_paths && p.owned_paths.length) ? p.owned_paths : spec.evidence.owned_paths }
    let build = await agent(buildPrompt(pp, specText), {
      label: `build:${p.id}`, phase: 'Build', schema: BUILD_SCHEMA, agentType: 'builder', effort: 'medium', isolation: 'worktree',
    })
    // Continuation: a builder cut by the 30-call cap returns PARTIAL with remaining_steps; resume on the same branch (max 3 times).
    for (let k = 1; k <= 3 && (!build || !build.evidence || !build.evidence.pr_number || (build.status === 'PARTIAL' && build.evidence.remaining_steps && build.evidence.remaining_steps.length)); k++) {
      log(`${p.id}: build continuation ${k} (${build.evidence.remaining_steps.length} steps left)`)
      const hadEvidence = build && build.evidence
      const salvage = hadEvidence
        ? `a previous builder already pushed WIP to branch ${branchOf(pp)} (head ${build.evidence.head_sha}, PR ${build.evidence.pr_url || 'not yet opened'})`
        : `the previous builder returned no result (likely cut off at the 30-call cap with NO StructuredOutput). Before doing anything else, probe for salvage: git ls-remote --heads origin ${branchOf(pp)} (does the branch exist on origin?) and gh pr list -R ${repoOf(pp)} --head ${branchOf(pp)} --json number,url,state (was a PR already opened?). If the branch exists, check it out and continue from its actual state; if it does not, start the packet from scratch`
      const steps = (hadEvidence && build.evidence.remaining_steps) || []
      const cont = `CONTINUATION ${k}: ${salvage}. First: git fetch origin ${branchOf(pp)} 2>/dev/null; if the branch exists: git checkout -B ${branchOf(pp)} origin/${branchOf(pp)}. Then do ONLY these remaining steps, in order (if none are known, redo the full buildPrompt below from the current branch state):${steps.map((st, i) => `\n  ${i + 1}. ${st}`).join('')}\n\n`
      build = await agent(cont + buildPrompt(pp, specText), {
        label: `build${k + 1}:${p.id}`, phase: 'Build', schema: BUILD_SCHEMA, agentType: 'builder', effort: 'medium', isolation: 'worktree',
      })
    }
    return { p: pp, spec, build }
  },
  // 3. Review
  async ({ p, spec, build }) => {
    if (!build || !build.evidence || !build.evidence.pr_number) { log(`${p.id}: no PR from build stage`); return { p, spec, build, review: null } }
    const review = await agent(reviewPrompt(p, build.evidence), {
      label: `review:${p.id}`, phase: 'Review', schema: REVIEW_SCHEMA, agentType: 'reviewer', effort: 'high',
    })
    return { p, spec, build, review }
  },
  // 4. Fix (only when the reviewer demands it), then re-review once
  async ({ p, spec, build, review }) => {
    if (!review || !build) return { p, spec, build, review, fix: null, rereview: null }
    const v = review.evidence
    if (v.verdict === 'PASS') return { p, spec, build, review, fix: null, rereview: null }
    if (v.verdict === 'REJECT') { log(`${p.id}: REJECTED by reviewer — ${review.result}`); return { p, spec, build, review, fix: null, rereview: null } }
    const fix = await agent(fixPrompt(p, build.evidence, v), {
      label: `fix:${p.id}`, phase: 'Fix', schema: BUILD_SCHEMA, agentType: 'builder', effort: 'medium', isolation: 'worktree',
    })
    const rereview = await agent(reviewPrompt(p, build.evidence), {
      label: `rereview:${p.id}`, phase: 'Review', schema: REVIEW_SCHEMA, agentType: 'reviewer', effort: 'high',
    })
    return { p, spec, build, review, fix, rereview }
  },
  // 5. Ship
  async (ctx) => {
    const { p, build, review, rereview } = ctx
    const final = rereview || review
    if (!build || !final || final.evidence.verdict !== 'PASS') {
      log(`${p.id}: not shipped (verdict ${final ? final.evidence.verdict : 'n/a'})`)
      return { ...ctx, ship: null }
    }
    let ship = await agent(shipPrompt(p, build.evidence), {
      label: `ship:${p.id}`, phase: 'Ship', schema: SHIP_SCHEMA, agentType: 'builder', effort: 'low',
    })
    // A ship agent that hits its budget while checks are pending returns PARTIAL; re-spawn (each attempt waits up to ~45 min).
    for (let k = 2; k <= 5 && ship && ship.status === 'PARTIAL' && !(ship.evidence && ship.evidence.merged && ship.evidence.live_verified); k++) {
      log(`${p.id}: ship attempt ${k}`)
      ship = await agent(`SHIP ATTEMPT ${k}: a previous ship agent already ran (result: ${String(ship.result).slice(0, 400)}; merged=${ship.evidence && ship.evidence.merged}). Do not repeat completed steps; resume from the first incomplete one.\n\n` + shipPrompt(p, build.evidence), {
        label: `ship${k}:${p.id}`, phase: 'Ship', schema: SHIP_SCHEMA, agentType: 'builder', effort: 'low',
      })
    }
    return { ...ctx, ship }
  },
)

const summary = results.filter(Boolean).map(r => ({
  id: r.p.id,
  lane: r.p.lane,
  ledger_rows: r.p.ledger_rows || [],
  spec: r.spec ? r.spec.status : 'NULL',
  pr: r.build && r.build.evidence ? r.build.evidence.pr_number : null,
  pr_url: r.build && r.build.evidence ? r.build.evidence.pr_url : null,
  verdict: (r.rereview || r.review) ? (r.rereview || r.review).evidence.verdict : null,
  blockers_open: (r.rereview || r.review) ? ((r.rereview || r.review).evidence.blockers || []) : [],
  merged: r.ship && r.ship.evidence ? r.ship.evidence.merged : false,
  merge_sha: r.ship && r.ship.evidence ? r.ship.evidence.merge_sha : null,
  live_verified: r.ship && r.ship.evidence ? r.ship.evidence.live_verified : false,
  live_proof: r.ship && r.ship.evidence ? r.ship.evidence.live_proof : null,
  gaps: [].concat(...[r.spec, r.build, r.review, r.fix, r.rereview, r.ship].map(s => (s && s.gaps) || [])),
}))

const shipped = summary.filter(s => s.merged && s.live_verified).length
log(`Wave ${WAVE} (${CEO}): ${shipped}/${summary.length} packets merged + live-verified`)
return { ceo: CEO, wave: WAVE, shipped, total: summary.length, packets: summary }
