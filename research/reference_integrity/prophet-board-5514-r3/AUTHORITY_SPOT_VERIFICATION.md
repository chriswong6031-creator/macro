# Design-authority spot verification — RIG r3, artifact 6ad6b51b

Ran by the adjudicating authority against the frozen fixture and a real browser,
independently of both critics, before adjudicating any blocker. Method noted per row
because two of the checks are measurement-sensitive.

## CONFIRMED exactly

**PRC-303 — rank-1 card contradicts itself.** Fixture read of `GPCR`:
`verb="FRESH BUY"`, `trg="triggered"`, `star=true`, `life="entered"`, `entry=53.14`,
caution `"Already moving. Don't chase above the buy zone."` — while `stance="blocked_data"`
(renders "No read yet") and `zk="none"` (renders "No zone — stand aside"). The card denies
having a zone in the same breath as a caution that names the zone, on the board's ★Featured
rank-1 name. **5 rows** carry a verb under a `blocked_data` stance: GPCR, VSEC, DXYZ, AYI, CSR.

**PRC-306 — card-unreachable population.** Recomputed the union independently:
`GRID_CAP=40`; default live view + all seven lifecycle filters reach **102/179** rows as a
card; **77 rows (43%) can never render as a card in any state or filter.** Matches Reviewer A's
number exactly. Cell sizes: watch 0 · ready 62 · entered 95 · delivering 0 · overtime 0 ·
invalidated 2 · resolved 20.

**PRC-312 — vocabulary collision.** 27 rows are `life="entered"` with `stance="wait"`.

**PRC-304 — fabricated change values.** `demoChange(tk)` is literally
`h = (h*31 + charCodeAt) % 997` over the ticker string, mapped to −2.8%…+3.2%. Every change
value in every crop is a hash of the ticker, rendered in direction ink.

## CONFIRMED with a precision correction

**PRC-301 — card→detail navigation.** Substance holds: the card root is `<article>`
(board.js:286), cards emit `data-id` and never `id`, the only card href is
`href="#id=<plan>"` on the **2** rows carrying `newer` (board.js:388-389), and the only
`id=` attributes in the document are the five section anchors (board.js:791-795). No consumer
resolves `#id=`. **0 of 179 names route anywhere.**

*Correction to the receipt's wording:* `location.hash` IS present (board.js:804) — but it is
a **write** of the lifecycle filter (`location.hash = "life=" + k`), never a read. The claim
"nothing reads `location.hash`" is imprecise; the conclusion — that no hash consumer resolves a
plan id, so the link is inert — is correct. The finding stands on the corrected wording.

## CONFIRMED in ordering, refined in magnitude

**VTC-302 — chart-stroke salience inverted against actionability.** Verified by sampling
**rendered pixels** (playwright at DSF 2, modal-pixel backdrop, most-common far-from-backdrop
pixel as the ink) rather than by `getComputedStyle`, which does not reliably resolve
`color-mix()` on this path — my first attempt via computed style produced a spurious
`rgb(0,1,0)` for `--pv-buy` and had to be discarded.

| stance | dark contrast | light contrast |
|---|---|---|
| WAIT | **6.67** | 3.50 |
| NO-READ | 4.00 | **4.46** |
| BUY | **3.78** (lowest) | 3.66 |

`--pv-buy` resolves to `rgb(56,159,99)`, matching the hand-computed
`color-mix(in srgb, #45b873 80%, #063a24)`. The **ordering is inverted in both themes**: in
dark the loudest chart belongs to WAIT; in light the loudest belongs to a card carrying no
opinion at all. Reviewer B's absolute ratios differ from mine (B measured against the card
background, I measured against the chart's own tinted backdrop — the more local reference for
a stroke drawn on it); the finding is the ordering, and it holds under both references.

**Precision the verdict must carry:** BUY at 3.78 / 3.66 still clears the 3:1 WCAG threshold
for graphical objects. This is a **salience-ordering defect, not an accessibility violation**,
and must not be written up as the latter.

## Authority-originated finding

**DA-001 — the artifact violates a design principle its own notes record, without adjudicating
the reversal.** `DESIGN_NOTES` §C states "One universe, no view exemption — `paid` and `today`
render the same population." A later section of the same file states "`state=paid` renders the
plan rows the fixture can draw at full fidelity (33 today)… `state=today` is the honesty state…
**A 60%-`暂无判断` board must not become the flagship reference.**" The code at this SHA
implements §C: one universe, 179 rows, **97 (54%) carrying the no-read chip**. So the artifact
now ships precisely the board its own notes say must not become the flagship reference, and the
notes never adjudicate the reversal — they simply contain both statements. Put to both critics
at the pass-2 reveal rather than originated by the authority alone.
