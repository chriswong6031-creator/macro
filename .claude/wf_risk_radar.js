export const meta = {
  name: 'risk-radar-redesign',
  description: 'Design panel: 4 directions for the Market Risk Radar alert, judge, synthesize a final spec',
  phases: [
    { title: 'Design', detail: '4 independent design directions for the panel' },
    { title: 'Judge', detail: '3 judges score all 4 directions + pick grafts' },
    { title: 'Synthesize', detail: 'merge winner + grafts into one build-ready spec' },
  ],
}

const BRIEF = `
PRODUCT — "Market Risk Radar": the primary top-of-page risk panel on an institutional-grade macro
markets dashboard (dark, Bloomberg-terminal-adjacent, Inter typeface, used by serious traders).
The panel's ONE job: tell the reader at a glance (1) HOW elevated near-term pullback risk is,
(2) WHY — which threat-types are firing, and (3) WHAT to do about it (position sizing).

THE PROBLEM WE MUST FIX (this is why we are redesigning): today the panel dumps its single most
important number as a cramped middot-separated text run:
   "Drawdown odds (>=5% pullback, escalating): 5d 4% . 10d 10% . 21d 19% (1.07x base 18%)"
The user's verbatim reaction: "who tf can read what this is saying? ... literally low quality
content." That escalating pullback-probability across horizons is the HERO of the panel and MUST be
VISUALIZED, not stuffed into an inline text run. The rest of the panel is also a dense, unscannable
wall of small grey text full of cryptic engine codes. Make the WHOLE alert beautiful, organized,
clearly hierarchied and user-friendly.

============================ THE LIVE DATA (use these EXACT real values in your mockup) ============================
STATE: "caution"  (ladder: calm < watch < caution < elevated < risk-off). The accent color for the
   whole panel follows the state -> for CAUTION the accent is AMBER (var(--warn)).
DOMINANT THREAT: "Growth scare / defensive rotation", intensity 91/100.
HEADLINE (engine sentence): "Growth scare / defensive rotation (91/100), with Credit stress also
   firing. Leading evidence: defensives outperforming (93rd pctile), cyclicals fading (89th). Modest
   odds (~1.5-2x) - de-risk, favour good entries."

PULLBACK-ODDS (the HERO number set) - probability of a >=5% S&P pullback within each horizon, and it
   ESCALATES with horizon. Compare each to the unconditional "normal" base rate:
     5 days:  4%   (normal 3.6%)
     10 days: 10%  (normal 8.6%)
     21 days: 19%  (normal 17.8%)   <- headline; 1.07x normal
   Read: right now odds are only slightly above normal (state is early/caution, not a crash call).
   The design must make "current vs normal" instantly legible, and the 5->10->21 escalation visible.

THE 5 THREAT-TYPES ("scares"), each 0-100 intensity + plain-English firing evidence (sorted by intensity):
  1. Growth scare / defensive rotation -- 91 -- VALIDATED -- evidence: "Defensives outperforming" 93rd
       pctile [CONFIRMED, 1.62x lift];  "Cyclicals fading vs defensives" 89th pctile [1.63x lift]
  2. Credit stress -- 68 -- VALIDATED -- evidence: "HY bonds lagging Treasuries" 83rd pctile [0.5x];
       "HY credit spreads widening" 65th pctile [1.23x]
  3. Volatility event -- 58 -- DISPLAY-ONLY -- evidence: "VIX term-structure stress" 58th pctile [0.44x]
  4. Bubble / blow-off unwind -- 38 -- VALIDATED -- evidence: "Narrow leadership (semis vs S&P)" 98th
       pctile [CONFIRMED, 0.38x]
  5. Rates / inflation shock -- 14 -- VALIDATED -- evidence: (none firing)
   (pctile = how extreme that signal is right now; "lift" = measured conditional multiplier on forward
    drawdown odds; CONFIRMED = at/above the strict backtest threshold. Keep these but make them readable,
    not cryptic.)

LOUD-ALERT GATE: SHUT -- "broad tape intact; quiet/early tier only." (When OPEN the whole panel goes
   loud and floats to the very top of the page and pulses. Design both the quiet and loud feel.)
ACTION ("Do"): "Trim chasing; favour good entries over extended leaders; honour stops."
SUGGESTED GROSS EXPOSURE: x0.90  (i.e. run ~90% of normal position size).
QUIET FOOTER META (keep small/secondary): a self-audit track-record line (graded calls / alert
   precision / recall / false alarms) shown only when present; a "vol-event detection still accruing:
   put/call 17/252 days, GEX 17/252 days" note; and a one-line methodology disclaimer.

============================ HARD CONSTRAINTS ============================
- DARK institutional dashboard. Use ONLY these CSS variables (no hard-coded hex anywhere):
    --bg:#0f1115  --panel:#181b21  --panel2:#1e222a  --text:#d7dce3  --muted:#8b93a1  --line:#2a2f3a
    --warn:#e0a030 (amber = caution)  --orange:#e08b45 (elevated)  --act:#e05555 (red = danger/risk-off)
    --ok:#3da564 / --up:#45b873 (green = safe/normal)  --info:#5b9bf0  --link:#7aa7e0
  The panel accent is var(--rr) which for this state = var(--warn). Build tints with
  color-mix(in srgb, var(--warn) 14%, transparent) etc. NEVER introduce a new raw color.
- Typeface: Inter (already loaded), weights 400-900 available. Hierarchy comes from size/weight/spacing,
  tabular-nums for figures (font-variant-numeric: tabular-nums).
- BILINGUAL-SAFE: in production every label is duplicated EN/ZH, so keep labels SHORT and avoid layouts
  that break if a label's width changes. (Write English-only in the mockup.)
- RESPONSIVE: full-width on desktop, must reflow to a single readable column under 900px. No horizontal scroll.
- Self-contained: ONE <div> block with an inline <style> scoped to a unique wrapper class. Pure HTML+CSS
  only -- NO external images, NO JS, NO web fonts beyond inheriting Inter. It must render standalone on a
  --bg:#0f1115 page. Define the listed CSS vars locally in your scoped style so it renders alone.
- This is a RISK panel: never make low risk look scary or high risk look calm; the color must track state.

============================ WHAT MAKES THIS GOOD ============================
- The pullback-odds escalation is the visual HERO and is instantly readable (the fix for the complaint).
- Clear 3-zone hierarchy: HOW BAD (state + odds) -> WHY (threat meters + evidence) -> WHAT TO DO (action/sizing).
- The 5 threat-types read as a scannable ranked board, dominant one emphasised; evidence is plain-English.
- Quiet, disciplined, premium institutional feel -- not a busy wall of grey text, not a toy.
- One distinctive, content-true SIGNATURE element it will be remembered by.
`;

