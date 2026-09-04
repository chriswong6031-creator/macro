# XPV2-SC-R3B.1 — Fresh Critic Review: Data / Authority

**Reference:** `mastermind-xpv2-sector-r3b-1`
**Artifact:** `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`
**Bound sha256:** `fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70`
**Bound freeze commit:** `0667f800764bf210af6c1237ccf0b5f0a71b4af2`
**Governing document:** `research/reference_integrity/mastermind-xpv2-sector-r3b-1/COMMISSION.md`
**Seat:** Data / Authority (one of four fresh final critic seats, COMMISSION.md §"Final review")
**Verdict:** **PASS_WITH_CONDITIONS**

---

## 0. Seat, method, disclosures

### 0.1 Identity, independence, and RE-RUN status

**This is a RE-RUN seat.** A Data/Authority receipt for this exact SHA was produced earlier
in the cycle but exists only in a chat transcript and cannot be recovered as a durable
artifact. Under the governing commission's rule *"rerun only that missing critic; do not
fabricate provenance,"* this receipt is the lawful re-execution.

I had **no prior involvement** in the design, build, QA, orchestration or adjudication of
`mastermind-xpv2-sector-r3b-1`. I did not read, and could not read, the lost receipt. I did
not attempt to guess or reconstruct what the previous seat concluded. **Every finding, ID,
severity and attribution below is my own independent judgment**, reached from my own
rendering and my own producer tracing. Where my conclusions coincide with the R3B
predecessor receipt's numbering (`DAC-1xx`), that is because I read the predecessor receipt
in `research/reference_integrity/mastermind-xpv2-sector-r3b/reviews/data_authority.md`
in order to model this file's shape and to resolve continuity dispositions — a required
input, not a source of verdicts.

**Finding IDs in this receipt use the prefix `DA1-` (R3B.1 Data/Authority).** They do not
continue the predecessor's `DAC-` series. Where a `DA1-` finding is the surviving residue
of a predecessor `DAC-` item, that lineage is named explicitly.

### 0.2 Disclosed non-independence input

I read `research/reference_integrity/mastermind-xpv2-sector-r3b-1/ORCHESTRATOR_ADJUDICATIONS_R3B1.md`
before completing my producer tracing. That document self-discloses two conclusions inside
my seat's scope (the R3B1-06 residual, and the R3B1-13 resolution). **I treated both as
claims to be falsified, not as findings to be inherited**, and I re-derived each from the
producer code and the embedded fixtures myself. §3.1 and §3.2 record the independent
derivations. This disclosure exists so a later reader can discount the risk that I anchored
on the builder's own account.

### 0.3 Method

1. **SHA verification** — `shasum -a 256` on the artifact; `git cat-file -t` and
   `git rev-parse <commit>:<path>` on the declared freeze commit (§1).
2. **Fixture extraction** — the 22 embedded `<script type="application/json" id="ref-data-N"
   data-path="…">` payloads were parsed out with Python (never regex-grepped across the
   5.4 MB file) into a scratch directory outside `mockups/`.
3. **Rendering** — Chromium 151.0.7922.34 via Playwright, viewport 1440×1400, `file://`
   load. All six views were activated by clicking the real `.si-view-btn[data-view]`
   controls (not by injecting state), in **EN and then ZH** via the artifact's own
   `REF.setLang('zh')`. For each of the 12 cells I walked the `.si-stage` subtree and
   captured only text nodes whose parent was actually painted (`display!=='none'`,
   `visibility!=='hidden'`, no `hidden` attribute, `offsetParent!==null`). **Every label
   quoted in this receipt is painted text, not source text.**
4. **Producer tracing** — each challenged figure/label was traced to a field in the embedded
   fixture, and thence to the production contract in `engine/`, `scripts/` or `templates/`,
   cited by file and line.
5. **Console** — 0 console errors and 0 page errors across the full EN+ZH six-view sweep.

### 0.4 No repair work performed

