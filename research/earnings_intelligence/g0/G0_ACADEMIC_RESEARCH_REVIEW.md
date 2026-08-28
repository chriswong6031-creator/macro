# G0 Academic Research Review

**Scope:** incremental information after earnings events. Not a trading model.  
**Rule:** a paper is `PRIMARY SOURCE VERIFIED` only if this session opened a publisher/IR/repository page. Training memory is `INFERRED`.

Opened this session:

- Erasmus Pure record for Matsumoto, Pronk, Roelofsen 2011 (abstract + DOI). PRIMARY SOURCE VERIFIED — https://pure.eur.nl/en/publications/what-makes-conference-calls-useful-the-information-content-of-man/
- RePEc / JSTOR pointers for Bernard & Thomas 1989. Title/venue PRIMARY SOURCE VERIFIED via https://ideas.repec.org/a/bla/joares/v27y1989ip1-36.html — **abstract body was empty on that page**.
- Fink 2021 PEAD review landing (ScienceDirect). PRIMARY SOURCE VERIFIED pointer — https://www.sciencedirect.com/science/article/pii/S2214635020303750
- Hollander, Pronk, Roelofsen “Does Silence Speak?” SSRN / JAR 2010 pointers. PRIMARY SOURCE VERIFIED as bibliographic records, not full text.

Full PDFs were not retrieved. Findings below use the opened abstracts/records plus explicit INFERRED flags.

---

## 1. Filings vs press release

| Paper | Year | Venue | Finding (as far as the opened record supports) | Tag | G0 state |
|---|---|---|---|---|---|
| Ball & Brown | 1968 | JAR | Earnings announcements move prices; the announcement is incremental to prior-year numbers. | INFERRED (canonical; PDF not opened) | `FULL_RELEASE` |
| Beaver | 1968 | JAR | Volume/volatility spike at earnings. | INFERRED | `FULL_RELEASE` / `FIRST_SESSION_CLOSE` |
| Li (MD&A tone / 10-K) | 2008–2010 family | various | Filing text carries incremental content beyond the earnings number. | INFERRED | `FILING_RECONCILED` |
| Levi / 10-Q vs 8-K literature | various | — | 10-Q/10-K arrive later and can revise the 8-K print (accruals, footnotes, segment notes). | INFERRED | `FILING_RECONCILED` |

**So what:** `FULL_RELEASE` ≠ `FILING_RECONCILED`. FIF exists precisely so CEI does not pretend the 8-K is the statement.

**Does not prove:** that our estate holds PIT 10-Q text for the flagship event. Live AAPL completeness `filing=bound` is an 8-K accession, not a statement packet.

---

## 2. Conference calls / prepared remarks

| Paper | Year | Venue | Finding | Tag | G0 state |
|---|---|---|---|---|---|
| Matsumoto, Pronk, Roelofsen | 2011 | *The Accounting Review* 86(4) 1383–1414. DOI 10.2308/accr-10034 | Sample >10,000 transcripts. **Both** presentation and discussion have incremental information over the accompanying press release. Discussion is relatively more informative; that gap rises with analyst following. When performance is poor, managers disclose more in the presentation, but relatively more information still comes out in discussion. | PRIMARY SOURCE VERIFIED (abstract on Pure) | `PREPARED_REMARKS` vs `QA_AVAILABLE` vs `FULL_RELEASE` |
| Bowen, Davis, Matsumoto | 2002 | family | Conference calls themselves are incrementally informative. | INFERRED | `PREPARED_REMARKS` |

**So what:** collapsing prepared remarks and Q&A into one `transcript: present` flag (live workspace) **discards the paper’s main split**. Digest chapters already distinguish `prepared` vs `q_and_a` lexically (`digest.py`); the workspace does not project that split.

**Does not prove:** that Q&A *caused* a price move in any named name. Incremental R² / abnormal return around the segment is not a mechanism ID.

---

## 3. Q&A / silence / analyst identity

| Paper | Year | Venue | Finding | Tag | G0 state |
|---|---|---|---|---|---|
| Hollander, Pronk, Roelofsen | 2010 | JAR 48(3) 531–563 | Open conference calls let researchers study whether managers withhold; silence is a disclosure choice. | PRIMARY SOURCE VERIFIED as bibliographic record (SSRN 1264966 / IDEAS) | `QA_AVAILABLE` |
| Mayew | 2008 | family | Managers discriminate among analysts on the call. | INFERRED | `QA_AVAILABLE` |

**So what:** a structured `qa_exchange.v1` needs speaker, role, and a first-class “no answer” / deflection — E0 ledger already marks non-answer as `NOT_BUILT`. Do not fill that with an LLM label (`DNR:KILL-LLM-FRAME-TAGS`).

---

## 4. Accounting changes / non-GAAP / accruals

| Paper | Year | Finding | Tag | G0 state |
|---|---|---|---|---|
| Bradshaw, Christensen, Gee, Whipple (non-GAAP family) | 2010s–2020s | Non-GAAP exclusions are incrementally used by the Street and can invert a GAAP miss. | INFERRED | `FULL_RELEASE` + basis |
| Doyle, Jennings, Soliman / Doyle, Lundholm, Soliman | family | Accruals / special items predict later disappointment; PEAD is stronger in the accrual tail. | INFERRED | `FILING_RECONCILED` |
| Freeze Q / Wire L3 (estate law) | 2026 | If `basis_match` is false, **no beat/miss**. | CODE VERIFIED | all states |