const RULES = `
Return a SINGLE self-contained mockup. The "html" field must be a complete <div class="rr-wrap-XXX">...</div>
(pick a unique suffix) with an inline <style> that scopes ALL rules to that wrapper class and locally
defines the CSS vars listed in the brief so it renders on a bare dark page. Bake in the EXACT real data
values. English-only labels, kept short. No JS, no external assets.
`;

phase('Design');
const DIRECTIONS = [
  { key: 'console',
    brief: 'DIRECTION A - "Risk console / equalizer." The signature is the 5 threat-types rendered as a row of calibrated meter bars (think a mixing console / signal spectrum) with the dominant one lit in the state accent and the inert/display-only ones dimmed; the pullback-odds hero is an escalating horizon ramp (5d -> 10d -> 21d) sitting above the console, with the "normal" base rate drawn as a faint reference. Dense but immaculately legible institutional console. Boldness lives in the console; everything else stays quiet.' },
  { key: 'editorial',
    brief: 'DIRECTION B - "Quiet editorial brief." The signature is a large typographic hero: the 21-day odds as a single commanding number with a small "vs 18% normal (1.07x)" delta beneath, set in a confident type scale with generous whitespace; the 5/10/21 escalation shown as a slim inline ramp; the threat-types as a restrained ranked list with hairline meters and plain-English evidence. Minimal, calm, premium - precision in spacing and type, almost no chrome.' },
  { key: 'chart',
    brief: 'DIRECTION C - "Analyst, chart-forward." The signature is a real small chart of the pullback odds: an escalating curve-or-bars across the 5/10/21-day horizons with the unconditional base rate as a dashed reference line and a clear "x normal" read, drawn in pure CSS/inline-SVG. The threat-types become compact horizontal intensity bars sorted high-to-low with evidence chips. Data-first, analytical, the kind of thing a desk strategist would screenshot.' },
  { key: 'command',
    brief: 'DIRECTION D - "Decision command card." The signature is a bold state band that recolors the panel header by state, a single prominent risk read, the three horizons as labeled stat tiles with escalation arrows (4% -> 10% -> 19%) each tagged vs normal, and the ACTION (trim chasing / suggested gross x0.90) elevated into a primary, can\'t-miss callout. Decisive, glanceable, built so a reader gets the verdict + the to-do in two seconds.' },
];

