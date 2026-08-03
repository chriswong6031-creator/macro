# BioCatalyst D0a — IA, state, content, and reference contract

Status: **draft reference contract; human design approval pending**
Owner: BioCatalyst product design
Companion executable manifest: `config/biocatalyst_product_acceptance.yml`

## 0. Scope, collision boundary, and release posture

This is the BioCatalyst-specific D0a design contract. It does not add a production
template, API, collector, timer, source entitlement, user store, model, Neural Web
reader, or Prophet behavior. The reference corpus is synthetic and non-authorizing.

The merged **Sector Intelligence Workspace V2 masterplan** now owns the active host
shell direction in `research/SI_WORKSPACE_V2_MASTERPLAN_BY_FABLE.md`. It defines the
five-view workspace/navigation doctrine; no shared shell primitive is shipped by this
contract. This lane therefore owns only the Bio-specific information architecture,
content grammar, finite references, and acceptance contract. It deliberately does
**not** edit `templates/`, `site/`, shared navigation, sector-router code, or V2
masterplan paths. D0b must align to that five-view doctrine and consume the shared
shell primitives when their implementation lands; it must not fork a Bio-only shell.

No reference state is a release approval. The current manifest is intentionally
`draft_human_approval_pending`: it fails generic acceptance until a named Fable or
Opus design owner records an approval and a production-shaped browser run exists.

## 1. Design thesis — an operator cockpit with an epistemic envelope

BioCatalyst is not a calendar wearing a terminal costume. It is a compact decision
workspace for answering: **what changed, what is actually known, when was it known,
and what is still missing?** The visual hierarchy makes the evidence envelope more
legible than the headline.

Every rich-value surface has five non-optional adjacent cues:

| Cue | User-facing language | Meaning | Display rule |
|---|---|---|---|
| Fact class | `Reported`, `Registry fact`, `Model`, or `Unavailable` | what kind of statement this is | never infer a stronger class from color |
| Time | `As known 14:32 UTC` or a precision interval | public/record availability, not a false exact date | one stamp per panel |
| Provenance | named source and resolvable evidence thread | where the fact came from | source is a link, not a vague badge |
| Completeness | `Complete`, `Partial`, `Stale`, `Outage`, or `Locked` | what the system cannot currently establish | visible before any rich metric |
| Authority | `Research context — no trade call` | allowed use | always persists in the research tray/footer |

The envelope creates a hard UI distinction between direct source facts, reviewed
interpretation, model output, and absence. A card never disguises an unavailable
dependency as a zero, a hidden tab, or a generic loading shimmer. This is how the
suite feels premium without becoming theatrically certain.

### Visual direction

- **Character:** deep observatory, not a legacy data grid: ink-black / graphite
  canvas, hairline structure, warm bone text, electric mint for source-backed
  movement, violet only for explicitly model-labelled material, and amber/red for
  caution/error—not sentiment.
- **Light mode:** warm quartz canvas, navy text, forest source accents, preserved
  hierarchy and contrast. It is a separate composed theme, not inverted dark mode.
- **Typography:** a calm grotesk for dense operating data with a high-contrast
  editorial face only for the top-level question. No oversized marketing numerals;
  precision is carried by alignment, tabular figures, and breathing room.
- **Density:** one loud question per column; panels have a one-line purpose and a
  single primary action. Details move into evidence threads, object drawers, and
  research tray pins.
- **Motion:** 160–220 ms opacity/transform transitions communicate focus changes;
  reduced-motion swaps every transition for an immediate state change. Motion never
  carries sole meaning.

## 2. Information architecture

| Surface | Primary job | Glance tier | Study tier / signature interaction | Explicit non-claim |
|---|---|---|---|---|
| **Catalyst Radar** | orient to source-reported upcoming constraints and fresh changes | time window, object, fact class, completeness | expand the evidence envelope; pin a row to Research Tray | no probability, expected move, or trade stance |
| **Explorer** | find a bounded cohort with inspectable filters | result count, active filters, data coverage | filter provenance drawer; save only through product-plane adapter | no invisible ranking or inferred issuer match |
| **Dossiers** | understand one company, asset, trial, or regulatory object | object identity, source-backed status, missing dependencies | evidence thread, point-in-time/as-known selector, contradiction rail | no fabricated links across ambiguous identity |
| **Change Tape** | audit exactly what changed and corrections | change class, before/after, source time | side-by-side source-path diff; correction lineage playback | no materiality or delay claim without reviewed layer |
| **Research Workbench** | compare explicit objects and keep working context | cohort name, comparison coverage, pinned questions | Trial Peer Matrix and Research Tray collection | no auto-generated peer or competitor cohort |
| **Alerts** | explain why a user received a source event | watch provenance, event fact class, received time | modify/snooze the governed watch; inspect correction | no attention score disguised as urgency |
| **Data / API** | make coverage, freshness, field semantics, and export policy visible | source health, projection availability, schema version | field dictionary and request receipt view | no raw-store/private-object exposure |

