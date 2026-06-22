export const meta = {
  name: 'audit-basket-propagation',
  description: 'Adversarial multi-dimension audit of the regenerated us_stocks site after the 34-basket integration build',
  phases: [
    { title: 'Audit', detail: 'parallel auditors, one per dimension, hunting for real defects' },
    { title: 'Synthesize', detail: 'merge findings into a go/no-go verdict' },
  ],
}

const ROOT = (args && args.root) || '.'

const FINDING_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['dimension', 'status', 'findings', 'evidence'],
  properties: {
    dimension: { type: 'string' },
    status: { type: 'string', enum: ['ok', 'warn', 'fail'] },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'detail'],
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'nit'] },
          detail: { type: 'string' },
          where: { type: 'string' },
        },
      },
    },
    evidence: { type: 'string', description: 'concrete proof you actually inspected (counts, grep hits, file sizes)' },
  },
}

const common = `You are auditing a freshly REGENERATED static dashboard at ${ROOT}. This was a build that
added 3 narrative baskets (insurance, big_pharma, industrial_distribution; 31->34 baskets) and a
new unified sector+basket "What to act on now" board + de-crammed standout cards on us_stocks.html.
Be ADVERSARIAL: actively hunt for defects (broken layout, Jinja leftovers like {{ or {% in output,
empty/"Building…" sections that should have data, missing/duplicated content, broken links, NaN/null,
truncated files). Use Read/Grep/Bash to inspect the ACTUAL regenerated files. Report only what you can
prove with evidence. Default status to 'fail' for a blocker, 'warn' for major/minor, 'ok' if clean.`

phase('Audit')

const DIMENSIONS = [
  {
    key: 'new-basket-pages',
    prompt: `${common}
DIMENSION: the 3 NEW per-basket pages. Verify ${ROOT}/site/basket/insurance.html,
big_pharma.html, industrial_distribution.html each EXIST, are non-trivial in size, set body
background+color (the repo convention: a standalone page MUST set body{background:var(--bg);color:var(--text)}
or text renders black-on-dark), contain their member tickers, and have NO unrendered Jinja ({{ or {% or
"Undefined"). Compare structure to an existing basket page (e.g. site/basket/ai_semiconductors.html).`,
  },
  {
    key: 'action-board',
    prompt: `${common}
DIMENSION: the unified "What to act on now" board in ${ROOT}/site/us_stocks.html. Confirm it carries
BOTH GICS sectors (🏛) and narrative baskets (🧩), that every basket item's href (basket/<slug>.html)
points to a file that EXISTS under site/basket/, that the honesty markers (★ in-book, ✓ validated, ≈ lens)
render, and that the 3 new baskets are eligible to appear (grep their slugs/names). Flag broken links,
duplicated items, or a basket bucketed into an obviously wrong lane.`,
  },
  {
    key: 'standout-cards',
    prompt: `${common}
DIMENSION: the standout scorecard in ${ROOT}/site/us_stocks.html + its data ${ROOT}/site/factordata/us_standouts.json.
Verify: "Event edge" appears ONCE (not ~144x) and a single .nb-legend exists; "within-board percentile RANK"
appears ONCE; no per-card nb-tier div; basket_alloc coverage in us_standouts.json (count names with
conviction.basket_alloc — should be >= ~25, ideally higher now that 3 baskets were added; report the number);
de-risk cautions ("below its long-term trend" / "is deteriorating" / "is fading" / "crowded") are present and
consistent with the basket state. Flag any card-shatter (nested anchors), overflow, or dup boilerplate.`,
  },
  {
    key: 'allocation-model',
    prompt: `${common}
DIMENSION: ${ROOT}/site/allocationdata/allocation.json + ${ROOT}/site/allocation.html. Verify the ranks
array now has 34 entries, the 3 new baskets (insurance, big_pharma, industrial_distribution) are present with
sane gate{above_200dma}/durability/score (not null/NaN), allocation.html renders "34 themes", and the model
book weights are sane (each <= pos_cap 0.30, cash <= 0.60). Flag any NaN/null/missing-field or a basket that
silently dropped.`,
  },
  {
    key: 'mastermind-bundle',
    prompt: `${common}
DIMENSION: the Mastermind intake ${ROOT}/site/intelligence/by_ticker.json (and site/factordata/us_standouts.json).
Verify per-ticker bundles carry standout.conviction.basket_alloc for names that are in a basket (so Mastermind
sees the narrow-basket trend-gate state, not just GICS). Confirm the JSON is valid and not truncated. Report
how many tickers carry basket_alloc and show one example object.`,
  },
  {
    key: 'cross-page-integrity',
    prompt: `${common}
DIMENSION: whole-page integrity of ${ROOT}/site/us_stocks.html, ${ROOT}/site/macro.html, ${ROOT}/site/baskets.html.
Grep each for unrendered Jinja ({{, {%, "Undefined", "jinja2"), for stray "Building…" placeholders where real
data should be, and confirm file sizes are sane (us_stocks ~1.2-1.6MB, not truncated). Confirm body bg/color set.
Flag anything that would render visibly broken.`,
  },
]

const audits = await parallel(DIMENSIONS.map(d => () =>
  agent(d.prompt, { label: `audit:${d.key}`, phase: 'Audit', schema: FINDING_SCHEMA, agentType: 'Explore' })
))

phase('Synthesize')
const clean = audits.filter(Boolean)
const blockers = clean.flatMap(a => (a.findings || []).filter(f => f.severity === 'blocker' || f.severity === 'major').map(f => ({ dim: a.dimension, ...f })))
log(`audited ${clean.length}/${DIMENSIONS.length} dimensions · ${blockers.length} blocker/major findings`)

return {
  verdict: blockers.length === 0 ? 'GO' : 'ISSUES',
  dimensions: clean.map(a => ({ dimension: a.dimension, status: a.status, evidence: a.evidence,
    issues: (a.findings || []).length })),
  blockers,
  all_findings: clean.flatMap(a => (a.findings || []).map(f => ({ dim: a.dimension, ...f }))),
}