const DESIGN_SCHEMA = {
  type: 'object',
  required: ['direction', 'signature', 'rationale', 'tokens', 'type', 'layout', 'html', 'mobile_note'],
  additionalProperties: false,
  properties: {
    direction: { type: 'string' },
    signature: { type: 'string', description: 'the single memorable, content-true element' },
    rationale: { type: 'string', description: '<=3 sentences on why this serves the brief' },
    tokens: { type: 'string', description: 'how the palette is used (which var for what)' },
    type: { type: 'string', description: 'type roles: display / body / data, weights & scale' },
    layout: { type: 'string', description: '1-2 sentences; ascii wireframe allowed' },
    html: { type: 'string', description: 'complete self-contained <div> mockup w/ scoped inline <style>, real data baked in, dark theme' },
    mobile_note: { type: 'string', description: 'how it reflows under 900px' },
  },
};

const designs = (await parallel(DIRECTIONS.map(d => () =>
  agent(`You are a design lead at a studio known for distinctive, non-templated visual identities.
Design ONE direction for the Market Risk Radar panel.

${d.brief}

${BRIEF}

${RULES}`, { label: `design:${d.key}`, phase: 'Design', schema: DESIGN_SCHEMA })
    .then(r => r ? { ...r, key: d.key } : null)
))).filter(Boolean);

log(`${designs.length}/4 design directions returned`);

phase('Judge');
const JUDGE_SCHEMA = {
  type: 'object',
  required: ['scores', 'ranking', 'winner', 'best_grafts', 'risks'],
  additionalProperties: false,
  properties: {
    scores: {
      type: 'array',
      items: {
        type: 'object',
        required: ['direction', 'clarity_of_odds', 'beauty', 'institutional_fit', 'hierarchy', 'data_fidelity', 'distinctiveness', 'feasibility', 'total', 'note'],
        additionalProperties: false,
        properties: {
          direction: { type: 'string' },
          clarity_of_odds: { type: 'number', description: '0-10: is the pullback-odds escalation instantly readable (the thing we are fixing)' },
          beauty: { type: 'number', description: '0-10' },
          institutional_fit: { type: 'number', description: '0-10: dark Bloomberg-adjacent desk feel' },
          hierarchy: { type: 'number', description: '0-10: HOW-BAD -> WHY -> WHAT-TO-DO scannability' },
          data_fidelity: { type: 'number', description: '0-10: all real fields present & honestly colored' },
          distinctiveness: { type: 'number', description: '0-10: not a templated default' },
          feasibility: { type: 'number', description: '0-10: easy to wire into Jinja, bilingual, responsive, token-only' },
          total: { type: 'number' },
          note: { type: 'string' },
        },
      },
    },
    ranking: { type: 'array', items: { type: 'string' }, description: 'directions best -> worst' },
    winner: { type: 'string' },
    best_grafts: { type: 'array', items: { type: 'object', required: ['from', 'idea'], additionalProperties: false, properties: { from: { type: 'string' }, idea: { type: 'string' } } } },
    risks: { type: 'array', items: { type: 'string' } },
  },
};

const corpus = designs.map(d => `===== DIRECTION "${d.key}" (${d.direction}) =====
SIGNATURE: ${d.signature}
RATIONALE: ${d.rationale}
TOKENS: ${d.tokens}
TYPE: ${d.type}
LAYOUT: ${d.layout}
MOBILE: ${d.mobile_note}
HTML:
${d.html}`).join('\n\n');

