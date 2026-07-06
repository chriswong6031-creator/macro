export const meta = {
  name: 'cycle-cause-research',
  description: 'Deep web-grounded cause research for every 15y sector/basket cycle leg + a per-series cycle-DNA profile',
  phases: [
    { title: 'Research', detail: 'one agent per series: explain every dated cycle leg, grounded in leg_context + web history' },
    { title: 'Verify', detail: 'adversarial fact-check vs the cross-asset grounding + web, fix errors, finalize' },
  ],
}

// Internal concurrency cap — kept LOW so a single solo run never trips the server-side
// rate limiter (running multiple workflows concurrently is what throttled earlier runs).
const CONCURRENCY = 8

const LEG = {
  type: 'object',
  required: ['date', 'title', 'body', 'drivers', 'title_zh', 'body_zh', 'drivers_zh'],
  additionalProperties: false,
  properties: {
    date: { type: 'string', description: 'the leg START date, EXACTLY matching a bundle leg.start (YYYY-MM-DD)' },
    title: { type: 'string', description: 'plain-English headline naming the leg driver, <=7 words' },
    body: { type: 'string', description: '2-4 sentences: what happened & WHY, specific dated catalysts, consistent with ctx grounding' },
    drivers: { type: 'array', items: { type: 'string' }, description: '3-5 short causal driver tags' },
    title_zh: { type: 'string' }, body_zh: { type: 'string' },
    drivers_zh: { type: 'array', items: { type: 'string' } },
  },
}

const DNA = {
  type: 'object',
  required: ['summary', 'summary_zh', 'drivers', 'drivers_zh', 'top_signals', 'bottom_signals',
    'top_signals_zh', 'bottom_signals_zh', 'median_cycle_months', 'analog', 'analog_zh', 'confidence'],
  additionalProperties: false,
  properties: {
    summary: { type: 'string', description: 'what STRUCTURALLY drives THIS series to cycle — the rhyming pattern (2-4 sentences)' },
    summary_zh: { type: 'string' },
    drivers: { type: 'array', items: { type: 'string' }, description: 'the recurring causal forces behind its cycles (macro/policy/commodity/flow), 3-6' },
    drivers_zh: { type: 'array', items: { type: 'string' } },
    top_signals: { type: 'array', items: { type: 'string' }, description: 'what has historically marked its PEAKS (2-4)' },
    bottom_signals: { type: 'array', items: { type: 'string' }, description: 'what has historically marked its TROUGHS (2-4)' },
    top_signals_zh: { type: 'array', items: { type: 'string' } },
    bottom_signals_zh: { type: 'array', items: { type: 'string' } },
    median_cycle_months: { type: 'number', description: 'median peak-to-peak (full) cycle length in months, computed from the leg dates' },
    analog: { type: 'string', description: 'which PAST leg the CURRENT setup most rhymes with, and why (the "sing along" read)' },
    analog_zh: { type: 'string' },
    confidence: { type: 'string', enum: ['low', 'medium', 'high'] },
  },
}

const RESULT = {
  type: 'object',
  required: ['key', 'now', 'now_zh', 'legs', 'dna'],
  additionalProperties: false,
  properties: {
    key: { type: 'string' },
    now: { type: 'string', description: 'current focus read: what is driving this series NOW (phase/position/leadership), 2-4 sentences' },
    now_zh: { type: 'string' },
    legs: { type: 'array', items: LEG, description: 'ONE entry per bundle leg — cover EVERY leg, no gaps' },
    dna: DNA,
    issues: { type: 'array', items: { type: 'string' }, description: 'verify stage: what was wrong in the draft and fixed (empty if clean)' },
  },
}

