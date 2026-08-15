# State inventory — Live Entry Radar W8 fixtures

All fixtures are synthetic (`synthetic: true`). Query `?state=<id>`.

| State id | What it proves | Expert | Lifecycle | Freshness / bar |
|---|---|---|---|---|
| `quiet` | No candidates; empty well; not a broken page | — | — | — |
| `g0` | G0-only nightly confirmed grey dot | G0 | candidate | nightly · confirmed |
| `c1` | C1 1D LIVE provisional; first arm is candidate; C4 context chip | C1 | candidate | 1D LIVE · provisional |
| `c2` | C2 candidate; variant `c2a_kd_cross` inspectable | C2 | candidate | 1D LIVE · provisional |
| `c3` | C3 confirmed 4H — not provisional | C3 | candidate | confirmed 4H |
| `c5` | C5 watch / event-bound; pre-candidate | C5 | pre_candidate | event-bound |
| `multi` | Same ticker `FIX.MANY` on G0 + C1 + C2 as **three cards** | G0, C1, C2 | mixed | mixed |
| `expired` | Expired episode retained | C1 | expired | expired |
| `invalidated` | Invalidated false start retained | C2 / c2b | invalidated | invalidated |
| `history` | Live C1 plus two prior false starts on the card | C1 | candidate | 1D LIVE · provisional |
| `stale` | Stale demotion; no featured / no live-candidate look | C1 | candidate | STALE · 14m |
| `unavailable` | Unavailable ≠ non-fire; C2f ATR missing | C2 / c2f | probing | UNAVAILABLE |
| `raw` | Raw/adjusted basis refusal; whole observation null | C1 | probing | UNAVAILABLE · basis |
| `degraded` | Evaluator degraded banner + demoted card | C3 | pre_candidate | DEGRADED |
| `partial` | Missing change / spark printed as unavailable | C5 | probing | partial |
| `board` | Many-candidate mix (default) | mixed | mixed | mixed |
| `anon` | Honest gate; no entry/target/void; no win probability | — | — | — |
| `ipo` | IPO-cohort fixture in the Probe Set (P-6) | C1 | candidate | 1D LIVE · provisional |
| `lobe` | Lobe-only probe — not yet armed | C5 | probing | event-bound |

Required crop states (brief): no candidates (`quiet`); many (`board`); stale/degraded (`stale`, `degraded`); multi-expert (`multi`); false start / invalidated (`invalidated`, `history`); partial/unavailable (`partial`, `unavailable`, `raw`).