const LENSES = [
  'You are a buy-side trader who will actually USE this panel every morning. Judge ruthlessly on whether the pullback-odds read is instant and whether you can act in 2 seconds. Penalize anything that still reads as a wall of text.',
  'You are an award-winning product/visual designer. Judge on beauty, type, hierarchy, restraint and distinctiveness. Punish templated defaults (cream+serif, single acid accent, generic stat-card) and decoration that does not encode information.',
  'You are the front-end engineer who must ship this into a bilingual (EN/ZH), light+dark, responsive Jinja template using ONLY the theme tokens. Judge on feasibility, data fidelity, and whether the color honestly tracks risk state.',
];

const verdicts = (await parallel(LENSES.map((lens, i) => () =>
  agent(`${lens}

Score EVERY one of the ${designs.length} design directions below for the Market Risk Radar panel. Use the full 0-10 range; do not bunch scores. Be specific in notes. The single most important criterion is clarity_of_odds (the cramped "5d 4% . 10d 10% . 21d 19%" line is exactly what we are fixing).

${BRIEF}

${corpus}`, { label: `judge:${i + 1}`, phase: 'Judge', schema: JUDGE_SCHEMA })
))).filter(Boolean);

// tally consensus
const tally = {};
for (const v of verdicts) for (const s of v.scores) {
  tally[s.direction] = (tally[s.direction] || 0) + (s.total || 0);
}
log(`judge consensus totals: ${JSON.stringify(tally)}`);

phase('Synthesize');
const SYNTH_SCHEMA = {
  type: 'object',
  required: ['chosen_direction', 'why', 'final_html', 'scoped_css', 'field_mapping', 'mobile_notes', 'build_notes'],
  additionalProperties: false,
  properties: {
    chosen_direction: { type: 'string' },
    why: { type: 'string' },
    final_html: { type: 'string', description: 'COMPLETE self-contained <div> panel mockup, dark theme, real data baked in, scoped inline <style>' },
    scoped_css: { type: 'string', description: 'the CSS rules to live under body.page-macro #risk-radar (no inline-style duplication)' },
    field_mapping: { type: 'array', items: { type: 'object', required: ['field', 'renders_as'], additionalProperties: false, properties: { field: { type: 'string' }, renders_as: { type: 'string' } } } },
    mobile_notes: { type: 'string' },
    build_notes: { type: 'string', description: 'guidance for wiring into Jinja: loops, conditionals, t() bilingual, state-color mapping' },
  },
};

const synthesis = await agent(`You are the design lead doing the FINAL pass. Below are ${designs.length} design
directions for the Market Risk Radar panel and ${verdicts.length} judge scorecards. Judge-total consensus: ${JSON.stringify(tally)}.

Produce ONE build-ready final design: take the consensus-winning direction as the spine and GRAFT the
single best idea from each runner-up where it strengthens clarity or beauty without adding clutter
(Chanel rule - if it's not earning its place, cut it). The pullback-odds escalation MUST be the
unmistakable visual hero and instantly readable. Keep it disciplined and premium; one signature element.

Deliver: final_html (a complete self-contained mockup with the EXACT real data baked in, dark theme,
scoped inline <style>, token-only colors, bilingual-safe short labels, responsive), the scoped_css block,
a field_mapping covering EVERY data field in the brief (state, top_score, headline, the 3 horizon
odds + base + lift, all 5 scares with intensity/tier/evidence, loud-alert gate, action + gross factor,
the quiet footer meta), mobile_notes, and build_notes for wiring into a bilingual Jinja template.

${BRIEF}

${corpus}

===== JUDGE SCORECARDS =====
${verdicts.map((v, i) => `JUDGE ${i + 1}: winner=${v.winner}; ranking=${v.ranking.join(' > ')}; grafts=${v.best_grafts.map(g => g.from + ':' + g.idea).join(' | ')}; risks=${v.risks.join('; ')}`).join('\n')}`,
  { label: 'synthesize', phase: 'Synthesize', schema: SYNTH_SCHEMA, effort: 'high' });

return { designs, verdicts, tally, synthesis };