The top-level order is: **Radar → Explorer → Dossiers → Change Tape → Research
Workbench → Alerts → Data/API**. The user may arrive directly at a dossier, but the
system preserves the originating cohort, filters, scroll point, and as-known context.

### Shared frame

1. A narrow left rail names the seven surfaces and carries no live count badges that
   could move layout late.
2. The upper command line holds global search, as-known mode, data-completeness
   status, and a compact research-tray counter. It never implies identity resolution.
3. A focused main canvas holds one page question plus a finite amount of Tier-1
   content. Tables virtualize; dense fields open locally.
4. The right **Evidence Thread** is a persistent desktop rail, a tablet drawer, and a
   mobile bottom sheet. It always includes source class, availability time, exact
   locator/record version, correction link, and enough surrounding text to avoid a
   misleading fragment.
5. The **Research Tray** is a small, persistent context drawer. Canonical saved state
   belongs to the existing product plane, not browser storage or this package.

## 3. Content grammar and component rules

### 3.1 Rich value card

```
FACT CLASS  ·  SOURCE  ·  AS KNOWN TIME
Primary field / interval / unavailable state
Plain-language interpretation (one line)
Evidence   Completeness   Authority
```

The first line is immutable in its order. `Unavailable` replaces numeric content;
`Partial` keeps the known value but states which dependency is absent. `Reported` is
never recolored to look like regulator-verified. Each card has one source/evidence
action, not a pile of generic chips.

### 3.2 Object identity ribbon

Identity is presented as: source-native name → stable object ID → relationship state.
When an asset/company/security relationship is unresolved, show `Ambiguous link` with
candidate edges and no ticker. A ticker is not an identity shortcut. The ribbon never
collapses an ambiguous asset owner into a preferred company.

### 3.3 State banners

| State | Header copy | Body behavior | Allowed primary action |
|---|---|---|---|
| Source outage | `Source temporarily unavailable` | retain last good values with age and source label | inspect source health |
| Stale | `Data needs refresh` | retain data, state the target and actual age | inspect freshness receipt |
| Partial | `Some context is not available` | reveal missing dependency inline | inspect coverage |
| Ambiguous identity | `Relationship needs review` | show candidates separately, do not join | inspect links |
| Contradiction | `Sources disagree` | show both claims and chronology | compare evidence |
| Correction | `Earlier record corrected` | preserve before/after and correction chain | open Change Tape |
| Historical | `Viewing history` | freeze as-known time and hide now-only affordances | return to current |
| Locked | `This view needs access` | show no denied values, no layout shift | view access options |
| Empty | `No matching records` | preserve filters and explain the search scope | clear one filter |
| Error | `This view could not load` | no stale value masquerades as fresh | retry / inspect receipt |

### 3.4 Content priorities

The leading copy follows `docs/DESIGN_DOCTRINE.md`: a short title, one plain-language
line, one meaningful number/interval only when its interpretation is adjacent, then
the envelope. “Signal”, “score”, “rank”, forecast language, and trading directives are
not Tier-1 vocabulary in D0a. Chinese is written as native concise product copy, never
a raw English token drop.

## 4. Deterministic state precedence

One object can be both historical and partial, or corrected and stale. The following
precedence determines the primary banner and action; lower states remain visible as
secondary labels in the envelope. This makes screenshots, support, alerts, and later
automation deterministic.

