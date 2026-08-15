# Component inventory — Live Entry Radar W8 reference

Sister components reuse Prophet Board class names so the RIG can measure drift.
Radar-only components use the `er-` prefix.

| Component | Class / hook | Sister of | Radar job |
|---|---|---|---|
| Reference banner | `.er-refbanner` `[data-reference-banner]` | — | Unmissable REFERENCE / SYNTHETIC mark |
| Page header | `.bh` `.bh-title` `.bh-purpose` | Prophet `.bh` | Title + Radar question |
| Sister distinction | `.er-sister` | — | Prophet vs Radar question, one line |
| Session stamp | `.dtp-token` `.pbs` | Prophet freshness tokens | Session + synthetic/degraded |
| Probe Set headline | `.ladder-n` `[data-probe-set]` | Prophet `.ladder-n` | Probe Set count |
| Lifecycle ladder | `.mx-ladder` `.mx-cell` | Prophet ladder | Probing / Pre-candidate / Candidate \| Invalidated / Expired |
| Weight marks | `.mx-cap--*` `.mx-mark--*` | Prophet weight grammar | Radar lifecycle, direction-neutral |
| Expert lanes | `.er-lanes` `.er-lane` | Prophet chips, not Groups | G0/C1/C2/C3/C5 + Best + All |
| C4 non-lane | `.er-lane--c4` `[data-role=stratification_only]` | — | Visible, not a fire, not a filter |
| Stale/degraded banner | `.er-banner` `[data-stale-banner]` | Prophet `.nb-stale-note` | Demotion disclosure |
| Card | `.pvcard` | Prophet `.pvcard` | One (ticker, expert) episode |
| Featured aura | `.pv-featured` | Prophet featured | Best-lane live candidate only |
| Hero spark / null | `.pv-chart` `.pv-nochart` | Prophet hero | 74px equalised; printed null |
| Lifecycle chip | `.er-lifechip` `.pv-axis` | Prophet stance chip + axis | Radar lifecycle, axis labelled |
| Expert chip | `.er-xchip` `[data-expert]` | Prophet marks | Exact expert id G0/C1/C2/C3/C5 |
| C2 variant chip | `[data-c2-variant]` | — | Inspectable variant, never a blend |
| C4 context chip | `.er-c4` `[data-expert=C4]` | — | Context / stratification only |
| Quote | `.pv-quote` `.nb-px` `.nb-chg` | Prophet quote | Price + change; em-dash if missing |
| Identity | `.pv-tk` `.pv-nm` | Prophet identity | Ticker + bilingual name |
| Priority slot | `.pv-pri` `[data-priority=accruing]` | Prophet Priority | ACCRUING — no number |
| Why line | `.er-why` | Prophet zone sentence | Mechanical why-candidate |
| False-start flag | `.er-fs` `[data-false-starts]` | — | History cannot disappear |
| Freshness footer | `.pv-zn` | Prophet zone footer | Freshness + as-of |
| Why drawer | `.er-drawer` `.er-drawer-btn` | Prophet caution popover | Ordered disclosure |
| Opportunity slot | `[data-opportunity=not_yet_measured]` | — | NOT YET MEASURED |
| Empty well | `.er-empty` `[data-empty]` | Prophet empty | Quiet is a state |
| Anon gate | `.mx-tier-gate` `[data-anon]` | Prophet anon | Honest copy, no levels |
| Harness | `.harness` | Prophet harness | Theme/lang/state only; hidden at `chrome=0` |