I edited nothing. I did not run the build harness's mutation or inventory suites in a mode
that writes into `mockups/`. All scratch output went to a session scratch directory. See §8.

---

## 1. Artifact verification — PASS

| Check | Expected | Observed | Result |
|---|---|---|---|
| Candidate sha256 | `fec05b058fbc9dbe29744ad015b7ee9cd9baa5cb85bbbde739daa8b97644cf70` | identical | **PASS** |
| Freeze commit exists | `0667f800764bf210af6c1237ccf0b5f0a71b4af2` | object type `commit` | **PASS** |
| Candidate blob at freeze commit | — | `95981ada55ef60423503ba2056814d55eb5ba03c` | **PASS** |
| Candidate blob at review HEAD (`369d8a3c59e9`) | same blob | `95981ada55ef60423503ba2056814d55eb5ba03c` | **PASS — no post-freeze drift** |

Commands:

```
shasum -a 256 mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html
git cat-file -t 0667f800764bf210af6c1237ccf0b5f0a71b4af2
git rev-parse 0667f800764bf210af6c1237ccf0b5f0a71b4af2:mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html
git rev-parse HEAD:mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html
```

Note: `0667f800` is a merge commit (`Merge remote-tracking branch 'origin/main' into
claude/xpv2-sc-r3b1-build`, 2026-08-22 10:55:09 -0700). The reference landed on `main`
through squash-merge `780cbcf6d2d2` (PR #6248), which carries the identical blob. Both SHAs
in the commission are therefore correct and the artifact is unchanged since freeze.

---

## 2. Producer audit — what HOLDS (verified, not assumed)

These were attacked and survived. Recording them matters: several are the exact
restorations the fix packet commissioned, and a later seat should not re-litigate them.

**R3B1-01 — sizing directive. HOLDS.** Painted EN Overview: `positions sized to` / `81%`.
Producer `basketdata/baskets.json → theme_intel.regime_sizing`, embedded fixture values
`{"schema":"vol_regime.sizing.v2","gross_scalar":0.81,"active":true,…}`. The rendered 81%
is `gross_scalar` at the commission's stated fixture value; the `active:true` inert-guard
premise holds.

**R3B1-05 — hero enrichment counts. HOLDS, exactly.** Painted EN Overview:
`· 49 themes · 15 categories`. Measured against the fixture:
`len(theme_intel.themes) == 49`, and `len({t["category"] for t in theme_intel.themes}) == 15`.
Both counts are derivable from the payload and both are right. The outgoing/incoming
relative-performance context (`-9.6% 20d`, `+11.5% 20d`, `· climbing fast`) is present.

**R3B1-07 — the omission claim itself is now TRUE, and is MORE honest than production.**
Painted EN Confluence: `65` `of` `113` `subsectors have enough live data to time.` `48`
`are too thin to time and are omitted from the timed table.` Producer
`marketdata/subsector_confluence.json → coverage`:
`{"n_subsectors":113,"n_gateable":65,"n_thin":48,…}`. Critically, `len(payload["subsectors"]) == 65`
— the 48 thin groups are genuinely **absent** from the array the table renders from.
Production's own copy at `templates/subsectors.js:221-222` asserts the opposite
(`'… · ' + cov.n_thin + ' thin (listed in the table, not timed)'` / `'…（列于表内，不计时）'`),
which is **false against this payload**. The candidate corrected a real upstream lie. The ZH
twin is a native, semantically equivalent reconstruction, not a calque:
`113 个子行业中，65 个实时数据足够，可用于计时。另有 48 个数据过于稀疏，无法计时，未列入下方计时表。`

**R3B1-13 — SUSTAINED. The bare 0.xx is correctly identified and correctly labelled.**
Producer path: `marketdata/subsector_confluence.json → double_gated.double_buy[].combined_score`.
Contract: `engine/subsector_confluence.py:347` —
`"combined_score": round((m["stock_weight"] or 0.0) * sub_factor, 4)`, described at
`engine/subsector_confluence.py:323` as *"combined_score = stock cascade weight × …"*.
I verified the arithmetic against the embedded fixture rather than trusting the docstring:
- COIN: `stock_weight 1.0 × subsector_factor 0.6 = 0.6` → painted `0.60` ✔
- NSC: `stock_weight 0.9 × subsector_factor 0.6 = 0.54` → painted `0.54` ✔

The label `Conviction / 综合把握` is production's **own** header for this exact field at
`templates/subsectors.js:331`. It is not `Score`, `Probability`, `Confidence` or `Strength`,
so the commission's prohibition is satisfied by construction and no Sol return was owed.
*(Nit: ORCHESTRATOR_ADJUDICATIONS_R3B1.md §4 cites this as `templates/subsectors.js:330`;
line 330 is `}).join('');`. The correct citation is `:331`. Immaterial to the ruling.)*

**Bottoming Watch bare decimal — NOT a defect.** Painted `2.7 / 2.6 / 2.3` are unlabelled,
but each carries a real bilingual explanation on its own node
(`data-tip-en="Momentum is turning up from the low — a bigger number is a sharper turn. A
first hint, not a buy signal."`, `data-tip-zh` twin), and the strip is governed by a painted
footer: `All 3 rows: cycle turn signal — watch only · may be bottoming` and *"A forming low
on its own has not been shown to predict what comes next — watch, don't chase."* That is the
compliant plain-word-null-disclosure form. No charge.

**Display-only separation on Money — HOLDS.** Painted: *"Display-only context — volatility
regime from the conditions engine + CBOE put/call. Never scored, no forward claim."* This is
the correct pattern and is exactly what §3.3 below finds MISSING one band lower.

**Graded-vs-display labelling on Overview/Confluence — HOLDS.** `Graded call · this view only`
and `Display only — it does not set a lane below.` are both painted, correctly separated.

**Cardinality consistency — HOLDS.** Confluence tier chips `Entry now 1 · Tailwind 16 ·
Neutral 21 · Late 18 · Headwind 9` sum to **65**, matching the `S&P 500 65` universe chip,
matching `coverage.n_gateable`, matching `len(payload["subsectors"])`, matching the painted
`65 / 65` full-table counter and the painted 65 rendered `<tbody>` rows (measured in the
DOM). The headline `1 group just turned buyable and 16 more carry a tailwind` matches the
first two chips. No count drifts anywhere in this chain.

**EN/ZH numeric parity — HOLDS.** Every figure I checked paints identically in both
languages; the ZH view differs only in prose. Painted-node counts per view were identical
EN vs ZH to within one node (overview 105/106) — the delta is a language-conditional
separator, not a data claim.

---

## 3. Findings

### DA1-01 — MAJOR — One producer field is painted under two customer names on two views ("Score" and "Strength"); the commission's independence premise is FALSE

**Attribution: COMMISSION-INDUCED. Not candidate-invented; not upstream-caused.**
Lineage: this is the surviving residue of `mastermind-xpv2-sector-r3b::data_authority::DAC-107`.

The commission's R3B1-06 instructs: *"For `theme_intel.themes[].score`, use **Strength /
强度** in Overview-context and Map. **Do not rename the independent action-board score.**"*
My seat was directed to test that independence assertion rather than assume it. **I tested
it and it is false.**

Producer evidence (`scripts/build_site.py:1774-1785`), the action-board item constructor:

```
base_item = {
    "kind": "theme",
    …
    "score": th.get("score"),
```

`th` is the `theme_intel.themes[]` element. The action-board `score` is therefore a
**byte copy** of `theme_intel.themes[].score` for every `kind: "theme"` item, not a
separate producer field.

Fixture measurement — I cross-joined the embedded `basketdata/action_board.json` against the
embedded `basketdata/baskets.json → theme_intel.themes[]` on `ticker`:

```
theme items: identical score=33  differing=0  unmatched=0
 SAME buy_now    gold_miners     board.score=76  theme.score=76
 SAME buy_now    ai_agents       board.score=71  theme.score=71
 SAME buy_now    non_ai_software board.score=70  theme.score=70
 SAME on_the_run big_pharma      board.score=77  theme.score=77
 SAME on_the_run silver_miners   board.score=76  theme.score=76
```

**33 of 33 identical, zero differing.** There is no independent action-board score on this
fixture.

Rendered consequence, measured in the painted DOM of the frozen candidate:

| View | Painted column label | Painted value | Producer path |
|---|---|---|---|
| Overview, action board | `Score` (`评分`) | Gold Miners `76`, AI Agents `71`, Non-AI Software `70` | `theme_intel.themes[].score` (via `build_site.py:1784`) |
| The Map, selected-group panel | `Strength score` | Big Pharma `77` | `theme_intel.themes[].score` |
| The Map, text-equivalent table | `Strength` | Big Pharma `77`, Gold Miners `76` | `theme_intel.themes[].score` |

The same number — Gold Miners `76`, Big Pharma `77` — is presented to the customer as
**"Score"** on one view and **"Strength"** on another, inside one reference. A reader has no
way to know these are one measure, and the two names invite the inference that the action
board carries an independent, action-grade quantity that the Map's context surface does not.
It does not.

**Why this is not the candidate's defect.** The candidate did exactly what it was told: it
unified the *context* surfaces to Strength/强度 and left the action-board header alone,
because the commission explicitly forbade renaming it. The build lane also **disclosed** the
residual honestly (`ORCHESTRATOR_ADJUDICATIONS_R3B1.md` §4 ruling 1), which is the correct
behaviour when a fix packet's premise is wrong. Charging the candidate for obeying a binding
instruction would be the wrong incentive.

**Why it must still be charged.** The customer-visible harm is real, is present in the frozen
bytes, and is exactly the exposure `DAC-107` opened. R3B1-06 was written to close it and
closed only half of it, because the carve-out protects a field that does not need protecting.
The remedy is a one-line header change on the Overview action board (`Score / 评分` →
`Strength / 强度`), which is inside the frozen architecture and touches no production path.

**Condition C1 (below) requires Sol to rule**, because only Sol can amend its own carve-out.

---

### DA1-02 — MAJOR — Confluence paints "thin" for two different producer fields on one screen, and the two statements contradict each other

**Attribution: CANDIDATE-OWNED (promotion to visible text), on an upstream-owned string.**

The candidate's corrected R3B1-07 sentence is true (§2). But on the *same view*, the
candidate also paints a row-level chip reading **`Thin data — read with caution`** /
**`数据稀疏 — 请谨慎解读`**.

Measured in the painted DOM, Confluence view, EN, full table expanded:

- painted `Thin data — read with caution` nodes: **32**
- rendered `<tbody>` rows in the timed table: **65**

So the customer reads, in one scroll:

> `48 are too thin to time and are omitted from the timed table.`

…and then meets **32 rows inside that very table**, each stamped `Thin data`.

These are two different producer paths wearing one customer word:

| Customer word | Producer path | Fixture value | Meaning |
|---|---|---|---|
| "thin" (the 48) | `subsector_confluence.json → coverage.n_thin` | `48` | gate-dropped; **absent** from `payload.subsectors` |
| "Thin data" (the chips) | `subsector_confluence.json → subsectors[].reliability == "low"` | `Counter({'low': 31, 'med': 26, 'high': 8})` over the 65 | in-table low-confidence flag |

The two populations do not even overlap: the 48 are not in the array at all, and the 31/32
chipped rows are all inside `n_gateable`. The sentence and the chips are individually
producer-accurate and jointly incoherent.

**Why the promotion is candidate-owned.** Production never paints this string. At
`templates/subsectors.js:58`:

```
function relDot(rel) { … var lab = { high: 'High confidence — deep live coverage',
  med: 'Medium confidence', low: 'Thin data — read with caution' }[r];
  return '<span class="rel ' + r + '" title="' + lab + '"><i></i></span>'; }
```

Production renders a bare coloured dot and hides the wording in a `title=` attribute — a
hover affordance most customers never trigger, and one with no ZH twin at all. The candidate
promoted that hover string to persistent visible row text **and** authored a ZH twin for it.
That promotion is a genuine accessibility/i18n improvement and I do not want it reverted —
but it is the act that made the collision visible, and it happened on the very view whose
thin-coverage copy the commission had just ordered corrected. The candidate corrected the
sentence and then, one section down, undermined it.

**Remedy (inside the freeze, no production edit):** rename the row chip to the concept it
actually carries — reliability, not gateability. e.g. `Low confidence — few live members` /
`低置信度 — 实时成分少`, which also restores parity with the `high`/`med` rungs of the same
producer field and removes the word collision outright. Alternatively, qualify the sentence
so the two senses are explicitly distinguished. Either is a copy-only change.

*Overlap note (not adjudicated here):* whether a 32-instance repeated chip is the right
visual density on a 65-row table belongs to the Visual/Taste seat. I charge only the data
semantics.

---

### DA1-03 — MAJOR — "Forward track record: Validated" is painted over 21-day statistics whose own `proven` flag is `false`, with the producer's context-only caveat dropped

**Attribution: UPSTREAM-PRODUCER / PRODUCTION-TEMPLATE-OWNED, faithfully mirrored — but the
dropped caveat is the candidate's own omission relative to the payload it embeds.**

Painted, Money & Breadth, EN:

```
Forward track record: Validated
345 calls logged over 11 days
21d hit-rate: running 46% (24), coiling 57% (7)
```

Producer: `marketdata/index_leadership.json → track_record`. The embedded fixture reads:

```
"schema": "index_leadership.track_record.v1",
"is_context_only": true,
"n_snapshots": 345,
"n_days": 11,
"verdict": "validated",
"peak_ic": 0.1953,
"proven": { "5": true, "10": false, "21": false, "63": false },
"note": "Call-score IC is significant at the 5d horizon (measured). Context-only — informs the read, never sizes."
```

and at the 21-day horizon specifically:

```
"21": { "n_matured": 31,
        "by_stage": { "running": { "n": 24, "mean_fwd_rel": -0.023,  "hit_rate": 0.458 },
                      "coiling": { "n": 7,  "mean_fwd_rel": -0.0154, "hit_rate": 0.571 } },
        "running_ic": null, "running_ic_t_hac": null,
        "coiling_ic": null, "coiling_ic_t_hac": null }
```

Three separate authority problems, all visible on one line:

1. **Scope mismatch.** The badge word `Validated` derives from `verdict`, and the payload's
   own `proven` map says the claim holds at **5d only** (`"5": true`). The statistics painted
   immediately beside the badge are **21d**, where `proven` is **`false`** and where both
   IC fields are `null`. The horizon that *is* proven is never shown; the horizon that is
   shown is not proven. Nothing on the surface tells the reader these are different scopes.
2. **The badge sits over a sub-coin-flip, negative-drift cell.** `running` at 21d is
   `hit_rate 0.458` (painted as `46%`) on `n=24`, with `mean_fwd_rel -0.023`. A green
   `Validated` chip over "46% on 24 observations, negative mean forward relative return" is
   authority stronger than the payload supports. `coiling` is `n=7` — an honest-N of seven.
3. **The producer's own disclaimer is not painted.** `is_context_only: true` and the `note`
   *"Context-only — informs the read, never sizes"* are both in the embedded payload and
   neither reaches the screen. I probed for this directly: on the Money view,
   `/never sizes|Context-only/i.test(activeView.innerText)` returns **`false`**. This is
   notable because the candidate demonstrably knows the pattern — one band up on the *same
   view* it paints *"Display-only context … Never scored, no forward claim."* for the
   volatility block. The discipline was applied to the weaker claim and skipped on the
   stronger one.

**Why the label itself is upstream.** Production authors this badge, from this field, with
this wording, and pairs it with the same 21d horizon —
`templates/sector_central.html.j2:3460-3468`:

```
var vlab = tr.verdict === 'validated' ? L('Validated', '已验证') : …
var h = '<div class="lead-track"><span class="tr-badge" …>📊 ' + L('Forward track record','前瞻战绩') + ': ' + vlab + '</span> '
      + '<span class="tr-txt">' + L((tr.n_snapshots || 0) + ' calls logged over ' + days + …
var h21 = (tr.horizons || {})['21'];
```

The candidate reproduced production faithfully, including the defect. So the **badge-to-21d
pairing is an upstream production defect** and belongs on the R3C production-repair list,
not on the candidate's ledger. What *is* fairly charged to the candidate is item (3): the
payload it embeds carries an explicit `is_context_only` flag and an explicit context-only
note, and the reference chose not to surface either, on a view where it surfaces exactly that
caveat for a lesser claim 2,400 painted nodes earlier.

**House-law note (advisory, not a charge).** `scripts/check_validated_claims.py` gates the
tokens `validated` / `已验证` on user-facing surfaces, backing them only via
`data/regime/validated_claims_allowlist.json` or a referenced artifact with top-level
`validated == true`. Here the flag is `track_record.verdict == "validated"` — nested, not
top-level. The gate scans `templates/`, `site/*.js`, generated `*_data.js` and `engine/`
copy; `mockups/` is outside its scan set, so the reference does not fail CI today. But if
this composition is ever promoted to a production template it will need an allowlist entry
naming the 5d evidence, and the scope mismatch in (1) is precisely what that allowlist is
designed to force into the open.

---

### DA1-04 — MINOR — The Map's per-gate `validated` chip is producer-backed but is the third distinct customer meaning of "validated" in one reference

**Attribution: UPSTREAM-PRODUCER-OWNED (field value), candidate-owned presentation choice.**

The Map paints a three-rung authority taxonomy per reasoning row, e.g.:

```
Cycle state   Prime entry — position 14/100 · turn signal BUY   validated
Trend gate    below its own 200-day trend / +1% 12m …           validated
Regime gate   Risk-on (MRS 0.29, …) → gate ×0.57 · cyclical (β+) validated
Momentum      RS 21d #9 · 63d #11 …                             confirmer
Heat          breadth 73.0% adv · -1.6% 1M (cap-wt)             display
```

DOM: `<span class="r3-chaintier"><span class="l-en">validated</span><span class="l-zh">已验证</span></span>`,
**33 painted instances** on the Map view.

The chip **is** producer-backed — I traced it to `sectordata/sector_central.json →
sectors[].reasoning[].tier`, whose values across the fixture are `validated` (181), `confirmer`
(60), `display` (19). So the word is the producer's own tier name and the reference did not
invent it. The graded/display separation this taxonomy expresses is exactly what my seat wants
to see, and it is correct.

The residual concern is lexical, not factual: within one reference the token "validated"
now carries **three** unrelated meanings — the gate-tier taxonomy here (§DA1-04), the forward
track-record verdict on Money (§DA1-03), and `build_site.py:1793`'s
`"validated": reco in ("trim","avoid")` which is a *risk-side* flag, not an evidence claim.
A reader who learns the word on the Map will carry the wrong prior to Money. I record this
as MINOR and **upstream** — no producer name is the reference's to change — and recommend it
join the R3C producer-side naming item already opened for the `Conviction` collision
(`ORCHESTRATOR_ADJUDICATIONS_R3B1.md` §4 ruling 3).

---

### DA1-05 — NIT — "All subsectors 65" is a false universal, and is production's own

**Attribution: UPSTREAM-PRODUCER-OWNED. No candidate action.**

Painted: `All subsectors` / `65` / `65 / 65`, on a view that has just told the reader there
are `113` subsectors. Source is production's own header at `templates/subsectors.js:493`:
`L('All ' + noun[0], '全部' + noun[1]) … <span class="n">' + groups.length + '</span>`, where
`groups` is the 65-element gateable array. Recorded for the R3C production-repair list only.
The candidate's corrected R3B1-07 sentence sits directly above it and does most of the work
of defusing it, which is why this is a nit and not a finding.

---

## 4. Attribution summary

| ID | Severity | Owner | Basis for attribution |
|---|---|---|---|
| DA1-01 | MAJOR | **Commission-induced** | Candidate obeyed an explicit R3B1-06 prohibition; the prohibition's independence premise is falsified by `build_site.py:1784` + 33/33 fixture identity |
| DA1-02 | MAJOR | **Candidate** | Production hides the string in `title=` (`subsectors.js:58`); the candidate promoted it to visible text, creating the collision |
| DA1-03 | MAJOR | **Upstream** (badge/21d pairing, `sector_central.html.j2:3460-3468`) + **Candidate** (dropped `is_context_only` / `note`) | Production authors the same pairing; the caveat exists in the embedded payload and is not painted |
| DA1-04 | MINOR | **Upstream** | Tier values are producer bytes (`sectors[].reasoning[].tier`) |
| DA1-05 | NIT | **Upstream** | `templates/subsectors.js:493` |

---

## 5. Verdict and conditions

**PASS_WITH_CONDITIONS.**

The reference's data authority is, on the whole, in good order. Every figure I traced resolved
to a real producer field; counts and cardinalities are internally consistent to the row;
EN/ZH numeric parity holds; the graded-vs-display separation is explicit and correct on the
surfaces that carry it; R3B1-01, R3B1-05, R3B1-07 and R3B1-13 all verify against the payload;
and the R3B1-07 repair is materially **more** honest than the production copy it replaces.
Nothing I found is a fabricated number or an invented measure. That is why this is not a BLOCK.

It is not a clean PASS because three customer-visible authority defects survive in the frozen
bytes, two of which the reference could close with copy-only edits inside the frozen
architecture.

**C1 (blocks a clean PASS; Sol must rule) — DA1-01.** R3B1-06's carve-out rests on a false
premise. Sol should either (a) amend R3B1-06 to permit the Overview action-board header to
become `Strength / 强度`, closing `DAC-107` outright, or (b) affirm the carve-out and accept
the one-measure-two-names exposure as a recorded, standing residual. **This seat cannot
resolve it** — the instruction is Sol's, and the candidate's compliance was correct.

**C2 (candidate-owned; copy-only) — DA1-02.** Re-label the row-level reliability chip so it
stops sharing the word "thin" with the gate-drop count. Keep the visible-text promotion and
the ZH twin.

**C3 (candidate-owned; copy-only) — DA1-03 item (3).** Paint the producer's own context-only
disclosure next to the `Validated` badge, using the pattern the same view already uses for the
volatility block. Optionally name the badge's horizon (`validated at 5d`) so the badge and the
adjacent 21d figures stop reading as one claim.

**R3C production-repair candidates (record only, do not implement here):** DA1-03 items (1)
and (2) (`sector_central.html.j2:3460-3468` badge/21d scope mismatch); DA1-04 (the tri-valent
"validated" token); DA1-05 (`All subsectors` false universal); and the pre-existing
`templates/subsectors.js:221-222` "listed in the table" falsehood, which this reference has
now *proved* wrong against a real payload and which still ships to customers on production.

---

## 6. Limitations / NOT_EVALUABLE

Stated plainly so a later seat knows what this receipt does **not** cover.

1. **Re-run seat, lost predecessor.** The earlier Data/Authority pass on this SHA is
   unrecoverable. I did not read it and made no attempt to reproduce it. If it raised a
   finding I did not independently rediscover, that finding is **not** captured here. This
   receipt should be read as *a* complete Data/Authority pass, not as a merge of two.
2. **Coverage is deep-but-not-exhaustive.** I traced every figure on Overview, the Map's
   selected-group panel and text-equivalent table, Confluence in full, and the Money
   track-record and volatility blocks. I did **not** individually trace every one of the
   ~2,490 painted nodes on Money (the heatmap treemap and its table equivalent, the full
   flow fragment) nor every row of Explore's 1,476-name scan. Absence of a finding on those
   surfaces is not evidence of their correctness.
3. **Fixture-bound only.** Every conclusion holds for the embedded frozen fixtures. Fields
   that are `null`/absent on this fixture but populated in live production (e.g. Baskets
   `gateable`/`thin`, which the commission notes the producer lacks) were not exercisable.
   `is_context_only`, `proven` and `verdict` were evaluated at their frozen values only.
4. **`data/` is sparse in this worktree** (`config/sparse_worktree.json` omits `data/`), so
   `data/regime/validated_claims_allowlist.json` was not read. My house-law note in DA1-03 is
   therefore advisory: I confirmed the gate's *logic* from `scripts/check_validated_claims.py`
   but did not confirm the current allowlist contents. This does not affect the finding, which
   rests on the payload's own `proven` map, not on the allowlist.
5. **I did not execute the build harness suites.** `verify_reference.py`, `inventory_check.py`,
   `mutation_suite.py`, `zoom_sweep.py`, `contrast_audit.py` and `lang_probe.py` were read for
   method but not run, to guarantee zero writes under `mockups/`. Their pass/fail claims in
   `ORCHESTRATOR_ADJUDICATIONS_R3B1.md` are **unverified by this seat** — including the
   R3B1-14 bidirectional-inventory claim, which is a completeness gate and is squarely the
   kind of thing a Data/Authority seat would otherwise want to falsify. A later seat should
   treat R3B1-14 as unaudited.
6. **Out of scope by commission, noted not adjudicated:** visual taste and density (the
   32-instance chip repetition in DA1-02), mobile geometry, and product feature regression.
7. **Rendering conditions:** Chromium 151.0.7922.34, 1440×1400, dark theme default, `file://`,
   0 console/page errors. I did not sweep light theme or narrow viewports for data claims;
   no data binding I inspected is theme- or width-conditional, but I did not prove that
   exhaustively.

---

## 7. Statement of non-modification

I created exactly one file: this receipt. I did not modify the candidate bytes, `build/`,
any fixture, `manifest.yml`, `baseline.yml`, `continuity.yml`, `proposal.yml`, any production
path, or any `approval.yml`. I issued no approval and no self-verdict beyond this seat's own
`PASS_WITH_CONDITIONS`. All harness/scratch output was written to a session scratch directory
outside the repository. `git status --porcelain` shows only this file.

## 8. Evidence index

- Candidate: `mockups/refs/reference_integrity/mastermind-xpv2-sector-r3b-1/proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html` @ `fec05b05…`, freeze `0667f800…`, blob `95981ada…`
- Producer contracts cited: `scripts/build_site.py:1774-1793`; `engine/subsector_confluence.py:323,347,357`;
  `templates/subsectors.js:58,221-222,331,493`; `templates/sector_central.html.j2:3460-3468`;
  `scripts/check_validated_claims.py` (module docstring, backing rules (a)/(b))
- Fixtures read from the artifact's own embedded registry (`ref-data-0` … `ref-data-21`),
  notably `basketdata/action_board.json`, `basketdata/baskets.json`,
  `marketdata/subsector_confluence.json`, `marketdata/index_leadership.json`,
  `sectordata/sector_central.json`
- Painted-text capture: six views × EN/ZH, Chromium 151.0.7922.34 @ 1440×1400, via the
  artifact's own `.si-view-btn[data-view]` controls and `REF.setLang('zh')`