**So what:** “headline beat / deep weakness” is illegal to emit without a matched basis. Live AAPL already withholds. Bank / REIT / insurer golden-corpus classes exist so a generic EPS extractor cannot launder a basis error.

---

## 5. Guidance

| Paper | Year | Finding | Tag | G0 state |
|---|---|---|---|---|
| Bundled guidance / 8-K literature (Hsu et al. cited by `edgar_guidance.py`) | — | Guidance-language 8-Ks pull faster, larger revisions than the later consensus print. | INFERRED via collector docstring; Hsu PDF not opened | `HEADLINE_AVAILABLE` / `FULL_RELEASE` leads `ANALYST_REVISION_STATE` |
| Walk-down / range literature | family | Managers walk the Street down; range width is itself information. | INFERRED | `guidance_item.v1` status `raised\|cut\|withdrawn` |

**So what:** CEI already has `guidance_item.v1` (`low`, `high`, `status`). Live AAPL mints one introduced FY2026 Q4 revenue range from a transcript span. There is **no** prior comparable, so raise/cut cannot be computed. Thematic `edgar_guidance.py` is a **different owner** (theme universe phrase hits) and is not a CEI series.

---

## 6. Attention / information diffusion

| Paper | Year | Finding | Tag | G0 state |
|---|---|---|---|---|
| DellaVigna & Pollet | 2009 | Friday earnings get less immediate attention; more drift. | INFERRED | `FIRST_SESSION_CLOSE` vs later |
| Hirshleifer, Lim, Teoh | 2009 | Same-day earnings congestion reduces immediate response. | INFERRED | `FIRST_SESSION_CLOSE` |
| Peress / media | family | Coverage speeds incorporation. | INFERRED | attention leg (not CEI) |

**So what:** `session_phase` and a same-day congestion count are display context, not a calendar gate (`DNR:KILL-CALENDAR-GATED-RISK`).

---

## 7. Post-earnings drift and reversal

| Paper | Year | Venue | Finding | Tag | G0 state |
|---|---|---|---|---|---|
| Bernard & Thomas | 1989 | JAR 27 (Supplement) 1–36 | PEAD: delayed price response vs risk-premium debate. Title/venue verified on RePEc; abstract empty there. Fink 2021 review restates ~±2% over 60 trading days for good/bad news in B&T. | Title PRIMARY via RePEc; magnitude INFERRED via Fink landing page | after `FIRST_SESSION_CLOSE` |
| Bernard & Thomas | 1990 | family | Subsequent-announcement serial correlation. | INFERRED | later events, not this event’s frontier |
| Foster, Olsen, Shevlin | 1984 | family | SUE-sorted drift. | INFERRED | — |
| Livnat & Mendenhall | 2006 | family | Drift depends on the surprise definition (seasonal random walk vs analyst). | INFERRED | another reason `basis_match` is load-bearing |
| Fink | 2021 | review | Survey of PEAD evidence and explanations. | PRIMARY pointer | — |

**So what for G0:** PEAD is a **cross-sectional average**, not a per-event verdict. A single name’s 3/5/10d hold (winner-case G3) is a case geometry, not “PEAD confirmed.” CEI must not print “drift expected.” Stock-page PEAD copy already exists; do not rebuild it inside Earnings.

**Does not prove:** that live CEI can measure PEAD. Reaction is `not_joined`. SUE on the US stock-score edge is a **different program** and is out of scope (no Prophet change).

---

## 8. Mapping onto the G0 clock

| G0 state | Incremental-info claim the literature supports | What our estate can show today |
|---|---|---|
| `PRE_EVENT` | Anticipation / leakage / calendar attention | Calendar row only; unofficial |
| `HEADLINE_AVAILABLE` | First number moves volume (Beaver) | No headline object |
| `FULL_RELEASE` | PR is incrementally informative | AAPL Exhibit 99.1 bound; Wire still `not_ingested` |
| `PREPARED_REMARKS` | Presentation incrementally informative vs PR (MPR 2011) | Transcript present; chapter not on workspace |
| `QA_AVAILABLE` | Discussion **more** informative than presentation (MPR 2011) | `qa_exchanges: []`; digest markers only |
| `FILING_RECONCILED` | Footnotes / accruals / non-GAAP recon | FIF packet fixture; FIF-7 todo |
| `FIRST_SESSION_CLOSE` | Immediate abnormal return | `reaction_not_joined` |
| `ANALYST_REVISION_STATE` | Guidance and calls pull revisions | Unlicensed / accruing from 2026-06 |

---

## 9. Rights and reuse

Academic findings are citations, not data licenses. Transcript and filing **bodies** stay behind existing rights profiles. Golden-corpus prose is synthetic and must not be treated as a historical call.

---

## 10. Gaps (papers not opened)

Ball & Brown 1968 PDF; Beaver 1968; Bernard & Thomas 1989/1990 full text; DellaVigna & Pollet 2009; Hirshleifer, Lim, Teoh 2009; Livnat & Mendenhall 2006; Bradshaw et al. non-GAAP; Li 2010; Mayew 2008 full text; Price, Doran, Peterson, Bliss call-tone; Chen, Demers, Lev. A later pass should open those PDFs before any promotion-bearing claim.