// ---- args: {series:[{key,region,bucket,name,path,n_legs}]} (mixed regions/buckets ok),
//      or legacy {region,bucket,series:[{key,name,path,n_legs}]}.
let A = args
if (typeof A === 'string') { try { A = JSON.parse(A) } catch (e) { A = {} } }
A = A || {}
const series = (A.series || []).map((s) => ({
  ...s, region: s.region || A.region || 'us', bucket: s.bucket || A.bucket || 'sectors',
}))
// singleStage: one Sonnet agent that drafts AND self-verifies (no separate Opus verify) — ~half
// the agents/tokens, so a large batch fits inside one account session window. Used for the
// secondary universe (baskets + China) when the 2-stage flagship pass is quota-constrained.
const singleStage = A.singleStage === true
const SELF_VERIFY = `

SINGLE-PASS QUALITY GATE (there is NO second reviewer — you are also the fact-checker). Before returning, RE-READ every leg and: (1) cross-check each cause against the bundle ctx grounding and FIX any claim the data refutes (wrong direction, "flight to safety" when defensives actually lagged, sector strength that was really index beta); (2) web-verify each major (>=20%) leg's catalyst and exact date — drop or correct anything unconfirmable; (3) be CONSERVATIVE on "now": stick to the ctx numbers and do NOT assert specific recent (last-90-day) company/policy events unless you web-confirmed them. Return only well-supported claims, with a non-empty "issues" list noting anything you corrected.`

function researchPrompt(s) {
  const region = s.region, bucket = s.bucket
  const benchLabel = region === 'china' ? 'the Shanghai Composite (SHCOMP) and cross-Shenwan rotation' : 'SPY and the 11 GICS SPDR sectors'
  return `You are an elite macro & sector historian writing the DEFINITIVE, front-loaded cause record for one ${region.toUpperCase()} ${bucket === 'sectors' ? 'sector' : 'thematic basket'}: ${s.name} (key="${s.key}").

Read the research bundle first:
  Read ${s.path}

It contains, for this series over up to the last 15 years:
- "legs": ${s.n_legs} dated cycle legs (turn→turn). Each has start, end, dir (rally/selloff), mag_pct, a "major" flag (>=20% move), and "ctx" = the REAL cross-asset ROTATION grounding for that exact window (which ${region === 'china' ? 'Shenwan industries' : 'sectors'} led/lagged, defensives-vs-cyclicals, ${region === 'china' ? 'growth-vs-value style, SHCOMP return' : 'quad regime, dollar/oil/rates/VIX, breadth'}, and plain-English "signals").
- "current": today's phase/position + now_ctx.
- ${region === 'us' && bucket === 'sectors' ? '"existing_now"/"existing_legs": prior researched text for RECENT legs — PRESERVE and lightly improve what is already good; your job is to ALSO fill every older (pre-2020) leg and deepen causes.' : 'no prior narratives exist — you are writing them all from scratch.'}

YOUR TASK — for EVERY one of the ${s.n_legs} legs, explain WHAT happened and WHY it moved, as a falsifiable causal claim:
- Name the SPECIFIC dated catalyst(s): the macro regime, policy action, rate/dollar/commodity move, earnings/guidance event, or ${region === 'china' ? 'Beijing policy (stimulus, deleveraging campaign, property curbs, regulatory crackdown, RRR/LPR cuts, zero-COVID, A-share margin/leverage cycle)' : 'Fed pivot, recession/growth scare, oil shock, credit event, election/tariff policy'} that drove THIS leg.
- Your causal claim MUST be consistent with the ctx grounding: if ctx says defensives led while ${region === 'china' ? 'SHCOMP fell' : 'VIX rose'}, the cause is a risk-off/flight-to-safety rotation, NOT sector-specific strength. Cross-check leaders/laggards and the "signals".
- VERIFY specific dates/events with web search. Load tools if needed: ToolSearch "select:WebSearch,WebFetch", then WebSearch the period (e.g. "${s.name} ${region === 'china' ? 'A-shares' : 'sector'} 2015" / the catalyst). Confirm the catalyst is real and correctly dated before asserting it. Prefer specifics over generic "uncertainty".
- title: <=7 words naming the driver. body: 2-4 tight sentences, concrete (cite the actual rates/dollar/oil/policy/earnings move). drivers: 3-5 short tags.

Then write:
- "now": what is driving ${s.name} RIGHT NOW (use current + now_ctx): its phase, cycle position, ${region === 'china' ? 'leadership vs Shenwan peers' : 'RS rank vs SPY/peers'}, and the live setup.
- "dna" (the PREDICTIVE "history rhymes" layer): summary = what STRUCTURALLY makes ${s.name} cycle (its recurring causal engine, referencing ${benchLabel}); drivers = the recurring forces; top_signals/bottom_signals = what has historically marked its peaks vs troughs (so future turns can be anticipated); median_cycle_months = compute the median PEAK-TO-PEAK length from the leg dates; analog = which PAST leg today's setup most rhymes with and why — LEAD with the past analog (its date + type), e.g. "Closest to the Oct-2018 peak: same rate-shock-into-narrow-leadership setup…"; do NOT begin the analog with the word "Today"; confidence.

Bilingual: every *_zh field is idiomatic financial Chinese (the dashboard is bilingual), NOT machine-literal. Cover EVERY leg — the "date" field of each entry MUST equal a bundle leg "start" exactly. Be specific, accurate, and dense. Return ONLY the structured object for key="${s.key}".`
}

