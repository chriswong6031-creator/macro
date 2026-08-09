# Wave 9D review record — reviewed defense19 recipient graph (PUBLISHED 2026-08-08)

**This is the review record for a graph that IS published.** Everything below the
horizontal rule is the proposer's worksheet reproduced verbatim, so its own
`awaiting_analyst_review` state and its "nothing here is published" line describe
the state at *proposal* time (2026-08-07), not now. This header is the publication
act; the body is the evidence it was taken against.

The sibling `RECIPIENT_GRAPH_REVIEW_2026-08-08_defense19.json` is the same
worksheet in machine-readable form, likewise byte-verbatim: its
`review_state: awaiting_analyst_review` and `candidate_graph_is_unpublished: true`
are the proposer's 2026-08-07 assertions, preserved rather than edited so the
record stays a faithful account of what review was performed against. This file is
the authority on publication state for both.

| | |
|---|---|
| Published graph id | `recipient-graph:reviewed:2026-08-08:defense19-v1` |
| Canonical path | `data/government_revenue/recipient_entity_graph.json` |
| Publisher | `scripts/curate_government_revenue_recipient_graph.py` (admission `status=ready`, `error_codes=[]`) |
| Graph digest | `2ffa5dceb60ae13ed9ee0eda6bd2d8db4e55012ca3d9d876e5c7b7f7762cc537` |
| Proposer run | 2026-08-07T12:00:00Z, candidate id `recipient-graph:candidate:2026-08-07:defense` |
| Proposer lineage | tool shipped and adversarially reviewed through the PR #4906 lineage (EX-21 picker heal) |
| Operator approval | 2026-08-08, verbatim: "yes publish wave 9d candidate" |
| Coverage | 1 reviewed issuer (PLTR) → **19** (AVAV BA CW GD HEI HII HWM IRDM KTOS LDOS LHX LMT NOC PLTR RTX TDG TDY TXT VSAT) |
| Rows | 19 companies · 101 legal entities · 203 identifiers · 241 evidence · 101 ownership edges · 0 blocks/conflicts/overrides |

## What the review act covers, precisely

The operator approved publication of this candidate as a whole. `verification_state:
reviewed` on all 665 rows is therefore an assertion made at the level of the
method and the artifact — the proposer's exact-identity join, its normalization
rules, its award-receipt rule, and the per-edge evidence reproduced below — not a
record that each of the 203 identifier edges was separately opened and read.
Anyone tightening a downstream claim on a single edge should open that edge's
cited evidence URLs here first.

The method admits no fuzzy path: discovery ticker, name similarity, substring
containment, web snippets, and LLM assertion are all excluded by construction, and
every cited award record must itself contain the UEI it is cited for. That is what
makes artifact-level approval meaningful rather than a rubber stamp.

## What was changed between candidate and published bytes

Exactly one top-level key: `graph_id`, re-minted from
`recipient-graph:candidate:2026-08-07:defense` to
`recipient-graph:reviewed:2026-08-08:defense19-v1`. Every other byte of the
candidate — all 665 rows (19 + 101 + 203 + 241 + 101), every
`known_at` / `valid_from` / `valid_to`, every evidence record — is untouched.

`graph_known_at` and `graph_effective_at` deliberately remain the candidate's own
`2026-08-07T12:00:00+00:00`: that is the instant the evidence was retrieved and
the instant every row in the graph is stamped. They are **not** the wall-clock
publication instant, because `build_candidate_queue` joins the graph at
`latest.json["as_of"]` end-of-day (`engine/government_revenue/candidates.py:939`,
`:943`), and a graph-level knowledge clock ahead of that analysis clock trips the
fail-closed `future_known_graph` guard and withholds the ENTIRE graph. Measured
both ways against the live 2026-08-07 generation:

| `graph_known_at` | `recipient_graph_status` | `reviewed_issuer_company_count` |
|---|---|---|
| `2026-08-07T12:00:00Z` (evidence instant, shipped) | `ready` | **19** |
| `2026-08-08T11:57:07Z` (wall-clock publish instant) | `invalid` | **0** |

The publication act is recorded by the `graph_id`, by this record, and by the
commit — never by forward-dating a join clock past the data it must join against.

## Two issuers carry no proposed edge — both are finished answers

| Ticker | Reason code | What it means |
|---|---|---|
| `GE` | `no_exact_match` | 100 collected rows in discovery scope, 69 EX-21 names extracted, and not one collected recipient name equals the registrant or any subsidiary under the documented normalization. The collected recipients are other companies. |
| `BWXT` | `no_collected_recipients` | The collected USAspending panel holds zero rows for this issuer's discovery scope. An upstream COLLECTION gap, not a matching gap — nothing was available to join against. |

Neither is an outstanding mapping task. These two are the whole remainder: the
mapping backlog holds 21 rows, of which exactly these 2 sit at
`mapping_state=mapping_needed`. The other 19 rows are the reviewed issuers at
`mapping_state=partial_identifier_coverage` — identifier-linked, but their
collected discovery scope is not complete. That is coverage reporting, not an
unmapped issuer, and it is why the backlog row count stays 21 while reviewed
issuer coverage goes 1 → 19.

## Relationship to the previously published graph

The candidate re-derives PLTR from its own evidence rather than carrying the
2026-08-03 rows forward, so the published PLTR row identities changed
(`legal:pltr-technologies-inc` → `legal:pltr:palantir-technologies-inc`, and
likewise for its identifier, ownership, and evidence ids). The mapping itself is
preserved: both previously published UEIs (`FSY4LVSBGWB7`, `HNN4F9JZWDY8`) are
present with the same namespace, value, `valid_from`, canonical names, and
ownership shape, and `HNN4F9JZWDY8` still resolves to `central:PLTR`. A naive
union of the old and new rows was tested and is inadmissible
(`ambiguous_exact_identifier_path`: one UEI under two entity ids), which is why
the coherent reviewed artifact replaces rather than unions.

---

# Recipient entity graph — CANDIDATE for analyst review

**Review state:** `awaiting_analyst_review` · **candidate graph id:** `recipient-graph:candidate:2026-08-07:defense`

Nothing here is published. The canonical graph (`data/government_revenue/recipient_entity_graph.json`) is untouched and is written only by `scripts/curate_government_revenue_recipient_graph.py`.

- Issuers requested: **21** · with proposed edges: **19** · without: **2**
- Proposed identifier edges: **203** · withheld identifiers: **0** · documents fetched: **288**

## How a proposed edge was derived

- Ticker identity: SEC company_tickers.json (ticker -> CIK)
- Issuer documents: latest 10-K primary document + its EX-21 exhibit
- Recipient names: collected USAspending award panel (recipient_name + recipient_uei)
- Join: exact equality of normalized legal names
- Award receipt: the fetched award record must itself contain the UEI it is cited for
- Discovery ticker: scope selection and review metadata only; never a condition for an edge

Normalization, in full:

1. Unicode NFKC, then lowercase.
1. Every character outside [a-z0-9&] becomes a space; runs of spaces collapse.
1. Corporate-form spelling only: incorporated->inc, corporation->corp, company->co, limited->ltd.
1. A single leading article 'the' is dropped when at least one token remains.
1. Nothing else. No edit distance, no token-set overlap, no substring containment, no similarity score.

Never used: discovery_query_ticker, fuzzy or approximate name similarity, web-search snippets, LLM assertion.

## Proposed edges

### AVAV → `HE86H1JJJTK5`