| Rank | State | Why it wins | Required visible secondary context |
|---:|---|---|---|
| 1 | access denied / locked | no data may leak | object title only, access explanation |
| 2 | privacy / rights / integrity block | unsafe data is never rendered | safe status + incident/review reference |
| 3 | source capability absent | a field cannot be truthfully computed | missing source/dependency |
| 4 | ambiguous identity | prevents false cross-object joins | candidate identities/edges |
| 5 | contradiction | competing evidence changes interpretation | both claims + chronology |
| 6 | correction / retraction | newer source history changes prior reading | before/after + correction chain |
| 7 | source outage | live freshness cannot be claimed | last-good age + outage source |
| 8 | stale | value is known but outside target freshness | target/actual age |
| 9 | historical mode | user deliberately requested a past view | selected as-known time |
| 10 | partial dependency | some, not all, fields are missing | field-level unavailable labels |
| 11 | empty | query succeeded without a match | query/filter summary |
| 12 | normal | all currently permitted fields are available | ordinary envelope |

If two states have equal rank, use the earliest `known_at`, then lexical state code as a
stable tie breaker. This rule belongs in D0b state-harness fixtures—not client-local
ad hoc conditionals.

## 5. Interaction and responsive contract

| Viewport | Layout | Primary interaction rules |
|---|---|---|
| 1440×900 desktop | rail + main canvas + evidence rail | arrow-key result navigation; inspector remains visible; research tray is docked |
| 820×1180 tablet | compact rail + one main column + evidence drawer | filters open as a bounded sheet; comparison table maintains an identity column |
| 390×844 mobile | one focused list or dossier | object opens full height; explicit Back restores filter/scroll/focus; evidence opens bottom sheet; tray is compact drawer |

At 390×844, never compress a peer matrix into unreadable cells: show semantic comparison
cards or a horizontal table with frozen identity. No meaning is hover-only. Focus order
is rail/menu → page question → filters → results → inspector/evidence → research tray;
Escape returns from transient panels. The semantic DOM must maintain this order even if
the visual order changes.

## 6. Frozen reference matrix

The 24 committed PNGs in `mockups/refs/biocatalyst/d0a/` cover every required
viewport × theme × language × motion cell. They are **draft contract-state plates**
rendered through a non-portable SVG→sips reference renderer—not final browser truth
and not an approval substitute. The renderer loads and validates the bound synthetic
fixture and projection; its exact source bytes, both data inputs, every PNG, masks,
thresholds, and exact cell metadata are bound in the manifest and draft receipt.

| Viewport | Dark EN | Dark ZH | Light EN | Light ZH |
|---|---|---|---|---|
| 1440×900 | Radar / Change Tape | Explorer / Asset ambiguity | Trial Matrix / Company partial | Regulatory / Evidence Thread |
| 820×1180 | Radar / Explorer | Change Tape / Historical | Company partial / Trial Matrix | Asset ambiguity / Regulatory |
| 390×844 | Explorer / Locked | Dossier ambiguity / Empty | Evidence Thread / Outage | Change Tape correction / Historical |

Each slash means the standard-motion and reduced-motion sibling of that theme/language
cell respectively. The exact state code is recorded in the manifest; all twelve states
in §3.3 are present. Reduced-motion captures visibly retain the same information and
focus treatment with no animated affordance.

## 7. Acceptance and human gate

The acceptance contract establishes five fail-closed boundaries for D0b:

1. binds this design spec, synthetic fixture and projection, renderer source, benchmark
   corpus, draft receipt, and every PNG by SHA-256;
2. rejects unknown viewport/theme/language/motion combinations, incomplete matrix
   coverage, unsafe masks, changed image dimensions, and unbounded thresholds;
3. freezes exact desktop/tablet/mobile engine, version, OS, font, scale, and network
   profiles without claiming that a performance run has happened;
4. requires completed measurement receipts to byte-bind raw samples and summary code;
   and
5. remains draft-only and unconditionally rejects generic acceptance, even if every
   approval, browser, and performance field is self-described as passed.

The named approval that remains human-gated is **Fable / Opus design owner approval**.
It is deliberately blank in the draft manifest. Filling it is a design review decision,
not a builder-side edit and not permission to activate a source or ship a trading tool.
This v1 has no supersession lineage: both predecessor fields are fixed null. A future
trusted-browser verifier must use a separately reviewed successor contract; it cannot
turn this integrity-only draft into an approval by editing its manifest fields.

## 8. D0b implementation handoff

D0b may build the Bio-specific state atlas only after the human gate above; it must
align its navigation and workspace composition to the merged Sector Intelligence V2
five-view doctrine, then consume the shared shell once those primitives land. It must
render all D0a cells against contract-exact fixtures; capture browser screenshots using
the frozen browser/font/device metadata; and leave all source, identity, model, Neural
Web, and Prophet authority unchanged.