function verifyPrompt(s, draftJson) {
  const region = s.region, bucket = s.bucket
  return `You are an ADVERSARIAL fact-checker and finalizer for the cycle-cause record of ${region.toUpperCase()} ${bucket} "${s.name}" (key="${s.key}"). Default to skepticism.

1. Read the grounding bundle:  Read ${s.path}
2. Here is the DRAFT to audit:
${draftJson}

Audit EVERY leg against the bundle's ctx grounding and real history:
- CONTRADICTIONS: does any "body" claim a rotation/cause the ctx data refutes? (e.g. claims "flight to safety" but defensives actually LAGGED; claims sector strength when it was just market beta / ${region === 'china' ? 'SHCOMP' : 'SPY'} doing the work; wrong direction). Fix to the ctx-grounded truth.
- FACTUAL ERRORS: web-verify the named catalyst and its date for EVERY major (>=20%) leg and any specific claim. Load tools if needed (ToolSearch "select:WebSearch,WebFetch"). Wrong/unconfirmable catalyst → replace with the supported cause. No invented events, no misdated ones.
- COVERAGE: there must be exactly one entry per bundle leg (date == a leg.start). Add any missing leg; drop duplicates/legs not in the bundle.
- DNA: sanity-check median_cycle_months vs the actual dates; ensure top/bottom signals and the analog are concrete and supported.
- ZH: ensure faithful, idiomatic translations (not literal).

Return the FULL CORRECTED object (same schema) with "issues" listing each substantive change you made (empty array if the draft was clean). This corrected object is FINAL.`
}

// concurrency-limited runner: at most CONCURRENCY series-pipelines in flight → caps live agents
async function mapLimit(items, limit, fn) {
  const out = new Array(items.length)
  let idx = 0
  async function worker() {
    while (idx < items.length) {
      const i = idx++
      out[i] = await fn(items[i], i)
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
  return out
}

log(`cycle-cause-research: ${series.length} series, ${series.reduce((a, s) => a + (s.n_legs || 0), 0)} legs, concurrency=${CONCURRENCY}`)

const tagged = await mapLimit(series, CONCURRENCY, async (s) => {
  const draft = await agent(researchPrompt(s) + (singleStage ? SELF_VERIFY : ''), { label: `draft:${s.region}:${s.key}`, phase: 'Research', model: 'sonnet', effort: 'high', schema: RESULT })
  if (!draft) { log(`draft FAILED: ${s.region}/${s.bucket}/${s.key}`); return null }
  if (singleStage) return { region: s.region, bucket: s.bucket, result: draft }
  const fin = await agent(verifyPrompt(s, JSON.stringify(draft)), { label: `verify:${s.region}:${s.key}`, phase: 'Verify', effort: 'high', schema: RESULT })
  return { region: s.region, bucket: s.bucket, result: fin || draft }
})

const groups = {}
for (const t of tagged.filter(Boolean)) {
  const k = `${t.region}__${t.bucket}`
  ;(groups[k] = groups[k] || { region: t.region, bucket: t.bucket, results: [] }).results.push(t.result)
}
const groupList = Object.values(groups)
log(`done: ${tagged.filter(Boolean).length}/${series.length} series finalized across ${groupList.length} groups`)
return { groups: groupList }