- SEC name (ex21_subsidiary): **BlueHalo, LLC**
- SEC document: `avav-20260430xex21d1.htm`
- USAspending recipient name(s): **BLUEHALO LLC**
- Normalized join key: `bluehalo llc`
- Discovery ticker on the matched rows: AVAV
- Graph rows: `legal:avav:bluehalo-llc` · `identifier:avav:he86h1jjjtk5` · `ownership:avav:bluehalo-llc`
- Evidence:
    - `evidence:avav-sec-ex21` (SEC, official_filing, 12265 bytes, sha256 `0bd04717c93892af…`) https://www.sec.gov/Archives/edgar/data/1368622/000110465926078906/avav-20260430xex21d1.htm
    - `evidence:avav-usaspending-he86h1jjjtk5` (USAspending.gov, official_award, 6774 bytes, sha256 `756e33a62044fae4…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA239424FB005_9700_FA239424DB001_9700/

### AVAV → `MWKWXVSSC518`

- SEC name (sec_registrant): **AeroVironment Inc**
- SEC document: `avav-20260430x10k.htm`
- USAspending recipient name(s): **AEROVIRONMENT, INC**
- Normalized join key: `aerovironment inc`
- Discovery ticker on the matched rows: AVAV
- Graph rows: `legal:avav:aerovironment-inc` · `identifier:avav:mwkwxvssc518` · `issuer-identity:avav:aerovironment-inc`
- Evidence:
    - `evidence:avav-sec-10k` (SEC, official_filing, 4303986 bytes, sha256 `535f568a5df774c1…`) https://www.sec.gov/Archives/edgar/data/1368622/000110465926078906/avav-20260430x10k.htm
    - `evidence:avav-usaspending-mwkwxvssc518` (USAspending.gov, official_award, 6370 bytes, sha256 `54dd6a28f99cb22f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA862926FB002_9700_FA862926DB001_9700/

### AVAV → `P9MYM1427519`

- SEC name (sec_registrant): **AeroVironment Inc**
- SEC document: `avav-20260430x10k.htm`
- USAspending recipient name(s): **AEROVIRONMENT INC**
- Normalized join key: `aerovironment inc`
- Discovery ticker on the matched rows: AVAV
- Graph rows: `legal:avav:aerovironment-inc` · `identifier:avav:p9mym1427519` · `issuer-identity:avav:aerovironment-inc`
- Evidence:
    - `evidence:avav-sec-10k` (SEC, official_filing, 4303986 bytes, sha256 `535f568a5df774c1…`) https://www.sec.gov/Archives/edgar/data/1368622/000110465926078906/avav-20260430x10k.htm
    - `evidence:avav-usaspending-p9mym1427519` (USAspending.gov, official_award, 6077 bytes, sha256 `e189866d1996c962…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W31P4Q17C0193_9700_-NONE-_-NONE-/

### AVAV → `PN69XPUMA243`

- SEC name (sec_registrant): **AeroVironment Inc**
- SEC document: `avav-20260430x10k.htm`
- USAspending recipient name(s): **AEROVIRONMENT, INC.**
- Normalized join key: `aerovironment inc`
- Discovery ticker on the matched rows: AVAV
- Graph rows: `legal:avav:aerovironment-inc` · `identifier:avav:pn69xpuma243` · `issuer-identity:avav:aerovironment-inc`
- Evidence:
    - `evidence:avav-sec-10k` (SEC, official_filing, 4303986 bytes, sha256 `535f568a5df774c1…`) https://www.sec.gov/Archives/edgar/data/1368622/000110465926078906/avav-20260430x10k.htm
    - `evidence:avav-usaspending-pn69xpuma243` (USAspending.gov, official_award, 6364 bytes, sha256 `43293f602cff5c49…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002422F6200_9700_N0002421D6200_9700/

### AVAV → `YJG1MDHLBC88`

- SEC name (sec_registrant): **AeroVironment Inc**
- SEC document: `avav-20260430x10k.htm`
- USAspending recipient name(s): **AEROVIRONMENT, INC.**
- Normalized join key: `aerovironment inc`
- Discovery ticker on the matched rows: AVAV
- Graph rows: `legal:avav:aerovironment-inc` · `identifier:avav:yjg1mdhlbc88` · `issuer-identity:avav:aerovironment-inc`
- Evidence:
    - `evidence:avav-sec-10k` (SEC, official_filing, 4303986 bytes, sha256 `535f568a5df774c1…`) https://www.sec.gov/Archives/edgar/data/1368622/000110465926078906/avav-20260430x10k.htm
    - `evidence:avav-usaspending-yjg1mdhlbc88` (USAspending.gov, official_award, 6714 bytes, sha256 `5fb7c65057aca40b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0015_9700_W31P4Q11D0032_9700/

### AVAV → `ZVG6XCZMY1H6`

- SEC name (ex21_subsidiary): **Arcturus UAV, Inc.**
- SEC document: `avav-20260430xex21d1.htm`
- USAspending recipient name(s): **ARCTURUS UAV, INC**
- Normalized join key: `arcturus uav inc`
- Discovery ticker on the matched rows: AVAV
- Graph rows: `legal:avav:arcturus-uav-inc` · `identifier:avav:zvg6xczmy1h6` · `ownership:avav:arcturus-uav-inc`
- Evidence:
    - `evidence:avav-sec-ex21` (SEC, official_filing, 12265 bytes, sha256 `0bd04717c93892af…`) https://www.sec.gov/Archives/edgar/data/1368622/000110465926078906/avav-20260430xex21d1.htm
    - `evidence:avav-usaspending-zvg6xczmy1h6` (USAspending.gov, official_award, 6591 bytes, sha256 `2648ed94ff3b25be…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0003_9700_H9222217D0010_9700/

### BA → `E466BXU4KJH8`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:e466bxu4kjh8` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-e466bxu4kjh8` (USAspending.gov, official_award, 6827 bytes, sha256 `c655b69724dfa044…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0001_9700_W58RGZ04G0023_9700/

### BA → `H1C4ZVECADM6`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:h1c4zvecadm6` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-h1c4zvecadm6` (USAspending.gov, official_award, 6417 bytes, sha256 `e50976f2fe8d6669…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA821415C0001_9700_-NONE-_-NONE-/

### BA → `HLWWEH2CCXW5`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:hlwweh2ccxw5` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-hlwweh2ccxw5` (USAspending.gov, official_award, 6258 bytes, sha256 `b939aefef33bef90…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_NAS1510000_8000_-NONE-_-NONE-/

### BA → `JJM4FRDZJDX1`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:jjm4frdzjdx1` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-jjm4frdzjdx1` (USAspending.gov, official_award, 6571 bytes, sha256 `536560a5443333b0…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA821317F1001_9700_FA821315D0002_9700/

### BA → `LAJJQWA1PF31`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:lajjqwa1pf31` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-lajjqwa1pf31` (USAspending.gov, official_award, 5850 bytes, sha256 `f0b65f73abca0fff…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W58RGZ05C0274_9700_-NONE-_-NONE-/

### BA → `M25AW7P5S7K7`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:m25aw7p5s7k7` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-m25aw7p5s7k7` (USAspending.gov, official_award, 6552 bytes, sha256 `76cc89ede8a4ae20…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA810616C0001_9700_-NONE-_-NONE-/

### BA → `M6BRZ1FHEZQ1`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:m6brz1fhezq1` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-m6brz1fhezq1` (USAspending.gov, official_award, 6178 bytes, sha256 `408d2b984c7e89b6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA880725CB006_9700_-NONE-_-NONE-/

### BA → `M8JLMEHJADQ5`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:m8jlmehjadq5` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-m8jlmehjadq5` (USAspending.gov, official_award, 6465 bytes, sha256 `97292a4b14d0d821…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0005_9700_FA852612D0001_9700/

### BA → `MF2LE5RK6L84`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:mf2le5rk6l84` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-mf2le5rk6l84` (USAspending.gov, official_award, 6290 bytes, sha256 `9084ac56532599dc…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA850512C0001_9700_-NONE-_-NONE-/

### BA → `NJVNVWQJMPA4`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:njvnvwqjmpa4` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-njvnvwqjmpa4` (USAspending.gov, official_award, 6362 bytes, sha256 `a3ff59876b8156ba…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W58RGZ19C0024_9700_-NONE-_-NONE-/

### BA → `SML4NN2CT556`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:sml4nn2ct556` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-sml4nn2ct556` (USAspending.gov, official_award, 6565 bytes, sha256 `2b08e1abdc9137fd…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_80MSFC20C0052_8000_-NONE-_-NONE-/

### BA → `UEGFHX6R6KJ1`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:uegfhx6r6kj1` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-uegfhx6r6kj1` (USAspending.gov, official_award, 6366 bytes, sha256 `abdad73b09a3ca3e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0006_9700_FA861406D2006_9700/

### BA → `WZWRLY4G3PL8`

- SEC name (sec_registrant): **BOEING CO**
- SEC document: `ba-20251231.htm`
- USAspending recipient name(s): **THE BOEING COMPANY**
- Normalized join key: `boeing co`
- Discovery ticker on the matched rows: BA
- Graph rows: `legal:ba:boeing-co` · `identifier:ba:wzwrly4g3pl8` · `issuer-identity:ba:boeing-co`
- Evidence:
    - `evidence:ba-sec-10k` (SEC, official_filing, 3439474 bytes, sha256 `5e6dd009813c7851…`) https://www.sec.gov/Archives/edgar/data/12927/000162828026004357/ba-20251231.htm
    - `evidence:ba-usaspending-wzwrly4g3pl8` (USAspending.gov, official_award, 6385 bytes, sha256 `7a397b8e1b4ce051…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0026_9700_F1962801D0016_9700/

### CW → `HLQLWMV97J37`

- SEC name (ex21_subsidiary): **Curtiss-Wright Electro-Mechanical Corporation**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT ELECTRO-MECHANICAL CORP**
- Normalized join key: `curtiss wright electro mechanical corp`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-electro-mechanical-corp` · `identifier:cw:hlqlwmv97j37` · `ownership:cw:curtiss-wright-electro-mechanical-corp`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-hlqlwmv97j37` (USAspending.gov, official_award, 6108 bytes, sha256 `2bb88523fe1a8d3d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010424PJA32_9700_-NONE-_-NONE-/

### CW → `JKZNKGGWYZ87`

- SEC name (ex21_subsidiary): **Curtiss-Wright Electro-Mechanical Corporation**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT ELECTRO-MECHANICAL CORPORATION**
- Normalized join key: `curtiss wright electro mechanical corp`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-electro-mechanical-corp` · `identifier:cw:jkznkggwyz87` · `ownership:cw:curtiss-wright-electro-mechanical-corp`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-jkznkggwyz87` (USAspending.gov, official_award, 6171 bytes, sha256 `76185ab504f733c9…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0001922C0003_9700_-NONE-_-NONE-/

### CW → `MWAKL633WET8`

- SEC name (ex21_subsidiary): **Curtiss-Wright Electro-Mechanical Corporation**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT ELECTRO-MECHANICAL CORPORATION**
- Normalized join key: `curtiss wright electro mechanical corp`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-electro-mechanical-corp` · `identifier:cw:mwakl633wet8` · `ownership:cw:curtiss-wright-electro-mechanical-corp`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-mwakl633wet8` (USAspending.gov, official_award, 6477 bytes, sha256 `b733814dbf2f250f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010422FNA00_9700_N0010419GNA01_9700/

### CW → `N257NEGSDQJ9`

- SEC name (ex21_subsidiary): **Curtiss Wright Controls Inc.**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT CONTROLS, INC.**
- Normalized join key: `curtiss wright controls inc`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-controls-inc` · `identifier:cw:n257negsdqj9` · `ownership:cw:curtiss-wright-controls-inc`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-n257negsdqj9` (USAspending.gov, official_award, 6093 bytes, sha256 `65b7886f36c744e9…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPE4A724C0140_9700_-NONE-_-NONE-/

### CW → `NGCRKJERS5T1`

- SEC name (ex21_subsidiary): **Curtiss-Wright Flow Control Service, LLC**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT FLOW CONTROL SERVICE, LLC**
- Normalized join key: `curtiss wright flow control service llc`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-flow-control-service-llc` · `identifier:cw:ngcrkjers5t1` · `ownership:cw:curtiss-wright-flow-control-service-llc`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-ngcrkjers5t1` (USAspending.gov, official_award, 6717 bytes, sha256 `2282c1f45c78dd22…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA853421F0005_9700_FA853421D0001_9700/

### CW → `NYGUEDY27AM8`

- SEC name (ex21_subsidiary): **Curtiss-Wright Flow Control Corporation**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT FLOW CONTROL CORPORATION**
- Normalized join key: `curtiss wright flow control corp`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-flow-control-corp` · `identifier:cw:nyguedy27am8` · `ownership:cw:curtiss-wright-flow-control-corp`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-nyguedy27am8` (USAspending.gov, official_award, 6078 bytes, sha256 `dbcd06363b211972…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010424CLA34_9700_-NONE-_-NONE-/

### CW → `TMFLTAKP1KH2`

- SEC name (ex21_subsidiary): **Curtiss Wright Controls Inc.**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT CONTROLS, INC.**
- Normalized join key: `curtiss wright controls inc`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-controls-inc` · `identifier:cw:tmfltakp1kh2` · `ownership:cw:curtiss-wright-controls-inc`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-tmfltakp1kh2` (USAspending.gov, official_award, 6107 bytes, sha256 `3ed218fcf80088cb…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPE4A726C0068_9700_-NONE-_-NONE-/

### CW → `UVF8ZTYG9FV3`

- SEC name (ex21_subsidiary): **Curtiss-Wright Electro-Mechanical Corporation**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT ELECTRO-MECHANICAL CORPORATION**
- Normalized join key: `curtiss wright electro mechanical corp`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-electro-mechanical-corp` · `identifier:cw:uvf8ztyg9fv3` · `ownership:cw:curtiss-wright-electro-mechanical-corp`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-uvf8ztyg9fv3` (USAspending.gov, official_award, 6176 bytes, sha256 `7883bf11dcc63662…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010425PJD21_9700_-NONE-_-NONE-/

### CW → `VXHFDAKS2LZ6`

- SEC name (ex21_subsidiary): **Curtiss-Wright Electro-Mechanical Corporation**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT ELECTRO-MECHANICAL CORP**
- Normalized join key: `curtiss wright electro mechanical corp`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-electro-mechanical-corp` · `identifier:cw:vxhfdaks2lz6` · `ownership:cw:curtiss-wright-electro-mechanical-corp`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-vxhfdaks2lz6` (USAspending.gov, official_award, 6102 bytes, sha256 `33a024c895b1703d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPRMM121PYE12_9700_-NONE-_-NONE-/

### CW → `WYDAKCJ5K219`

- SEC name (ex21_subsidiary): **Curtiss-Wright Electro-Mechanical Corporation**
- SEC document: `exhibit21_20251231.htm`
- USAspending recipient name(s): **CURTISS-WRIGHT ELECTRO-MECHANICAL CORPORATION**
- Normalized join key: `curtiss wright electro mechanical corp`
- Discovery ticker on the matched rows: CW
- Graph rows: `legal:cw:curtiss-wright-electro-mechanical-corp` · `identifier:cw:wydakcj5k219` · `ownership:cw:curtiss-wright-electro-mechanical-corp`
- Evidence:
    - `evidence:cw-sec-ex21` (SEC, official_filing, 7558 bytes, sha256 `42f709391c0cfd79…`) https://www.sec.gov/Archives/edgar/data/26324/000162828026007587/exhibit21_20251231.htm
    - `evidence:cw-usaspending-wydakcj5k219` (USAspending.gov, official_award, 6140 bytes, sha256 `fa84eb6d01203988…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010417CFA82_9700_-NONE-_-NONE-/

### GD → `CRBHYXTBZUL1`

- SEC name (ex21_subsidiary): **General Dynamics Information Technology, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS INFORMATION TECHNOLOGY, INC.**
- Normalized join key: `general dynamics information technology inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-information-technology-inc` · `identifier:gd:crbhyxtbzul1` · `ownership:gd:general-dynamics-information-technology-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-crbhyxtbzul1` (USAspending.gov, official_award, 6846 bytes, sha256 `73a6053cd8d6aeee…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HSHQDC08J00169_7001_HSHQDC06D00021_7001/

### GD → `E7BEKJ4V9528`

- SEC name (ex21_subsidiary): **Electric Boat Corporation**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **ELECTRIC BOAT CORPORATION**
- Normalized join key: `electric boat corp`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:electric-boat-corp` · `identifier:gd:e7bekj4v9528` · `ownership:gd:electric-boat-corp`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-e7bekj4v9528` (USAspending.gov, official_award, 6110 bytes, sha256 `8996c7c9d3ff6c8e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002405C2103_9700_-NONE-_-NONE-/

### GD → `E7FAZ5GRAWJ3`

- SEC name (ex21_subsidiary): **General Dynamics Land Systems Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS LAND SYSTEMS, INC**
- Normalized join key: `general dynamics land systems inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-land-systems-inc` · `identifier:gd:e7faz5grawj3` · `ownership:gd:general-dynamics-land-systems-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-e7faz5grawj3` (USAspending.gov, official_award, 6182 bytes, sha256 `37a7991ccff3a127…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_M6785408C0003_9700_-NONE-_-NONE-/

### GD → `FNEJKBCACXL1`

- SEC name (ex21_subsidiary): **General Dynamics Ordnance and Tactical Systems, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS ORDNANCE AND TACTICAL SYSTEMS, INC.**
- Normalized join key: `general dynamics ordnance and tactical systems inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-ordnance-and-tactical-systems-inc` · `identifier:gd:fnejkbcacxl1` · `ownership:gd:general-dynamics-ordnance-and-tactical-systems-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-fnejkbcacxl1` (USAspending.gov, official_award, 6601 bytes, sha256 `82243736f681589f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W15QKN24F0392_9700_W15QKN23D0054_9700/

### GD → `FREEMCLKFXE3`

- SEC name (ex21_subsidiary): **Bath Iron Works Corporation**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **BATH IRON WORKS CORPORATION**
- Normalized join key: `bath iron works corp`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:bath-iron-works-corp` · `identifier:gd:freemclkfxe3` · `ownership:gd:bath-iron-works-corp`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-freemclkfxe3` (USAspending.gov, official_award, 6460 bytes, sha256 `392bcb3dd5d2c058…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002402C2303_9700_-NONE-_-NONE-/

### GD → `H2TPPTLN7D18`

- SEC name (ex21_subsidiary): **General Dynamics Ordnance and Tactical Systems, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS ORDNANCE AND TACTICAL SYSTEMS, INC.**
- Normalized join key: `general dynamics ordnance and tactical systems inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-ordnance-and-tactical-systems-inc` · `identifier:gd:h2tpptln7d18` · `ownership:gd:general-dynamics-ordnance-and-tactical-systems-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-h2tpptln7d18` (USAspending.gov, official_award, 6283 bytes, sha256 `b9188c0be93f1ac6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W52P1J16C0058_9700_-NONE-_-NONE-/

### GD → `HAWKSQF848W7`

- SEC name (ex21_subsidiary): **General Dynamics Land Systems Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS LAND SYSTEMS INC.**
- Normalized join key: `general dynamics land systems inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-land-systems-inc` · `identifier:gd:hawksqf848w7` · `ownership:gd:general-dynamics-land-systems-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-hawksqf848w7` (USAspending.gov, official_award, 6662 bytes, sha256 `cd7cc95d84a5e636…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0001_9700_W56HZV17DB020_9700/

### GD → `J1FCJLK5LGU5`

- SEC name (ex21_subsidiary): **Metro Machine Corp.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **METRO MACHINE CORP.**
- Normalized join key: `metro machine corp`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:metro-machine-corp` · `identifier:gd:j1fcjlk5lgu5` · `ownership:gd:metro-machine-corp`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-j1fcjlk5lgu5` (USAspending.gov, official_award, 6018 bytes, sha256 `d4038b9f2c4d329f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002409C4416_9700_-NONE-_-NONE-/

### GD → `J4NSWZYV6EE4`

- SEC name (ex21_subsidiary): **General Dynamics Information Technology, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS INFORMATION TECHNOLOGY, INC.**
- Normalized join key: `general dynamics information technology inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-information-technology-inc` · `identifier:gd:j4nswzyv6ee4` · `ownership:gd:general-dynamics-information-technology-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-j4nswzyv6ee4` (USAspending.gov, official_award, 6556 bytes, sha256 `fcb3bea3287ffcec…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HHSM500200900029C_7530_-NONE-_-NONE-/

### GD → `JHY6AZA6H191`

- SEC name (ex21_subsidiary): **General Dynamics Mission Systems, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS MISSION SYSTEMS, INC.**
- Normalized join key: `general dynamics mission systems inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-mission-systems-inc` · `identifier:gd:jhy6aza6h191` · `ownership:gd:general-dynamics-mission-systems-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-jhy6aza6h191` (USAspending.gov, official_award, 6487 bytes, sha256 `22e9035a3c411366…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0001_9700_W15P7T10DC007_9700/

### GD → `L3AVSXCECXA5`

- SEC name (ex21_subsidiary): **General Dynamics Information Technology, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS INFORMATION TECHNOLOGY, INC**
- Normalized join key: `general dynamics information technology inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-information-technology-inc` · `identifier:gd:l3avsxcecxa5` · `ownership:gd:general-dynamics-information-technology-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-l3avsxcecxa5` (USAspending.gov, official_award, 6943 bytes, sha256 `1f8d93d8482a5aa0…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HHSM500T0002_7530_HHSM500200700017I_7530/

### GD → `LFK5WLJ8KT48`

- SEC name (ex21_subsidiary): **GM GDLS Defense Group, L.L.C.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GM GDLS DEFENSE GROUP, L.L.C.**
- Normalized join key: `gm gdls defense group l l c`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:gm-gdls-defense-group-l-l-c` · `identifier:gd:lfk5wlj8kt48` · `ownership:gd:gm-gdls-defense-group-l-l-c`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-lfk5wlj8kt48` (USAspending.gov, official_award, 6389 bytes, sha256 `932c3a245e2a842c…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0269_9700_W56HZV07DM112_9700/

### GD → `LKMMNBMPUNH7`

- SEC name (ex21_subsidiary): **General Dynamics Mission Systems, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS MISSION SYSTEMS, INC.**
- Normalized join key: `general dynamics mission systems inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-mission-systems-inc` · `identifier:gd:lkmmnbmpunh7` · `ownership:gd:general-dynamics-mission-systems-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-lkmmnbmpunh7` (USAspending.gov, official_award, 6464 bytes, sha256 `6ece2be134dfbf42…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0003016C0005_9700_-NONE-_-NONE-/

### GD → `MWDRZJ2ZVPV7`

- SEC name (ex21_subsidiary): **General Dynamics Mission Systems, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS MISSION SYSTEMS, INC.**
- Normalized join key: `general dynamics mission systems inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-mission-systems-inc` · `identifier:gd:mwdrzj2zvpv7` · `ownership:gd:general-dynamics-mission-systems-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-mwdrzj2zvpv7` (USAspending.gov, official_award, 6449 bytes, sha256 `90f6e6c009a29606…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_DTFAWA12C00040_6920_-NONE-_-NONE-/

### GD → `Q85KVUK3JBF5`

- SEC name (ex21_subsidiary): **National Steel and Shipbuilding Company**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **NATIONAL STEEL AND SHIPBUILDING COMPANY**
- Normalized join key: `national steel and shipbuilding co`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:national-steel-and-shipbuilding-co` · `identifier:gd:q85kvuk3jbf5` · `ownership:gd:national-steel-and-shipbuilding-co`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-q85kvuk3jbf5` (USAspending.gov, official_award, 6184 bytes, sha256 `ae4af9e8a98ac10d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002415C4313_9700_-NONE-_-NONE-/

### GD → `Q9SBTF8ELUP4`

- SEC name (ex21_subsidiary): **General Dynamics-OTS, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS-OTS, INC.**
- Normalized join key: `general dynamics ots inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-ots-inc` · `identifier:gd:q9sbtf8elup4` · `ownership:gd:general-dynamics-ots-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-q9sbtf8elup4` (USAspending.gov, official_award, 6774 bytes, sha256 `95686aa220601e47…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPRRA225F0197_9700_SPRRA225D0009_9700/

### GD → `SMNWM6HN79X5`

- SEC name (ex21_subsidiary): **General Dynamics Information Technology, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS INFORMATION TECHNOLOGY, INC.**
- Normalized join key: `general dynamics information technology inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-information-technology-inc` · `identifier:gd:smnwm6hn79x5` · `ownership:gd:general-dynamics-information-technology-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-smnwm6hn79x5` (USAspending.gov, official_award, 6571 bytes, sha256 `da2c4a4ac1ac88cc…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0142_9700_DAAB0700DE252_9700/

### GD → `V1TVADBWD4E9`

- SEC name (ex21_subsidiary): **General Dynamics OTS (Wilkes Barre), LLC**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS OTS (WILKES BARRE), LLC**
- Normalized join key: `general dynamics ots wilkes barre llc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-ots-wilkes-barre-llc` · `identifier:gd:v1tvadbwd4e9` · `ownership:gd:general-dynamics-ots-wilkes-barre-llc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-v1tvadbwd4e9` (USAspending.gov, official_award, 6726 bytes, sha256 `a3bf63d309f64888…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W15QKN24F0527_9700_W15QKN24D0052_9700/

### GD → `Z2L7LVNEAPC3`

- SEC name (ex21_subsidiary): **General Dynamics Information Technology, Inc.**
- SEC document: `ex21-20251231.htm`
- USAspending recipient name(s): **GENERAL DYNAMICS INFORMATION TECHNOLOGY INC.**
- Normalized join key: `general dynamics information technology inc`
- Discovery ticker on the matched rows: GD
- Graph rows: `legal:gd:general-dynamics-information-technology-inc` · `identifier:gd:z2l7lvneapc3` · `ownership:gd:general-dynamics-information-technology-inc`
- Evidence:
    - `evidence:gd-sec-ex21` (SEC, official_filing, 168683 bytes, sha256 `faac3298b7df8459…`) https://www.sec.gov/Archives/edgar/data/40533/000004053326000006/ex21-20251231.htm
    - `evidence:gd-usaspending-z2l7lvneapc3` (USAspending.gov, official_award, 6752 bytes, sha256 `5ea3e15769ac540f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SAQMMA16F3813_1900_SAQMMA10D0017_1900/

### HEI → `C6YFXFEM81Q5`

- SEC name (ex21_subsidiary): **TTT-Cubed, Inc.**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **TTT-CUBED INC**
- Normalized join key: `ttt cubed inc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:ttt-cubed-inc` · `identifier:hei:c6yfxfem81q5` · `ownership:hei:ttt-cubed-inc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-c6yfxfem81q5` (USAspending.gov, official_award, 6645 bytes, sha256 `f55c3902db4f03e4…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N6893622F0486_9700_N6893614D0009_9700/

### HEI → `G4M3KUF95AL3`

- SEC name (ex21_subsidiary): **Robertson Fuel Systems, L.L.C.**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **ROBERTSON FUEL SYSTEMS, L.L.C.**
- Normalized join key: `robertson fuel systems l l c`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:robertson-fuel-systems-l-l-c` · `identifier:hei:g4m3kuf95al3` · `ownership:hei:robertson-fuel-systems-l-l-c`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-g4m3kuf95al3` (USAspending.gov, official_award, 6693 bytes, sha256 `3278b4e316aead1b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA852421F0013_9700_FA852419D0002_9700/

### HEI → `H8PJQK5TU3N5`

- SEC name (ex21_subsidiary): **Jet Avion Corporation**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **JET AVION CORP**
- Normalized join key: `jet avion corp`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:jet-avion-corp` · `identifier:hei:h8pjqk5tu3n5` · `ownership:hei:jet-avion-corp`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-h8pjqk5tu3n5` (USAspending.gov, official_award, 6383 bytes, sha256 `a4f2a038427258e6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPE4A618F561W_9700_SPE4A618D6846_9700/

### HEI → `J5UNNCETDZ24`

- SEC name (ex21_subsidiary): **Transformational Security, LLC**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **TRANSFORMATIONAL SECURITY, LLC**
- Normalized join key: `transformational security llc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:transformational-security-llc` · `identifier:hei:j5unncetdz24` · `ownership:hei:transformational-security-llc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-j5unncetdz24` (USAspending.gov, official_award, 6298 bytes, sha256 `858f1e86aaceb4b6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA702219PA001_9700_-NONE-_-NONE-/

### HEI → `MV2FTFU6ELL8`

- SEC name (ex21_subsidiary): **Blue Aerospace LLC**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **BLUE AEROSPACE LLC**
- Normalized join key: `blue aerospace llc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:blue-aerospace-llc` · `identifier:hei:mv2ftfu6ell8` · `ownership:hei:blue-aerospace-llc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-mv2ftfu6ell8` (USAspending.gov, official_award, 6247 bytes, sha256 `9852e411c1f0ee2e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_1305M222PNMAN0035_1330_-NONE-_-NONE-/

### HEI → `N4LLJP3VYN48`

- SEC name (ex21_subsidiary): **Research Electronics International, L.L.C.**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **RESEARCH ELECTRONICS INTERNATIONAL, L.L.C.**
- Normalized join key: `research electronics international l l c`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:research-electronics-international-l-l-c` · `identifier:hei:n4lljp3vyn48` · `ownership:hei:research-electronics-international-l-l-c`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-n4lljp3vyn48` (USAspending.gov, official_award, 6200 bytes, sha256 `b864dd81443a2ef5…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_70RDA125P00000014_7001_-NONE-_-NONE-/

### HEI → `T9YDSKR72SH8`

- SEC name (ex21_subsidiary): **Future Aviation, Inc.**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **FUTURE AVIATION INC**
- Normalized join key: `future aviation inc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:future-aviation-inc` · `identifier:hei:t9ydskr72sh8` · `ownership:hei:future-aviation-inc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-t9ydskr72sh8` (USAspending.gov, official_award, 6100 bytes, sha256 `60f496f72706ca1e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPRTA121C0026_9700_-NONE-_-NONE-/

### HEI → `TGCRLMJWHDG4`

- SEC name (ex21_subsidiary): **Sensor Technology Engineering, LLC**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **SENSOR TECHNOLOGY ENGINEERING LLC**
- Normalized join key: `sensor technology engineering llc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:sensor-technology-engineering-llc` · `identifier:hei:tgcrlmjwhdg4` · `ownership:hei:sensor-technology-engineering-llc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-tgcrlmjwhdg4` (USAspending.gov, official_award, 6553 bytes, sha256 `60b98a071f2bb7e7…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_70RWMD22P00000002_7001_-NONE-_-NONE-/

### HEI → `TJKJJ8NE44C9`

- SEC name (ex21_subsidiary): **Rocky Mountain Hydrostatics, LLC**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **ROCKY MOUNTAIN HYDROSTATICS, LLC**
- Normalized join key: `rocky mountain hydrostatics llc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:rocky-mountain-hydrostatics-llc` · `identifier:hei:tjkjj8ne44c9` · `ownership:hei:rocky-mountain-hydrostatics-llc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-tjkjj8ne44c9` (USAspending.gov, official_award, 6031 bytes, sha256 `442395e74d33ec45…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010422PJC35_9700_-NONE-_-NONE-/

### HEI → `TLC5M9HQ62P3`

- SEC name (ex21_subsidiary): **Santa Barbara Infrared, Inc.**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **SANTA BARBARA INFRARED, INC.**
- Normalized join key: `santa barbara infrared inc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:santa-barbara-infrared-inc` · `identifier:hei:tlc5m9hq62p3` · `ownership:hei:santa-barbara-infrared-inc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-tlc5m9hq62p3` (USAspending.gov, official_award, 6280 bytes, sha256 `fd014193fe228db6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA248716C0299_9700_-NONE-_-NONE-/

### HEI → `WUWPR2NTEJ37`

- SEC name (ex21_subsidiary): **Aerospace & Commercial Technologies, LLC**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **AEROSPACE & COMMERCIAL TECHNOLOGIES, LLC**
- Normalized join key: `aerospace & commercial technologies llc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:aerospace-commercial-technologies-llc` · `identifier:hei:wuwpr2ntej37` · `ownership:hei:aerospace-commercial-technologies-llc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-wuwpr2ntej37` (USAspending.gov, official_award, 6662 bytes, sha256 `d4eac2fc91733409…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA825122F0020_9700_FA825121D0008_9700/

### HEI → `Y1M9BKYLXL58`

- SEC name (ex21_subsidiary): **Seal Dynamics LLC**
- SEC document: `a103125heiq4exhibit21.htm`
- USAspending recipient name(s): **SEAL DYNAMICS LLC**
- Normalized join key: `seal dynamics llc`
- Discovery ticker on the matched rows: HEI
- Graph rows: `legal:hei:seal-dynamics-llc` · `identifier:hei:y1m9bkylxl58` · `ownership:hei:seal-dynamics-llc`
- Evidence:
    - `evidence:hei-sec-ex21` (SEC, official_filing, 116105 bytes, sha256 `b8f1c553c513f106…`) https://www.sec.gov/Archives/edgar/data/46619/000004661925000082/a103125heiq4exhibit21.htm
    - `evidence:hei-usaspending-y1m9bkylxl58` (USAspending.gov, official_award, 5888 bytes, sha256 `ec7f3a6ba4391985…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010423PLF33_9700_-NONE-_-NONE-/

### HII → `C3NLZNSMU254`

- SEC name (ex21_subsidiary): **Huntington Ingalls Incorporated**
- SEC document: `hii-ex211202510xk.htm`
- USAspending recipient name(s): **HUNTINGTON INGALLS INCORPORATED**
- Normalized join key: `huntington ingalls inc`
- Discovery ticker on the matched rows: HII
- Graph rows: `legal:hii:huntington-ingalls-inc` · `identifier:hii:c3nlznsmu254` · `ownership:hii:huntington-ingalls-inc`
- Evidence:
    - `evidence:hii-sec-ex21` (SEC, official_filing, 19400 bytes, sha256 `ea19325cf78305ea…`) https://www.sec.gov/Archives/edgar/data/1501585/000150158526000006/hii-ex211202510xk.htm
    - `evidence:hii-usaspending-c3nlznsmu254` (USAspending.gov, official_award, 6232 bytes, sha256 `924f6c221844941d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HSCG2311C2DB043_7008_-NONE-_-NONE-/

### HII → `R8HYN67MPFC9`

- SEC name (ex21_subsidiary): **HII Nuclear Inc.**
- SEC document: `hii-ex211202510xk.htm`
- USAspending recipient name(s): **HII NUCLEAR INC**
- Normalized join key: `hii nuclear inc`
- Discovery ticker on the matched rows: HII
- Graph rows: `legal:hii:hii-nuclear-inc` · `identifier:hii:r8hyn67mpfc9` · `ownership:hii:hii-nuclear-inc`
- Evidence:
    - `evidence:hii-sec-ex21` (SEC, official_filing, 19400 bytes, sha256 `ea19325cf78305ea…`) https://www.sec.gov/Archives/edgar/data/1501585/000150158526000006/hii-ex211202510xk.htm
    - `evidence:hii-usaspending-r8hyn67mpfc9` (USAspending.gov, official_award, 6528 bytes, sha256 `6612a720463b4698…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_DEAT0108LM00501_8900_DEAM0107LM00060_8900/

### HII → `WMXDDH6HJNA5`

- SEC name (ex21_subsidiary): **Huntington Ingalls Incorporated**
- SEC document: `hii-ex211202510xk.htm`
- USAspending recipient name(s): **HUNTINGTON INGALLS INC**
- Normalized join key: `huntington ingalls inc`
- Discovery ticker on the matched rows: HII
- Graph rows: `legal:hii:huntington-ingalls-inc` · `identifier:hii:wmxddh6hjna5` · `ownership:hii:huntington-ingalls-inc`
- Evidence:
    - `evidence:hii-sec-ex21` (SEC, official_filing, 19400 bytes, sha256 `ea19325cf78305ea…`) https://www.sec.gov/Archives/edgar/data/1501585/000150158526000006/hii-ex211202510xk.htm
    - `evidence:hii-usaspending-wmxddh6hjna5` (USAspending.gov, official_award, 5628 bytes, sha256 `fe6a6140101f11c9…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002400C2104_9700_-NONE-_-NONE-/

### HWM → `DNKWWW1EHS28`

- SEC name (ex21_subsidiary): **Howmet Global Fastening Systems Inc.**
- SEC document: `ex21_4q25.htm`
- USAspending recipient name(s): **HOWMET GLOBAL FASTENING SYSTEMS INC**
- Normalized join key: `howmet global fastening systems inc`
- Discovery ticker on the matched rows: HWM
- Graph rows: `legal:hwm:howmet-global-fastening-systems-inc` · `identifier:hwm:dnkwww1ehs28` · `ownership:hwm:howmet-global-fastening-systems-inc`
- Evidence:
    - `evidence:hwm-sec-ex21` (SEC, official_filing, 10740 bytes, sha256 `6f1106ed10cdb341…`) https://www.sec.gov/Archives/edgar/data/4281/000000428126000012/ex21_4q25.htm
    - `evidence:hwm-usaspending-dnkwww1ehs28` (USAspending.gov, official_award, 6095 bytes, sha256 `2224c71b0287fa28…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0042122P0506_9700_-NONE-_-NONE-/

### HWM → `HV8GQ9L5SNM1`

- SEC name (ex21_subsidiary): **Howmet Castings & Services, Inc.**
- SEC document: `ex21_4q25.htm`
- USAspending recipient name(s): **HOWMET CASTINGS & SERVICES, INC.**
- Normalized join key: `howmet castings & services inc`
- Discovery ticker on the matched rows: HWM
- Graph rows: `legal:hwm:howmet-castings-services-inc` · `identifier:hwm:hv8gq9l5snm1` · `ownership:hwm:howmet-castings-services-inc`
- Evidence:
    - `evidence:hwm-sec-ex21` (SEC, official_filing, 10740 bytes, sha256 `6f1106ed10cdb341…`) https://www.sec.gov/Archives/edgar/data/4281/000000428126000012/ex21_4q25.htm
    - `evidence:hwm-usaspending-hv8gq9l5snm1` (USAspending.gov, official_award, 6510 bytes, sha256 `cd413e97d956c1ae…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0004_9700_W15QKN14D0040_9700/

### HWM → `LB1RA7SPKMV4`

- SEC name (ex21_subsidiary): **Howmet Global Fastening Systems Inc.**
- SEC document: `ex21_4q25.htm`
- USAspending recipient name(s): **HOWMET GLOBAL FASTENING SYSTEMS INC**
- Normalized join key: `howmet global fastening systems inc`
- Discovery ticker on the matched rows: HWM
- Graph rows: `legal:hwm:howmet-global-fastening-systems-inc` · `identifier:hwm:lb1ra7spkmv4` · `ownership:hwm:howmet-global-fastening-systems-inc`
- Evidence:
    - `evidence:hwm-sec-ex21` (SEC, official_filing, 10740 bytes, sha256 `6f1106ed10cdb341…`) https://www.sec.gov/Archives/edgar/data/4281/000000428126000012/ex21_4q25.htm
    - `evidence:hwm-usaspending-lb1ra7spkmv4` (USAspending.gov, official_award, 6183 bytes, sha256 `b571d9e0462125ab…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_70Z03825PA0000313_7008_-NONE-_-NONE-/

### IRDM → `HDGMK3RKNGC1`

- SEC name (ex21_subsidiary): **Iridium Satellite LLC**
- SEC document: `ex2111231202510k.htm`
- USAspending recipient name(s): **IRIDIUM SATELLITE LLC**
- Normalized join key: `iridium satellite llc`
- Discovery ticker on the matched rows: IRDM
- Graph rows: `legal:irdm:iridium-satellite-llc` · `identifier:irdm:hdgmk3rkngc1` · `ownership:irdm:iridium-satellite-llc`
- Evidence:
    - `evidence:irdm-sec-ex21` (SEC, official_filing, 9618 bytes, sha256 `059ff7bf7ec975ea…`) https://www.sec.gov/Archives/edgar/data/1418819/000141881926000009/ex2111231202510k.htm
    - `evidence:irdm-usaspending-hdgmk3rkngc1` (USAspending.gov, official_award, 6388 bytes, sha256 `c8b76c1a0f99ae17…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA254124CB001_9700_-NONE-_-NONE-/

### IRDM → `HLRBBNMS1EB8`

- SEC name (ex21_subsidiary): **Iridium Satellite LLC**
- SEC document: `ex2111231202510k.htm`
- USAspending recipient name(s): **IRIDIUM SATELLITE LLC**
- Normalized join key: `iridium satellite llc`
- Discovery ticker on the matched rows: IRDM
- Graph rows: `legal:irdm:iridium-satellite-llc` · `identifier:irdm:hlrbbnms1eb8` · `ownership:irdm:iridium-satellite-llc`
- Evidence:
    - `evidence:irdm-sec-ex21` (SEC, official_filing, 9618 bytes, sha256 `059ff7bf7ec975ea…`) https://www.sec.gov/Archives/edgar/data/1418819/000141881926000009/ex2111231202510k.htm
    - `evidence:irdm-usaspending-hlrbbnms1eb8` (USAspending.gov, official_award, 6384 bytes, sha256 `e2b68863b6695ee3…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_6913G625P800073_6901_-NONE-_-NONE-/

### IRDM → `S77SW52LCR57`

- SEC name (ex21_subsidiary): **Iridium Government Services LLC**
- SEC document: `ex2111231202510k.htm`
- USAspending recipient name(s): **IRIDIUM GOVERNMENT SERVICES LLC**
- Normalized join key: `iridium government services llc`
- Discovery ticker on the matched rows: IRDM
- Graph rows: `legal:irdm:iridium-government-services-llc` · `identifier:irdm:s77sw52lcr57` · `ownership:irdm:iridium-government-services-llc`
- Evidence:
    - `evidence:irdm-sec-ex21` (SEC, official_filing, 9618 bytes, sha256 `059ff7bf7ec975ea…`) https://www.sec.gov/Archives/edgar/data/1418819/000141881926000009/ex2111231202510k.htm
    - `evidence:irdm-usaspending-s77sw52lcr57` (USAspending.gov, official_award, 6626 bytes, sha256 `ae9fc95e9cd4e6cc…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0005_9700_N0017809D3007_9700/

### KTOS → `CQQAZNLAJHG1`

- SEC name (ex21_subsidiary): **Kratos Defense & Rocket Support Services, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS DEFENSE & ROCKET SUPPORT SERVICES, INC**
- Normalized join key: `kratos defense & rocket support services inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-defense-rocket-support-services-inc` · `identifier:ktos:cqqaznlajhg1` · `ownership:ktos:kratos-defense-rocket-support-services-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-cqqaznlajhg1` (USAspending.gov, official_award, 6515 bytes, sha256 `88932e4094b2fe7f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ014718C0025_9700_-NONE-_-NONE-/

### KTOS → `D7GMZLLJLXB3`

- SEC name (ex21_subsidiary): **Kratos S2, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS S2, INC**
- Normalized join key: `kratos s2 inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-s2-inc` · `identifier:ktos:d7gmzlljlxb3` · `ownership:ktos:kratos-s2-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-d7gmzlljlxb3` (USAspending.gov, official_award, 6726 bytes, sha256 `4aa396929f6d9ee1…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_47QFCA20C0019_4732_-NONE-_-NONE-/

### KTOS → `EJ5QQHF7B1P6`

- SEC name (ex21_subsidiary): **Florida Turbine Technologies, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **FLORIDA TURBINE TECHNOLOGIES, INC.**
- Normalized join key: `florida turbine technologies inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:florida-turbine-technologies-inc` · `identifier:ktos:ej5qqhf7b1p6` · `ownership:ktos:florida-turbine-technologies-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-ej5qqhf7b1p6` (USAspending.gov, official_award, 7016 bytes, sha256 `22b55a1a3d1dd73e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA865019F2071_9700_FA865019D2056_9700/

### KTOS → `EL87FVGWGUL3`

- SEC name (ex21_subsidiary): **Kratos S1, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS S1, INC.**
- Normalized join key: `kratos s1 inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-s1-inc` · `identifier:ktos:el87fvgwgul3` · `ownership:ktos:kratos-s1-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-el87fvgwgul3` (USAspending.gov, official_award, 6250 bytes, sha256 `b15428e85d7b0ab0…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA461020C0003_9700_-NONE-_-NONE-/

### KTOS → `FLLRPTP8S7N4`

- SEC name (ex21_subsidiary): **Kratos Technology & Training Solutions, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS TECHNOLOGY & TRAINING SOLUTIONS, INC.**
- Normalized join key: `kratos technology & training solutions inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-technology-training-solutions-inc` · `identifier:ktos:fllrptp8s7n4` · `ownership:ktos:kratos-technology-training-solutions-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-fllrptp8s7n4` (USAspending.gov, official_award, 6549 bytes, sha256 `c4caa37e1f0d9a30…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0002_9700_N6134012D5116_9700/

### KTOS → `GL85ACATYXX5`

- SEC name (ex21_subsidiary): **Gichner Systems Group, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **GICHNER SYSTEMS GROUP, INC.**
- Normalized join key: `gichner systems group inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:gichner-systems-group-inc` · `identifier:ktos:gl85acatyxx5` · `ownership:ktos:gichner-systems-group-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-gl85acatyxx5` (USAspending.gov, official_award, 6217 bytes, sha256 `cc3b6591da98635d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N6833521C0205_9700_-NONE-_-NONE-/

### KTOS → `GM11ZH81LBY7`

- SEC name (ex21_subsidiary): **Kratos SRE, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS SRE, INC.**
- Normalized join key: `kratos sre inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-sre-inc` · `identifier:ktos:gm11zh81lby7` · `ownership:ktos:kratos-sre-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-gm11zh81lby7` (USAspending.gov, official_award, 6973 bytes, sha256 `98fab541ecb4b5f4…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_80ARC023FA002_8000_80ARC023AA001_8000/

### KTOS → `GURMFDFLENX4`

- SEC name (ex21_subsidiary): **Kratos Unmanned Aerial Systems, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS UNMANNED AERIAL SYSTEMS, INC**
- Normalized join key: `kratos unmanned aerial systems inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-unmanned-aerial-systems-inc` · `identifier:ktos:gurmfdflenx4` · `ownership:ktos:kratos-unmanned-aerial-systems-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-gurmfdflenx4` (USAspending.gov, official_award, 6616 bytes, sha256 `3888b269990560e2…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA865016C2604_9700_-NONE-_-NONE-/

### KTOS → `L2HKXLBRTL16`

- SEC name (ex21_subsidiary): **Micro Systems, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **MICRO SYSTEMS, INC**
- Normalized join key: `micro systems inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:micro-systems-inc` · `identifier:ktos:l2hkxlbrtl16` · `ownership:ktos:micro-systems-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-l2hkxlbrtl16` (USAspending.gov, official_award, 6602 bytes, sha256 `be2c5c178754a5f3…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0001919F2417_9700_N0001918G0032_9700/

### KTOS → `LHB4M9WHT686`

- SEC name (ex21_subsidiary): **Kratos Communications, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS COMMUNICATIONS, INC**
- Normalized join key: `kratos communications inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-communications-inc` · `identifier:ktos:lhb4m9wht686` · `ownership:ktos:kratos-communications-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-lhb4m9wht686` (USAspending.gov, official_award, 6299 bytes, sha256 `58dea2e378a48459…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_273FCC22P0085_2700_-NONE-_-NONE-/

### KTOS → `M7X3M2FNEPM7`

- SEC name (ex21_subsidiary): **Kratos Space & Missile Defense Systems, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS SPACE & MISSILE DEFENSE SYSTEMS, INC.**
- Normalized join key: `kratos space & missile defense systems inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-space-missile-defense-systems-inc` · `identifier:ktos:m7x3m2fnepm7` · `ownership:ktos:kratos-space-missile-defense-systems-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-m7x3m2fnepm7` (USAspending.gov, official_award, 6242 bytes, sha256 `1ab92ec8bf6e622b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N6339416C0007_9700_-NONE-_-NONE-/

### KTOS → `WEPMW2JTJNS8`

- SEC name (ex21_subsidiary): **Kratos Antenna Solutions Corporation**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS ANTENNA SOLUTIONS CORPORATION**
- Normalized join key: `kratos antenna solutions corp`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-antenna-solutions-corp` · `identifier:ktos:wepmw2jtjns8` · `ownership:ktos:kratos-antenna-solutions-corp`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-wepmw2jtjns8` (USAspending.gov, official_award, 6227 bytes, sha256 `072107470c2f1e87…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA830721P0146_9700_-NONE-_-NONE-/

### KTOS → `XF6AHNQFTXU5`

- SEC name (ex21_subsidiary): **Kratos Defense & Rocket Support Services, Inc.**
- SEC document: `ktos20251228ex-211.htm`
- USAspending recipient name(s): **KRATOS DEFENSE & ROCKET SUPPORT SERVICES, INC.**
- Normalized join key: `kratos defense & rocket support services inc`
- Discovery ticker on the matched rows: KTOS
- Graph rows: `legal:ktos:kratos-defense-rocket-support-services-inc` · `identifier:ktos:xf6ahnqftxu5` · `ownership:ktos:kratos-defense-rocket-support-services-inc`
- Evidence:
    - `evidence:ktos-sec-ex21` (SEC, official_filing, 39444 bytes, sha256 `481c64578609adc8…`) https://www.sec.gov/Archives/edgar/data/1069258/000106925826000013/ktos20251228ex-211.htm
    - `evidence:ktos-usaspending-xf6ahnqftxu5` (USAspending.gov, official_award, 6576 bytes, sha256 `eb697e50c64f809c…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ086022C0001_9700_-NONE-_-NONE-/

### LDOS → `FNQDFB8Z8QA8`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:fnqdfb8z8qa8` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-fnqdfb8z8qa8` (USAspending.gov, official_award, 6754 bytes, sha256 `ef5dcbabf0aec40b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0032_9700_W9113M07D0006_9700/

### LDOS → `HV8BH9BPG8Y9`

- SEC name (ex21_subsidiary): **Leidos Biomedical Research, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS BIOMEDICAL RESEARCH INC**
- Normalized join key: `leidos biomedical research inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-biomedical-research-inc` · `identifier:ldos:hv8bh9bpg8y9` · `ownership:ldos:leidos-biomedical-research-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-hv8bh9bpg8y9` (USAspending.gov, official_award, 7184 bytes, sha256 `21fc63be879dccdb…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_75N91019F00129_7529_75N91019D00024_7529/

### LDOS → `JSTDGZNFP4A3`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:jstdgznfp4a3` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-jstdgznfp4a3` (USAspending.gov, official_award, 6857 bytes, sha256 `ed3cda004895f10d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_70B04C21F00000993_7014_70B04C20A00000008_7014/

### LDOS → `KTMAJCY6JXM3`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:ktmajcy6jxm3` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-ktmajcy6jxm3` (USAspending.gov, official_award, 6419 bytes, sha256 `4804c148a5c2efc1…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_75N94019C00013_7529_-NONE-_-NONE-/

### LDOS → `LK5RJU5V68X6`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:lk5rju5v68x6` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-lk5rju5v68x6` (USAspending.gov, official_award, 6402 bytes, sha256 `cecabf575d876b7f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HSBP1016C00103_7014_-NONE-_-NONE-/

### LDOS → `MDSWM6MB1BH7`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:mdswm6mb1bh7` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-mdswm6mb1bh7` (USAspending.gov, official_award, 6891 bytes, sha256 `933ea574d78701de…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_15A00020FAQA00189_1560_47QTCK18D0008_4732/

### LDOS → `MPD5KD7XAPK4`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS INC**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:mpd5kd7xapk4` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-mpd5kd7xapk4` (USAspending.gov, official_award, 7938 bytes, sha256 `6eee31fa5491b178…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_NNJ09HD46C_8000_-NONE-_-NONE-/

### LDOS → `MYKLJHTX3MM7`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:mykljhtx3mm7` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-mykljhtx3mm7` (USAspending.gov, official_award, 6609 bytes, sha256 `ad00592c5c29a7cd…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0024_9700_HC102812D0021_9700/

### LDOS → `NRCCMBKQ6FD7`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:nrccmbkq6fd7` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-nrccmbkq6fd7` (USAspending.gov, official_award, 6139 bytes, sha256 `2c70aa0f5cac2ade…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W58RGZ17C0058_9700_-NONE-_-NONE-/

### LDOS → `P1DHVE8PH2Q3`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:p1dhve8ph2q3` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-p1dhve8ph2q3` (USAspending.gov, official_award, 6057 bytes, sha256 `e9de09ee5569a0ed…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0010_9700_DAAH0100D0013_9700/

### LDOS → `QLNMVC12KWY3`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:qlnmvc12kwy3` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-qlnmvc12kwy3` (USAspending.gov, official_award, 6226 bytes, sha256 `32d32b7e611bc669…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_47QFCA21C0002_4732_-NONE-_-NONE-/

### LDOS → `UE9QJD4KK1L6`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:ue9qjd4kk1l6` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-ue9qjd4kk1l6` (USAspending.gov, official_award, 6460 bytes, sha256 `6ba94b0d4a66d456…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0001_9700_N0003915D0044_9700/

### LDOS → `X38JVP4R72E1`

- SEC name (ex21_subsidiary): **Leidos, Inc.**
- SEC document: `ldos1022026ex21.htm`
- USAspending recipient name(s): **LEIDOS, INC.**
- Normalized join key: `leidos inc`
- Discovery ticker on the matched rows: LDOS
- Graph rows: `legal:ldos:leidos-inc` · `identifier:ldos:x38jvp4r72e1` · `ownership:ldos:leidos-inc`
- Evidence:
    - `evidence:ldos-sec-ex21` (SEC, official_filing, 13362 bytes, sha256 `69076772e0b35d84…`) https://www.sec.gov/Archives/edgar/data/1336920/000133692026000030/ldos1022026ex21.htm
    - `evidence:ldos-usaspending-x38jvp4r72e1` (USAspending.gov, official_award, 6194 bytes, sha256 `d7266c21a17b649b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_693KA720C00002_6920_-NONE-_-NONE-/

### LHX → `CM2HHAV628D5`

- SEC name (ex21_subsidiary): **L3Harris Technologies Integrated Systems L.P.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES INTEGRATED SYSTEMS L.P.**
- Normalized join key: `l3harris technologies integrated systems l p`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-integrated-systems-l-p` · `identifier:lhx:cm2hhav628d5` · `ownership:lhx:l3harris-technologies-integrated-systems-l-p`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-cm2hhav628d5` (USAspending.gov, official_award, 6471 bytes, sha256 `8681e5b7d68ea960…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA862023F4781_9700_FA862020G4050_9700/

### LHX → `CXPAJ131RS23`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:cxpaj131rs23` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-cxpaj131rs23` (USAspending.gov, official_award, 6813 bytes, sha256 `be505dd12b2d378e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA880622F0009_9700_FA880621D0003_9700/

### LHX → `DK97RBJXMKF3`

- SEC name (ex21_subsidiary): **L3Harris Technologies Integrated Systems L.P.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES INTEGRATED SYSTEMS L.P.**
- Normalized join key: `l3harris technologies integrated systems l p`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-integrated-systems-l-p` · `identifier:lhx:dk97rbjxmkf3` · `ownership:lhx:l3harris-technologies-integrated-systems-l-p`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-dk97rbjxmkf3` (USAspending.gov, official_award, 6622 bytes, sha256 `2c658f9f22db1e09…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA862019F4839_9700_FA862019G4006_9700/

### LHX → `ENMFLGV87MS4`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:enmflgv87ms4` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-enmflgv87ms4` (USAspending.gov, official_award, 6915 bytes, sha256 `43f2c95b7651dc52…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA852319F0001_9700_FA854017D0002_9700/

### LHX → `H42MN1TYJ257`

- SEC name (ex21_subsidiary): **L3Harris Fuzing and Ordnance Systems, Inc.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS FUZING AND ORDNANCE SYSTEMS, INC.**
- Normalized join key: `l3harris fuzing and ordnance systems inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-fuzing-and-ordnance-systems-inc` · `identifier:lhx:h42mn1tyj257` · `ownership:lhx:l3harris-fuzing-and-ordnance-systems-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-h42mn1tyj257` (USAspending.gov, official_award, 6381 bytes, sha256 `0fecdf598a50c2f3…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W15QKN10C0015_9700_-NONE-_-NONE-/

### LHX → `JEGFV3LWEJH7`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:jegfv3lwejh7` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-jegfv3lwejh7` (USAspending.gov, official_award, 6618 bytes, sha256 `f1f5dfbbf88bbd61…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_80GSFC19C0021_8000_-NONE-_-NONE-/

### LHX → `JYAPS9B2MKE9`

- SEC name (ex21_subsidiary): **L3Harris Interstate Electronics Corporation**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS INTERSTATE ELECTRONICS CORPORATION**
- Normalized join key: `l3harris interstate electronics corp`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-interstate-electronics-corp` · `identifier:lhx:jyaps9b2mke9` · `ownership:lhx:l3harris-interstate-electronics-corp`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-jyaps9b2mke9` (USAspending.gov, official_award, 6358 bytes, sha256 `5f492fc38173b4c5…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA880712C0011_9700_-NONE-_-NONE-/

### LHX → `LB5KVANFKPY7`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:lb5kvanfkpy7` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-lb5kvanfkpy7` (USAspending.gov, official_award, 6622 bytes, sha256 `59648d9bb1aa3ba9…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_M6785423F2096_9700_M6785422D2090_9700/

### LHX → `LHJPD6T16EV9`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:lhjpd6t16ev9` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-lhjpd6t16ev9` (USAspending.gov, official_award, 7192 bytes, sha256 `f9712cdf7f25a230…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_F1962802C0010_9700_-NONE-_-NONE-/

### LHX → `LJNAJVPB3MW1`

- SEC name (ex21_subsidiary): **L3Harris Global Communications, Inc.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS GLOBAL COMMUNICATIONS, INC.**
- Normalized join key: `l3harris global communications inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-global-communications-inc` · `identifier:lhx:ljnajvpb3mw1` · `ownership:lhx:l3harris-global-communications-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-ljnajvpb3mw1` (USAspending.gov, official_award, 6585 bytes, sha256 `1fd03f8633c77b66…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0086_9700_W15P7T08DD248_9700/

### LHX → `N91TELG3HNB6`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:n91telg3hnb6` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-n91telg3hnb6` (USAspending.gov, official_award, 6333 bytes, sha256 `db84ca2bb31eb755…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA873014C0009_9700_-NONE-_-NONE-/

### LHX → `QM4EZDV15JL8`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:qm4ezdv15jl8` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-qm4ezdv15jl8` (USAspending.gov, official_award, 6837 bytes, sha256 `9dba2534747d15b0…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_1332KP23FNAAA0022_1330_1332KP23DNAAA0003_1330/

### LHX → `QWQYJDNHA561`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:qwqyjdnha561` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-qwqyjdnha561` (USAspending.gov, official_award, 6433 bytes, sha256 `976960f34e774e61…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA881919C0002_9700_-NONE-_-NONE-/

### LHX → `RDFKNPZNQ8E3`

- SEC name (ex21_subsidiary): **L3Harris Technologies Integrated Systems L.P.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES INTEGRATED SYSTEMS L.P.**
- Normalized join key: `l3harris technologies integrated systems l p`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-integrated-systems-l-p` · `identifier:lhx:rdfknpznq8e3` · `ownership:lhx:l3harris-technologies-integrated-systems-l-p`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-rdfknpznq8e3` (USAspending.gov, official_award, 6553 bytes, sha256 `c7b881ce07fae631…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_1524_9700_FA862011G4025_9700/

### LHX → `TZ67YHER84V7`

- SEC name (ex21_subsidiary): **L3HARRIS TECHNOLOGIES INC.**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS TECHNOLOGIES, INC.**
- Normalized join key: `l3harris technologies inc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-technologies-inc` · `identifier:lhx:tz67yher84v7` · `ownership:lhx:l3harris-technologies-inc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-tz67yher84v7` (USAspending.gov, official_award, 6391 bytes, sha256 `60a270687be92dbd…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_80GSFC23CA044_8000_-NONE-_-NONE-/

### LHX → `ZKE9UNL1NYF3`

- SEC name (ex21_subsidiary): **L3Harris NexGen Communications LLC**
- SEC document: `a10-kexhibit21cy25xq4.htm`
- USAspending recipient name(s): **L3HARRIS NEXGEN COMMUNICATIONS LLC**
- Normalized join key: `l3harris nexgen communications llc`
- Discovery ticker on the matched rows: LHX
- Graph rows: `legal:lhx:l3harris-nexgen-communications-llc` · `identifier:lhx:zke9unl1nyf3` · `ownership:lhx:l3harris-nexgen-communications-llc`
- Evidence:
    - `evidence:lhx-sec-ex21` (SEC, official_filing, 73990 bytes, sha256 `dd97d65fc4edcb89…`) https://www.sec.gov/Archives/edgar/data/202058/000020205826000015/a10-kexhibit21cy25xq4.htm
    - `evidence:lhx-usaspending-zke9unl1nyf3` (USAspending.gov, official_award, 6545 bytes, sha256 `e4837ab417967183…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002407C6311_9700_-NONE-_-NONE-/

### LMT → `CQWLW9XRQTH5`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORP**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:cqwlw9xrqth5` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-cqwlw9xrqth5` (USAspending.gov, official_award, 6815 bytes, sha256 `3ea0db24fd6e7d7c…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_F0470102C0002_9700_-NONE-_-NONE-/

### LMT → `CWM4UN76ZQW8`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:cwm4un76zqw8` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-cwm4un76zqw8` (USAspending.gov, official_award, 6360 bytes, sha256 `5a0fa16b8fcdd086…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ014716C0011_9700_-NONE-_-NONE-/

### LMT → `FYHNA5WC8XD7`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORP**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:fyhna5wc8xd7` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-fyhna5wc8xd7` (USAspending.gov, official_award, 6146 bytes, sha256 `911c4eb93efc835b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_DEAC0494AL85000_8900_-NONE-_-NONE-/

### LMT → `G4KDGE4JFFK7`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:g4kdge4jffk7` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-g4kdge4jffk7` (USAspending.gov, official_award, 6885 bytes, sha256 `e4ab6517bbe6c4f4…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA820518F0001_9700_FA820518D0001_9700/

### LMT → `H7PNSVNN5827`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:h7pnsvnn5827` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-h7pnsvnn5827` (USAspending.gov, official_award, 6139 bytes, sha256 `7db8793e00f8db00…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA868224CB001_9700_-NONE-_-NONE-/

### LMT → `HJP4JZG1FUL9`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:hjp4jzg1ful9` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-hjp4jzg1ful9` (USAspending.gov, official_award, 6225 bytes, sha256 `50bbe98985100a19…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0001911C0020_9700_-NONE-_-NONE-/

### LMT → `KMEVRAKJVBD3`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:kmevrakjvbd3` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-kmevrakjvbd3` (USAspending.gov, official_award, 6191 bytes, sha256 `6e57b0f1c43b2077…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0003024C0100_9700_-NONE-_-NONE-/

### LMT → `MJENSFHZJP11`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:mjensfhzjp11` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-mjensfhzjp11` (USAspending.gov, official_award, 6260 bytes, sha256 `0641becf942429a6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002411C2300_9700_-NONE-_-NONE-/

### LMT → `NB1ALNT2ZLN6`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:nb1alnt2zln6` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-nb1alnt2zln6` (USAspending.gov, official_award, 6254 bytes, sha256 `2fad0969619de15a…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_NAS998100_8000_-NONE-_-NONE-/

### LMT → `NGBVY5X32XZ5`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:ngbvy5x32xz5` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-ngbvy5x32xz5` (USAspending.gov, official_award, 6626 bytes, sha256 `a112af364227679b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ085621C0001_9700_-NONE-_-NONE-/

### LMT → `SJDEB3MKJEW5`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORP**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:sjdeb3mkjew5` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-sjdeb3mkjew5` (USAspending.gov, official_award, 6360 bytes, sha256 `73cfa4fc6693897c…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_F3365702C2000_9700_-NONE-_-NONE-/

### LMT → `VYGMKZA24SF1`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORP**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:vygmkza24sf1` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-vygmkza24sf1` (USAspending.gov, official_award, 6149 bytes, sha256 `40e8acdadcadbdc5…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_MSFC0199911DNAS800016_8000_-NONE-_-NONE-/

### LMT → `XFJMYSYFJEK4`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORPORATION**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:xfjmysyfjek4` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-xfjmysyfjek4` (USAspending.gov, official_award, 6317 bytes, sha256 `7a7aa9205b276914…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ014717C0032_9700_-NONE-_-NONE-/

### LMT → `ZFN2JJXBLZT3`

- SEC name (sec_registrant): **LOCKHEED MARTIN CORP**
- SEC document: `lmt-20251231.htm`
- USAspending recipient name(s): **LOCKHEED MARTIN CORP**
- Normalized join key: `lockheed martin corp`
- Discovery ticker on the matched rows: LMT
- Graph rows: `legal:lmt:lockheed-martin-corp` · `identifier:lmt:zfn2jjxblzt3` · `issuer-identity:lmt:lockheed-martin-corp`
- Evidence:
    - `evidence:lmt-sec-10k` (SEC, official_filing, 2909179 bytes, sha256 `252829a67a8ce782…`) https://www.sec.gov/Archives/edgar/data/936468/000162828026004195/lmt-20251231.htm
    - `evidence:lmt-usaspending-zfn2jjxblzt3` (USAspending.gov, official_award, 6305 bytes, sha256 `e88816e44ee5a977…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0003904C2009_9700_-NONE-_-NONE-/

### NOC → `D8QQPFNYJD63`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORP**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:d8qqpfnyjd63` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-d8qqpfnyjd63` (USAspending.gov, official_award, 6520 bytes, sha256 `12df4a34eb63b0e1…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA821920C0006_9700_-NONE-_-NONE-/

### NOC → `DE6HN4VGM3R1`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:de6hn4vgm3r1` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-de6hn4vgm3r1` (USAspending.gov, official_award, 6282 bytes, sha256 `b03f4a1d4b6eb136…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_M6785407C2072_9700_-NONE-_-NONE-/

### NOC → `DJUCEANK2KP4`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:djuceank2kp4` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-djuceank2kp4` (USAspending.gov, official_award, 6361 bytes, sha256 `2d9c2db8672e2fc3…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_70B02C20C00000024_7014_-NONE-_-NONE-/

### NOC → `E4X3BLZPPPX3`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:e4x3blzpppx3` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-e4x3blzpppx3` (USAspending.gov, official_award, 6492 bytes, sha256 `b51c9b6b6b75fe3b…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0008_9700_FA862612D2137_9700/

### NOC → `EH8UKZ6TML75`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:eh8ukz6tml75` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-eh8ukz6tml75` (USAspending.gov, official_award, 7202 bytes, sha256 `8db3d265dfbdc70a…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_8402_9700_H9500110D0001_9700/

### NOC → `EHBBTWLFSMW1`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:ehbbtwlfsmw1` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-ehbbtwlfsmw1` (USAspending.gov, official_award, 6525 bytes, sha256 `e22794d6e7028f70…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002417C6327_9700_-NONE-_-NONE-/

### NOC → `F9PAEKAAXGB6`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:f9paekaaxgb6` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-f9paekaaxgb6` (USAspending.gov, official_award, 6195 bytes, sha256 `d1feda198c19d053…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ014711C0006_9700_-NONE-_-NONE-/

### NOC → `FNBAMFZ3GD53`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:fnbamfz3gd53` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-fnbamfz3gd53` (USAspending.gov, official_award, 7478 bytes, sha256 `9b2b967dce536545…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ014718F0022_9700_HQ014718D0005_9700/

### NOC → `FVSEZFPCQ316`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:fvsezfpcq316` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-fvsezfpcq316` (USAspending.gov, official_award, 6464 bytes, sha256 `594ed35bc14479fd…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA865923FB006_9700_FA865621DA014_9700/

### NOC → `G7LEFNAN9J74`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:g7lefnan9j74` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-g7lefnan9j74` (USAspending.gov, official_award, 6731 bytes, sha256 `519f1727df04c27a…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_F4261098C0001_9700_-NONE-_-NONE-/

### NOC → `GHKDJMJNPL13`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:ghkdjmjnpl13` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-ghkdjmjnpl13` (USAspending.gov, official_award, 6623 bytes, sha256 `fdb1d7f311f8d396…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0001_9700_W91QUZ07D0005_9700/

### NOC → `GUVUU89P78Q3`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:guvuu89p78q3` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-guvuu89p78q3` (USAspending.gov, official_award, 6847 bytes, sha256 `95d8c34a65fab415…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ072719F1403_9700_HQ072716D0004_9700/

### NOC → `GWFBQY413N79`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:gwfbqy413n79` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-gwfbqy413n79` (USAspending.gov, official_award, 6660 bytes, sha256 `7357eea799f1525d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA854019C0001_9700_-NONE-_-NONE-/

### NOC → `H9M6J1PND9M3`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:h9m6j1pnd9m3` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-h9m6j1pnd9m3` (USAspending.gov, official_award, 6607 bytes, sha256 `137b3266cf9a5a60…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA861517C6047_9700_-NONE-_-NONE-/

### NOC → `JRVLDEXMYDK8`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORP**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:jrvldexmydk8` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-jrvldexmydk8` (USAspending.gov, official_award, 6385 bytes, sha256 `b76008ce6d3f56e1…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0002_9700_FA861614D6060_9700/

### NOC → `LAHZNLNSANJ7`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:lahznlnsanj7` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-lahznlnsanj7` (USAspending.gov, official_award, 6957 bytes, sha256 `56f25c6729a79cf1…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_28321318FDS030243_2800_SS001760017_2800/

### NOC → `LALWKM623MU7`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:lalwkm623mu7` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-lalwkm623mu7` (USAspending.gov, official_award, 6479 bytes, sha256 `de4ce6ef41bc88c8…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0003_9700_FA862015D3009_9700/

### NOC → `LCV2N9FVV739`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:lcv2n9fvv739` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-lcv2n9fvv739` (USAspending.gov, official_award, 6402 bytes, sha256 `3e4c3d95854454f7…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0003019C0015_9700_-NONE-_-NONE-/

### NOC → `LEMLXG994AU3`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:lemlxg994au3` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-lemlxg994au3` (USAspending.gov, official_award, 6387 bytes, sha256 `40eb7dc328f17f71…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA872609C0010_9700_-NONE-_-NONE-/

### NOC → `LRVQERN7YNH9`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:lrvqern7ynh9` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-lrvqern7ynh9` (USAspending.gov, official_award, 7455 bytes, sha256 `a8a31bed42586484…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_NNM07AA75C_8000_-NONE-_-NONE-/

### NOC → `PDKLLA6Q11N4`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:pdklla6q11n4` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-pdklla6q11n4` (USAspending.gov, official_award, 6413 bytes, sha256 `528a974852844e28…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002417C6311_9700_-NONE-_-NONE-/

### NOC → `PK8PM2GNVMP8`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:pk8pm2gnvmp8` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-pk8pm2gnvmp8` (USAspending.gov, official_award, 6591 bytes, sha256 `f1b8c9dbf06bff6c…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0162_9700_F0960300D0210_9700/

### NOC → `Q11ZHUFBW741`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:q11zhufbw741` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-q11zhufbw741` (USAspending.gov, official_award, 6904 bytes, sha256 `d62e94a5490f2099…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_NNG15VE05D_8000_NNG10AZ13B_8000/

### NOC → `T9XKQSKMW4J1`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:t9xkqskmw4j1` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-t9xkqskmw4j1` (USAspending.gov, official_award, 6875 bytes, sha256 `550b52c2c8b1ccaf…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_F1962800C0100_9700_-NONE-_-NONE-/

### NOC → `U6UKKQU345T7`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:u6ukkqu345t7` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-u6ukkqu345t7` (USAspending.gov, official_award, 6870 bytes, sha256 `62f7a43e57e11b79…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HQ085622F0001_9700_HQ085622D0001_9700/

### NOC → `U6V4EWXNS1D8`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:u6v4ewxns1d8` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-u6v4ewxns1d8` (USAspending.gov, official_award, 7114 bytes, sha256 `5140b854c25fa477…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_NNG11XA04C_8000_-NONE-_-NONE-/

### NOC → `ULU9F3WMEH66`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:ulu9f3wmeh66` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-ulu9f3wmeh66` (USAspending.gov, official_award, 6272 bytes, sha256 `a1ad9c901dac6e55…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W15QKN13C0074_9700_-NONE-_-NONE-/

### NOC → `VSBAFMDKTWL4`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:vsbafmdktwl4` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-vsbafmdktwl4` (USAspending.gov, official_award, 6882 bytes, sha256 `6025458841cdf444…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_F0470102C0009_9700_-NONE-_-NONE-/

### NOC → `WL6XPAJVBK83`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORP**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:wl6xpajvbk83` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-wl6xpajvbk83` (USAspending.gov, official_award, 6414 bytes, sha256 `2ea7968042b0eeb3…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA821917C0002_9700_-NONE-_-NONE-/

### NOC → `WNFAAJU8F1X1`

- SEC name (ex21_subsidiary): **Northrop Grumman Systems Corporation**
- SEC document: `noc-12312025xex21.htm`
- USAspending recipient name(s): **NORTHROP GRUMMAN SYSTEMS CORPORATION**
- Normalized join key: `northrop grumman systems corp`
- Discovery ticker on the matched rows: NOC
- Graph rows: `legal:noc:northrop-grumman-systems-corp` · `identifier:noc:wnfaaju8f1x1` · `ownership:noc:northrop-grumman-systems-corp`
- Evidence:
    - `evidence:noc-sec-ex21` (SEC, official_filing, 5617 bytes, sha256 `82a54bd52084bbdb…`) https://www.sec.gov/Archives/edgar/data/1133421/000113342126000003/noc-12312025xex21.htm
    - `evidence:noc-usaspending-wnfaaju8f1x1` (USAspending.gov, official_award, 6030 bytes, sha256 `af381cbe6162a214…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W58RGZ13C0010_9700_-NONE-_-NONE-/

### PLTR → `FSY4LVSBGWB7`

- SEC name (sec_registrant): **Palantir Technologies Inc.**
- SEC document: `pltr-20251231.htm`
- USAspending recipient name(s): **PALANTIR TECHNOLOGIES INC.**
- Normalized join key: `palantir technologies inc`
- Discovery ticker on the matched rows: PLTR
- **Already present in the published graph** — merge, do not duplicate.
- Graph rows: `legal:pltr:palantir-technologies-inc` · `identifier:pltr:fsy4lvsbgwb7` · `issuer-identity:pltr:palantir-technologies-inc`
- Evidence:
    - `evidence:pltr-sec-10k` (SEC, official_filing, 2192014 bytes, sha256 `a4fef9542c4d1a99…`) https://www.sec.gov/Archives/edgar/data/1321655/000132165526000011/pltr-20251231.htm
    - `evidence:pltr-usaspending-fsy4lvsbgwb7` (USAspending.gov, official_award, 6911 bytes, sha256 `1bff8eb4ba6e31f6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_12314426F0126_1205_12314426A0009_1205/

### PLTR → `HNN4F9JZWDY8`

- SEC name (ex21_subsidiary): **Palantir USG, Inc.**
- SEC document: `a2025fyexhibit211.htm`
- USAspending recipient name(s): **PALANTIR USG INC**
- Normalized join key: `palantir usg inc`
- Discovery ticker on the matched rows: PLTR
- **Already present in the published graph** — merge, do not duplicate.
- Graph rows: `legal:pltr:palantir-usg-inc` · `identifier:pltr:hnn4f9jzwdy8` · `ownership:pltr:palantir-usg-inc`
- Evidence:
    - `evidence:pltr-sec-ex21` (SEC, official_filing, 27169 bytes, sha256 `a139ad357b80c8de…`) https://www.sec.gov/Archives/edgar/data/1321655/000132165526000011/a2025fyexhibit211.htm
    - `evidence:pltr-usaspending-hnn4f9jzwdy8` (USAspending.gov, official_award, 6596 bytes, sha256 `e67e267378b30dbe…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_19AQMM22F7768_1900_19AQMM22A0249_1900/

### RTX → `ENC9Y8JGL3E9`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:enc9y8jgl3e9` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-enc9y8jgl3e9` (USAspending.gov, official_award, 6336 bytes, sha256 `92687180e71a4313…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002414C5315_9700_-NONE-_-NONE-/

### RTX → `F1ZBMFDJMGL3`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:f1zbmfdjmgl3` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-f1zbmfdjmgl3` (USAspending.gov, official_award, 6538 bytes, sha256 `930eb5fe4ded1fca…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA870514C0001_9700_-NONE-_-NONE-/

### RTX → `HEBCLD22EJD1`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:hebcld22ejd1` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-hebcld22ejd1` (USAspending.gov, official_award, 6206 bytes, sha256 `f3ac6943ea83e7d5…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA861124CB001_9700_-NONE-_-NONE-/

### RTX → `JLWLJXQ3M995`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:jlwljxq3m995` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-jlwljxq3m995` (USAspending.gov, official_award, 6543 bytes, sha256 `3abbdd8612ed48d4…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_1332KP18CNEEJ0005_1330_-NONE-_-NONE-/

### RTX → `LWF3QUSCDNG1`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:lwf3quscdng1` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-lwf3quscdng1` (USAspending.gov, official_award, 6120 bytes, sha256 `f9c0596d31280972…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002405C5346_9700_-NONE-_-NONE-/

### RTX → `MZK8TCNF24G2`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:mzk8tcnf24g2` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-mzk8tcnf24g2` (USAspending.gov, official_award, 6379 bytes, sha256 `471aaa3f73a424db…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA873017C0010_9700_-NONE-_-NONE-/

### RTX → `NBSLHP77ZJQ1`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:nbslhp77zjq1` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-nbslhp77zjq1` (USAspending.gov, official_award, 6608 bytes, sha256 `2a7a0fabfe72e0f2…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0001916C0002_9700_-NONE-_-NONE-/

### RTX → `QN1BCFY7JDJ5`

- SEC name (sec_registrant): **RTX Corp**
- SEC document: `rtx-20251231.htm`
- USAspending recipient name(s): **RTX CORPORATION**
- Normalized join key: `rtx corp`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:rtx-corp` · `identifier:rtx:qn1bcfy7jdj5` · `issuer-identity:rtx:rtx-corp`
- Evidence:
    - `evidence:rtx-sec-10k` (SEC, official_filing, 3685295 bytes, sha256 `9a8c294d9979aee2…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/rtx-20251231.htm
    - `evidence:rtx-usaspending-qn1bcfy7jdj5` (USAspending.gov, official_award, 6611 bytes, sha256 `e613febcad8a62b3…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA812424F0001_9700_FA812418D0001_9700/

### RTX → `VTEWM5QSE598`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:vtewm5qse598` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-vtewm5qse598` (USAspending.gov, official_award, 6713 bytes, sha256 `257ed4af92356837…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA865622FA071_9700_FA865621DA004_9700/

### RTX → `XSV6AZJ6SDJ7`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:xsv6azj6sdj7` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-xsv6azj6sdj7` (USAspending.gov, official_award, 6907 bytes, sha256 `77c548550de17c29…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPRBL123F0004_9700_SPRBL115D0017_9700/

### RTX → `YD6LTFVUZNG1`

- SEC name (ex21_subsidiary): **Raytheon Company**
- SEC document: `exhibit212025-12x3110xk.htm`
- USAspending recipient name(s): **RAYTHEON COMPANY**
- Normalized join key: `raytheon co`
- Discovery ticker on the matched rows: RTX
- Graph rows: `legal:rtx:raytheon-co` · `identifier:rtx:yd6ltfvuzng1` · `ownership:rtx:raytheon-co`
- Evidence:
    - `evidence:rtx-sec-ex21` (SEC, official_filing, 20604 bytes, sha256 `4a20f201f9bfaff9…`) https://www.sec.gov/Archives/edgar/data/101829/000010182926000006/exhibit212025-12x3110xk.htm
    - `evidence:rtx-usaspending-yd6ltfvuzng1` (USAspending.gov, official_award, 6459 bytes, sha256 `d66bd39d09551815…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002419C5501_9700_-NONE-_-NONE-/

### TDG → `DAUKP7DYKYN3`

- SEC name (ex21_subsidiary): **AeroControlex Group, Inc.**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **AEROCONTROLEX GROUP, INC.**
- Normalized join key: `aerocontrolex group inc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:aerocontrolex-group-inc` · `identifier:tdg:daukp7dykyn3` · `ownership:tdg:aerocontrolex-group-inc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-daukp7dykyn3` (USAspending.gov, official_award, 6183 bytes, sha256 `cb120696fa72bacc…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0038322CD005_9700_-NONE-_-NONE-/

### TDG → `FZY7VTQEZ4G4`

- SEC name (ex21_subsidiary): **Arkwin Industries, Inc.**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **ARKWIN INDUSTRIES, INC.**
- Normalized join key: `arkwin industries inc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:arkwin-industries-inc` · `identifier:tdg:fzy7vtqez4g4` · `ownership:tdg:arkwin-industries-inc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-fzy7vtqez4g4` (USAspending.gov, official_award, 6133 bytes, sha256 `ac169499cc348c0e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0038323CB051_9700_-NONE-_-NONE-/

### TDG → `HGYAQNHL9CT1`

- SEC name (ex21_subsidiary): **PneuDraulics, Inc.**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **PNEUDRAULICS, INC.**
- Normalized join key: `pneudraulics inc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:pneudraulics-inc` · `identifier:tdg:hgyaqnhl9ct1` · `ownership:tdg:pneudraulics-inc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-hgyaqnhl9ct1` (USAspending.gov, official_award, 6142 bytes, sha256 `77d8545cbd4a88b9…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0038325PT093_9700_-NONE-_-NONE-/

### TDG → `K78JMMAYPQ55`

- SEC name (ex21_subsidiary): **Telair US LLC**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **TELAIR US LLC**
- Normalized join key: `telair us llc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:telair-us-llc` · `identifier:tdg:k78jmmaypq55` · `ownership:tdg:telair-us-llc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-k78jmmaypq55` (USAspending.gov, official_award, 6267 bytes, sha256 `c2f3d15a485a8c40…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N6833520C0955_9700_-NONE-_-NONE-/

### TDG → `L3C5CZERQMK3`

- SEC name (ex21_subsidiary): **AeroControlex Group, Inc.**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **AEROCONTROLEX GROUP, INC.**
- Normalized join key: `aerocontrolex group inc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:aerocontrolex-group-inc` · `identifier:tdg:l3c5czerqmk3` · `ownership:tdg:aerocontrolex-group-inc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-l3c5czerqmk3` (USAspending.gov, official_award, 6406 bytes, sha256 `c60aa842e616b1f7…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0038322FBD00_9700_N0038317GBD01_9700/

### TDG → `M7TATW5PKF14`

- SEC name (ex21_subsidiary): **CEF Industries, LLC**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **CEF INDUSTRIES, LLC**
- Normalized join key: `cef industries llc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:cef-industries-llc` · `identifier:tdg:m7tatw5pkf14` · `ownership:tdg:cef-industries-llc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-m7tatw5pkf14` (USAspending.gov, official_award, 6577 bytes, sha256 `0089d2f4ac3feed3…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPE4A721F5979_9700_SPE4A721D0085_9700/

### TDG → `NUA1MAF1GP59`

- SEC name (ex21_subsidiary): **Champion Aerospace LLC**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **CHAMPION AEROSPACE LLC**
- Normalized join key: `champion aerospace llc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:champion-aerospace-llc` · `identifier:tdg:nua1maf1gp59` · `ownership:tdg:champion-aerospace-llc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-nua1maf1gp59` (USAspending.gov, official_award, 6095 bytes, sha256 `35fce33295369bb5…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0038322C004H_9700_-NONE-_-NONE-/

### TDG → `Q7CGW8NCRGJ6`

- SEC name (ex21_subsidiary): **AeroControlex Group, Inc.**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **AEROCONTROLEX GROUP, INC.**
- Normalized join key: `aerocontrolex group inc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:aerocontrolex-group-inc` · `identifier:tdg:q7cgw8ncrgj6` · `ownership:tdg:aerocontrolex-group-inc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-q7cgw8ncrgj6` (USAspending.gov, official_award, 6645 bytes, sha256 `ec0d7c4f93414890…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPE4AX22F1815_9700_SPE4AX18D9442_9700/

### TDG → `R3XCABD7U5H4`

- SEC name (ex21_subsidiary): **Whippany Actuation Systems, LLC**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **WHIPPANY ACTUATION SYSTEMS, LLC**
- Normalized join key: `whippany actuation systems llc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:whippany-actuation-systems-llc` · `identifier:tdg:r3xcabd7u5h4` · `ownership:tdg:whippany-actuation-systems-llc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-r3xcabd7u5h4` (USAspending.gov, official_award, 6191 bytes, sha256 `a36e2c19b76e291e…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0038319CF008_9700_-NONE-_-NONE-/

### TDG → `UJ9DLYWUAKD8`

- SEC name (ex21_subsidiary): **Acme Aerospace, Inc.**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **ACME AEROSPACE, INC.**
- Normalized join key: `acme aerospace inc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:acme-aerospace-inc` · `identifier:tdg:uj9dlywuakd8` · `ownership:tdg:acme-aerospace-inc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-uj9dlywuakd8` (USAspending.gov, official_award, 6462 bytes, sha256 `d15860f6a20b024f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_SPE7LX22F463N_9700_SPE7LX21D0090_9700/

### TDG → `W1EEJS3KUKX7`

- SEC name (ex21_subsidiary): **Skurka Aerospace Inc.**
- SEC document: `exhibit211tdg202510-k.htm`
- USAspending recipient name(s): **SKURKA AEROSPACE INC**
- Normalized join key: `skurka aerospace inc`
- Discovery ticker on the matched rows: TDG
- Graph rows: `legal:tdg:skurka-aerospace-inc` · `identifier:tdg:w1eejs3kukx7` · `ownership:tdg:skurka-aerospace-inc`
- Evidence:
    - `evidence:tdg-sec-ex21` (SEC, official_filing, 123706 bytes, sha256 `a25ebe2e32d694e9…`) https://www.sec.gov/Archives/edgar/data/1260221/000126022125000081/exhibit211tdg202510-k.htm
    - `evidence:tdg-usaspending-w1eejs3kukx7` (USAspending.gov, official_award, 6058 bytes, sha256 `f71660ab684b8e92…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0038322CB041_9700_-NONE-_-NONE-/

### TDY → `EKLDZ9NC5BQ6`

- SEC name (ex21_subsidiary): **Teledyne Energy Systems, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE ENERGY SYSTEMS, INC**
- Normalized join key: `teledyne energy systems inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-energy-systems-inc` · `identifier:tdy:ekldz9nc5bq6` · `ownership:tdy:teledyne-energy-systems-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-ekldz9nc5bq6` (USAspending.gov, official_award, 6438 bytes, sha256 `e75ba3915c7ca7ef…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_DENE0008392_8900_-NONE-_-NONE-/

### TDY → `F11UCKNJJHX8`

- SEC name (ex21_subsidiary): **Teledyne FLIR, LLC**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR, LLC**
- Normalized join key: `teledyne flir llc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-llc` · `identifier:tdy:f11ucknjjhx8` · `ownership:tdy:teledyne-flir-llc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-f11ucknjjhx8` (USAspending.gov, official_award, 6631 bytes, sha256 `8f549f0c1c76350a…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0035_9700_W9113M15D0001_9700/

### TDY → `FBRSJB6V4LW8`

- SEC name (ex21_subsidiary): **Teledyne Brown Engineering, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE BROWN ENGINEERING, INC.**
- Normalized join key: `teledyne brown engineering inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-brown-engineering-inc` · `identifier:tdy:fbrsjb6v4lw8` · `ownership:tdy:teledyne-brown-engineering-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-fbrsjb6v4lw8` (USAspending.gov, official_award, 6916 bytes, sha256 `374c2ef20c7210b6…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0002_9700_W9113M14D0005_9700/

### TDY → `G7WGK6L5ES76`

- SEC name (ex21_subsidiary): **Teledyne FLIR Defense, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR DEFENSE, INC.**
- Normalized join key: `teledyne flir defense inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-defense-inc` · `identifier:tdy:g7wgk6l5es76` · `ownership:tdy:teledyne-flir-defense-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-g7wgk6l5es76` (USAspending.gov, official_award, 6763 bytes, sha256 `7cefce075d140395…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_70Z03822FE0000040_7008_70Z03822DE0000002_7008/

### TDY → `PAH8M4BJACA5`

- SEC name (ex21_subsidiary): **Teledyne Instruments, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE INSTRUMENTS INC**
- Normalized join key: `teledyne instruments inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-instruments-inc` · `identifier:tdy:pah8m4bjaca5` · `ownership:tdy:teledyne-instruments-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-pah8m4bjaca5` (USAspending.gov, official_award, 6164 bytes, sha256 `e9e218c65a65c138…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0010426CNA02_9700_-NONE-_-NONE-/

### TDY → `QBXYRAGMYG93`

- SEC name (ex21_subsidiary): **Teledyne Controls, LLC**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE CONTROLS, LLC**
- Normalized join key: `teledyne controls llc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-controls-llc` · `identifier:tdy:qbxyragmyg93` · `ownership:tdy:teledyne-controls-llc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-qbxyragmyg93` (USAspending.gov, official_award, 6690 bytes, sha256 `f0d8fd5aa619a4d4…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0001919F2760_9700_N6833516G0008_9700/

### TDY → `R94BXDU1Y8X4`

- SEC name (ex21_subsidiary): **Teledyne FLIR Defense, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR DEFENSE, INC.**
- Normalized join key: `teledyne flir defense inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-defense-inc` · `identifier:tdy:r94bxdu1y8x4` · `ownership:tdy:teledyne-flir-defense-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-r94bxdu1y8x4` (USAspending.gov, official_award, 6872 bytes, sha256 `d9da4c889f2d33c1…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_6973GH20F01205_6920_6973GH18D00085_6920/

### TDY → `RR8KCXLJLT15`

- SEC name (ex21_subsidiary): **Teledyne FLIR Unmanned Ground Systems, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR UNMANNED GROUND SYSTEMS, INC**
- Normalized join key: `teledyne flir unmanned ground systems inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-unmanned-ground-systems-inc` · `identifier:tdy:rr8kcxljlt15` · `ownership:tdy:teledyne-flir-unmanned-ground-systems-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-rr8kcxljlt15` (USAspending.gov, official_award, 6852 bytes, sha256 `f2ee28c01c7eedfa…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_W56HZV19F0354_9700_W56HZV19D0031_9700/

### TDY → `SPTTT1DJTAK3`

- SEC name (ex21_subsidiary): **Teledyne FLIR Defense, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR DEFENSE, INC**
- Normalized join key: `teledyne flir defense inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-defense-inc` · `identifier:tdy:spttt1djtak3` · `ownership:tdy:teledyne-flir-defense-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-spttt1djtak3` (USAspending.gov, official_award, 6809 bytes, sha256 `571c9fb39a798158…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HSHQDC09C00057_7001_-NONE-_-NONE-/

### TDY → `SW2JX7CHDT85`

- SEC name (ex21_subsidiary): **Teledyne FLIR Defense, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR DEFENSE, INC.**
- Normalized join key: `teledyne flir defense inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-defense-inc` · `identifier:tdy:sw2jx7chdt85` · `ownership:tdy:teledyne-flir-defense-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-sw2jx7chdt85` (USAspending.gov, official_award, 6354 bytes, sha256 `d1467326e8a45051…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HDTRA113C0003_9700_-NONE-_-NONE-/

### TDY → `VEM6L3BCUJ51`

- SEC name (ex21_subsidiary): **Teledyne FLIR Defense, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR DEFENSE, INC.**
- Normalized join key: `teledyne flir defense inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-defense-inc` · `identifier:tdy:vem6l3bcuj51` · `ownership:tdy:teledyne-flir-defense-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-vem6l3bcuj51` (USAspending.gov, official_award, 6722 bytes, sha256 `8b26cb2574f92b58…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0001_9700_W911NF12D0002_9700/

### TDY → `WQKMXY9FRUC5`

- SEC name (ex21_subsidiary): **Teledyne Scientific & Imaging, LLC**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE SCIENTIFIC & IMAGING, LLC**
- Normalized join key: `teledyne scientific & imaging llc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-scientific-imaging-llc` · `identifier:tdy:wqkmxy9fruc5` · `ownership:tdy:teledyne-scientific-imaging-llc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-wqkmxy9fruc5` (USAspending.gov, official_award, 6487 bytes, sha256 `96910061eff4bef9…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_80GSFC18C0095_8000_-NONE-_-NONE-/

### TDY → `XMKCVNPCKNF5`

- SEC name (ex21_subsidiary): **Teledyne Defense Electronics, LLC**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE DEFENSE ELECTRONICS, LLC**
- Normalized join key: `teledyne defense electronics llc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-defense-electronics-llc` · `identifier:tdy:xmkcvnpcknf5` · `ownership:tdy:teledyne-defense-electronics-llc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-xmkcvnpcknf5` (USAspending.gov, official_award, 6635 bytes, sha256 `8942f01fa9951986…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA852223F0040_9700_FA852223D0005_9700/

### TDY → `YLHLLLEUTKC1`

- SEC name (ex21_subsidiary): **Teledyne FLIR Defense, Inc.**
- SEC document: `tdy-ex21subsidiariesoftele.htm`
- USAspending recipient name(s): **TELEDYNE FLIR DEFENSE, INC.**
- Normalized join key: `teledyne flir defense inc`
- Discovery ticker on the matched rows: TDY
- Graph rows: `legal:tdy:teledyne-flir-defense-inc` · `identifier:tdy:ylhllleutkc1` · `ownership:tdy:teledyne-flir-defense-inc`
- Evidence:
    - `evidence:tdy-sec-ex21` (SEC, official_filing, 120809 bytes, sha256 `f4491495d53a88c7…`) https://www.sec.gov/Archives/edgar/data/1094285/000109428526000017/tdy-ex21subsidiariesoftele.htm
    - `evidence:tdy-usaspending-ylhllleutkc1` (USAspending.gov, official_award, 8195 bytes, sha256 `44974f88f4381a77…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_HSCG2315F2DA021_7008_GS03F099CA_4732/

### TXT → `DC2JUKFHNLN3`

- SEC name (ex21_subsidiary): **TRU Simulation + Training Inc.**
- SEC document: `q4202510k-exx21.htm`
- USAspending recipient name(s): **TRU SIMULATION + TRAINING INC**
- Normalized join key: `tru simulation training inc`
- Discovery ticker on the matched rows: TXT
- Graph rows: `legal:txt:tru-simulation-training-inc` · `identifier:txt:dc2jukfhnln3` · `ownership:txt:tru-simulation-training-inc`
- Evidence:
    - `evidence:txt-sec-ex21` (SEC, official_filing, 109338 bytes, sha256 `50d3e9fd6c717e14…`) https://www.sec.gov/Archives/edgar/data/217346/000021734626000006/q4202510k-exx21.htm
    - `evidence:txt-usaspending-dc2jukfhnln3` (USAspending.gov, official_award, 6231 bytes, sha256 `ea2948b5fa4a64f9…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA862112C6266_9700_-NONE-_-NONE-/

### TXT → `LH8RF2CKLWK5`

- SEC name (ex21_subsidiary): **Textron Aviation Inc.**
- SEC document: `q4202510k-exx21.htm`
- USAspending recipient name(s): **TEXTRON AVIATION INC**
- Normalized join key: `textron aviation inc`
- Discovery ticker on the matched rows: TXT
- Graph rows: `legal:txt:textron-aviation-inc` · `identifier:txt:lh8rf2cklwk5` · `ownership:txt:textron-aviation-inc`
- Evidence:
    - `evidence:txt-sec-ex21` (SEC, official_filing, 109338 bytes, sha256 `50d3e9fd6c717e14…`) https://www.sec.gov/Archives/edgar/data/217346/000021734626000006/q4202510k-exx21.htm
    - `evidence:txt-usaspending-lh8rf2cklwk5` (USAspending.gov, official_award, 6697 bytes, sha256 `50d969fcbbd1c625…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_6973GH23F01933_6920_6973GH23D00122_6920/

### TXT → `N5QUZAYGPKM3`

- SEC name (ex21_subsidiary): **Bell Textron Inc.**
- SEC document: `q4202510k-exx21.htm`
- USAspending recipient name(s): **BELL TEXTRON INC**
- Normalized join key: `bell textron inc`
- Discovery ticker on the matched rows: TXT
- Graph rows: `legal:txt:bell-textron-inc` · `identifier:txt:n5quzaygpkm3` · `ownership:txt:bell-textron-inc`
- Evidence:
    - `evidence:txt-sec-ex21` (SEC, official_filing, 109338 bytes, sha256 `50d3e9fd6c717e14…`) https://www.sec.gov/Archives/edgar/data/217346/000021734626000006/q4202510k-exx21.htm
    - `evidence:txt-usaspending-n5quzaygpkm3` (USAspending.gov, official_award, 6340 bytes, sha256 `acf56de73dd822ee…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0024_9700_N0001906G0001_9700/

### TXT → `R9MCJ6BRC8M7`

- SEC name (ex21_subsidiary): **Textron Systems Corporation**
- SEC document: `q4202510k-exx21.htm`
- USAspending recipient name(s): **TEXTRON SYSTEMS CORPORATION**
- Normalized join key: `textron systems corp`
- Discovery ticker on the matched rows: TXT
- Graph rows: `legal:txt:textron-systems-corp` · `identifier:txt:r9mcj6brc8m7` · `ownership:txt:textron-systems-corp`
- Evidence:
    - `evidence:txt-sec-ex21` (SEC, official_filing, 109338 bytes, sha256 `50d3e9fd6c717e14…`) https://www.sec.gov/Archives/edgar/data/217346/000021734626000006/q4202510k-exx21.htm
    - `evidence:txt-usaspending-r9mcj6brc8m7` (USAspending.gov, official_award, 6051 bytes, sha256 `662bac70d38c4fda…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA868211C0044_9700_-NONE-_-NONE-/

### TXT → `RSCJXUGJNGE3`

- SEC name (ex21_subsidiary): **Textron Aviation Defense LLC**
- SEC document: `q4202510k-exx21.htm`
- USAspending recipient name(s): **TEXTRON AVIATION DEFENSE LLC**
- Normalized join key: `textron aviation defense llc`
- Discovery ticker on the matched rows: TXT
- Graph rows: `legal:txt:textron-aviation-defense-llc` · `identifier:txt:rscjxugjnge3` · `ownership:txt:textron-aviation-defense-llc`
- Evidence:
    - `evidence:txt-sec-ex21` (SEC, official_filing, 109338 bytes, sha256 `50d3e9fd6c717e14…`) https://www.sec.gov/Archives/edgar/data/217346/000021734626000006/q4202510k-exx21.htm
    - `evidence:txt-usaspending-rscjxugjnge3` (USAspending.gov, official_award, 6469 bytes, sha256 `b208baac2b8e4056…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0015_9700_FA861707D6151_9700/

### TXT → `SNJ8YY61GB95`

- SEC name (ex21_subsidiary): **Textron Systems Corporation**
- SEC document: `q4202510k-exx21.htm`
- USAspending recipient name(s): **TEXTRON SYSTEMS CORPORATION**
- Normalized join key: `textron systems corp`
- Discovery ticker on the matched rows: TXT
- Graph rows: `legal:txt:textron-systems-corp` · `identifier:txt:snj8yy61gb95` · `ownership:txt:textron-systems-corp`
- Evidence:
    - `evidence:txt-sec-ex21` (SEC, official_filing, 109338 bytes, sha256 `50d3e9fd6c717e14…`) https://www.sec.gov/Archives/edgar/data/217346/000021734626000006/q4202510k-exx21.htm
    - `evidence:txt-usaspending-snj8yy61gb95` (USAspending.gov, official_award, 6671 bytes, sha256 `721d6c13ed91221f…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0004_9700_W58RGZ17D0006_9700/

### TXT → `WEE9WFHMACH9`

- SEC name (ex21_subsidiary): **Textron Systems Corporation**
- SEC document: `q4202510k-exx21.htm`
- USAspending recipient name(s): **TEXTRON SYSTEMS CORP**
- Normalized join key: `textron systems corp`
- Discovery ticker on the matched rows: TXT
- Graph rows: `legal:txt:textron-systems-corp` · `identifier:txt:wee9wfhmach9` · `ownership:txt:textron-systems-corp`
- Evidence:
    - `evidence:txt-sec-ex21` (SEC, official_filing, 109338 bytes, sha256 `50d3e9fd6c717e14…`) https://www.sec.gov/Archives/edgar/data/217346/000021734626000006/q4202510k-exx21.htm
    - `evidence:txt-usaspending-wee9wfhmach9` (USAspending.gov, official_award, 6097 bytes, sha256 `a878848a5f47aca7…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_N0002412C2401_9700_-NONE-_-NONE-/

### VSAT → `DUD5VV6N1AD6`

- SEC name (ex21_subsidiary): **TrellisWare Technologies, Inc.**
- SEC document: `vsat-ex21_1.htm`
- USAspending recipient name(s): **TRELLISWARE TECHNOLOGIES INC**
- Normalized join key: `trellisware technologies inc`
- Discovery ticker on the matched rows: VSAT
- Graph rows: `legal:vsat:trellisware-technologies-inc` · `identifier:vsat:dud5vv6n1ad6` · `ownership:vsat:trellisware-technologies-inc`
- Evidence:
    - `evidence:vsat-sec-ex21` (SEC, official_filing, 210952 bytes, sha256 `4c034a64c306aa5b…`) https://www.sec.gov/Archives/edgar/data/797721/000119312526248290/vsat-ex21_1.htm
    - `evidence:vsat-usaspending-dud5vv6n1ad6` (USAspending.gov, official_award, 6598 bytes, sha256 `d147fb19419bb7e8…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA875020C0241_9700_-NONE-_-NONE-/

### VSAT → `KMVJW2X3H2F5`

- SEC name (sec_registrant): **VIASAT INC**
- SEC document: `vsat-20260331.htm`
- USAspending recipient name(s): **VIASAT INC**
- Normalized join key: `viasat inc`
- Discovery ticker on the matched rows: VSAT
- Graph rows: `legal:vsat:viasat-inc` · `identifier:vsat:kmvjw2x3h2f5` · `issuer-identity:vsat:viasat-inc`
- Evidence:
    - `evidence:vsat-sec-10k` (SEC, official_filing, 5421212 bytes, sha256 `a15905d6bb3028dd…`) https://www.sec.gov/Archives/edgar/data/797721/000119312526248290/vsat-20260331.htm
    - `evidence:vsat-usaspending-kmvjw2x3h2f5` (USAspending.gov, official_award, 6419 bytes, sha256 `83c1502f7312e803…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_FA875018C0135_9700_-NONE-_-NONE-/

### VSAT → `L9Z1ASN3B8E7`

- SEC name (sec_registrant): **VIASAT INC**
- SEC document: `vsat-20260331.htm`
- USAspending recipient name(s): **VIASAT INC**
- Normalized join key: `viasat inc`
- Discovery ticker on the matched rows: VSAT
- Graph rows: `legal:vsat:viasat-inc` · `identifier:vsat:l9z1asn3b8e7` · `issuer-identity:vsat:viasat-inc`
- Evidence:
    - `evidence:vsat-sec-10k` (SEC, official_filing, 5421212 bytes, sha256 `a15905d6bb3028dd…`) https://www.sec.gov/Archives/edgar/data/797721/000119312526248290/vsat-20260331.htm
    - `evidence:vsat-usaspending-l9z1asn3b8e7` (USAspending.gov, official_award, 6488 bytes, sha256 `3017cd60cdf0850d…`) https://api.usaspending.gov/api/v2/awards/CONT_AWD_0004_9700_H9222218D0005_9700/

## Issuers with no proposed edge, and why

| Issuer | Cause | EX-21 names kept / rejected | What it means |
| --- | --- | --- | --- |
| BWXT | `no_collected_recipients` | 17 / 13 | The collected USAspending award panel holds zero rows for this issuer's discovery scope. This is an upstream COLLECTION gap, not a matching gap — nothing was available to join against. |
| GE | `no_exact_match` | 69 / 47 | No exact issuer evidence: not one collected recipient name equals this registrant or any EX-21 subsidiary under the documented normalization. The collected recipients are other companies. This is a finished answer, not an outstanding mapping task — read it against the 69 EX-21 name(s) extracted and the 47 line(s) rejected, both listed here. |

- BWXT discarded EX-21 line `Canada` (no_recognised_corporate_form_tail)
- BWXT discarded EX-21 line `Delaware` (no_recognised_corporate_form_tail)
- BWXT discarded EX-21 line `Document` (no_recognised_corporate_form_tail)
- BWXT discarded EX-21 line `EX-21.1` (no_recognised_corporate_form_tail)
- BWXT discarded EX-21 line `EXHIBIT 21.1` (matched_noise_filter)
- GE discarded EX-21 line `AFFILIATES OF REGISTRANT INCLUDED IN REGISTRANT’S FINANCIAL STATEMENTS` (no_recognised_corporate_form_tail)
- GE discarded EX-21 line `Australia` (no_recognised_corporate_form_tail)
- GE discarded EX-21 line `Bank BPH SpóBka Akcyjna` (no_recognised_corporate_form_tail)
- GE discarded EX-21 line `Bermuda` (no_recognised_corporate_form_tail)
- GE discarded EX-21 line `Brazil` (no_recognised_corporate_form_tail)

## To publish

- [ ] Re-mint graph_id from recipient-graph:candidate:… to recipient-graph:reviewed:… once the rows are actually reviewed.
- [ ] Merge with the currently published graph rather than replacing it; already_in_published_graph flags the overlap.
- [ ] Read every proposed edge below against its cited evidence URLs and delete the rows that do not survive.
- [ ] Update the structural counts asserted in tests/test_government_revenue_recipient_graph.py in the same change.

```
python3 -m scripts.curate_government_revenue_recipient_graph --input <reviewed-graph.json> --as-of 2026-08-07
```

## Limitations

- This is a CANDIDATE. No row here has been reviewed by a human, and verification_state='reviewed' records the assertion the analyst is being asked to make, not one that has been made.
- valid_from on every SEC-sourced claim is the 10-K period-of-report date. Widen it only with evidence that the relationship held earlier.
- Ownership relationships are proposed as wholly_owned because an EX-21 lists significant subsidiaries without economic share. A partial or joint-venture holding must be corrected by the analyst before publication.
- An issuer reported with no_exact_match has no exact issuer evidence; that is a finished answer, not an outstanding mapping task.
