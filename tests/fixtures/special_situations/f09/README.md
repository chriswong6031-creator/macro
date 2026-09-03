# F09-1 precision corpus

`corpus.json` — 19 immutable cases for the deterministic deal-term extractor.

**Rights posture.** These excerpts are **authored** in canonical SEC merger / tender-offer
phrasing. They are deliberately NOT verbatim copies of any filing body: the operation forbids
committing production filing bodies, model caches or generated live data. Each case is bound to
a synthetic accession and, through `source_descriptor`, to the sha256 of its own bytes — so the
corpus is immutable, diffable, and a change to any excerpt changes every observation id derived
from it.

**What it proves and what it does not.** It proves *precision*: zero false precise numeric
publications, including on the hostile negatives (dividend, redemption price, exercise price,
aggregate value, conflicting values, per-ADS vs per-share). It does **not** measure real-world
recall against live EDGAR — that is only answerable on the natural production run, which is
gated behind macro#6783. See `research/F09_PREMIUM_MATH_PRECISION_REPORT_2026-09-03.md`.
