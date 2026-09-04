# XPV2-SC-R3B.2 Data / Authority — quarantined first pass

- Frozen at: `2026-08-24T10:16:08Z`
- Reviewer freshness: fresh; no prior R3/R3B/R3B.1/R3B.2 participation and no memory or sibling-result access
- Dispatch head: `0e542f3eda09721f8a255a08bb9db09070090871`
- Frozen content SHA: `d0830a374795925ee1e55b66c0cc42e329ac172d`
- Candidate SHA-256: `4adb4b6245e8e4aa5b68c850a615461327c0a5d2e672e4c203d6ba32a3b8d53c`
- Candidate size: `5,506,871` bytes
- Manifest state: `in_review`
- Canonical carrier: PR #6337, draft/open, `claude/xpv2-sc-r3b2-build`, exact head above
- Superseded exclusion: PR #6336 is a distinct draft/open carrier at `d4863b6...`; its candidate was not opened
- Exact-head CI: run `32702450784`, completed/success at the dispatch head
- Main re-pin: `origin/main=263e7719c640517ca88504f1161d5abb75ccb1c4`; no overlapping material Sector Central producer, authority, design-law, or RIG source drift found

## Independent method

I read the production-before capture set and the 92-row baseline capability/task manifest, parsed all 21 embedded fixture payloads directly from the exact candidate, cross-checked producer-path cardinalities and values, and rendered the candidate independently with local headless Chrome. Independent screenshots:

- `critic_return/render/confluence-1440-en.png`, SHA-256 `22f70162ae1244007a33eb3f4587af5868e610b8c7e94ee496355c891ba41271`
- `critic_return/render/money-1440-en.png`, SHA-256 `d8e6f2f51de55b3bcde9b9dc909eec551e13fb88626f87ae34f238583662229b`

No builder receipt, evidence index, continuity file, adjudication, R3B.1 verdict/review, R3A authority pack, Design Doctrine, Product Design System, RIG law, or sibling result was used before this freeze.

## Frozen verdict

`BLOCK`

### FP-DA-001 — major — candidate/reference attribution

The Money & Breadth track-record presentation still creates a 21-day validation implication that the embedded producer does not support. `marketdata/index_leadership.json → track_record` says `is_context_only:true` and `proven={5:true,10:false,21:false,63:false}`. The candidate nevertheless derives the headline badge from the unqualified producer-level `track_record.verdict` and paints `Forward track record: Validated`; in the same block it prints 21-day statistics (`horizons["21"]`). The added qualification — `Context only · evidence proven at 5d · never sizes decisions` — is a meaningful improvement, but it does not neutralize the adjacent, stronger `Validated` badge tied visually to the 21-day statistics. A reasonable reader can still read those 21-day values as validated.

Smallest remedy: within this candidate/reference only, do not paint `Validated` as the displayed-horizon badge when the displayed horizon's `proven[21]` is false. Preserve the producer verdict as provenance if needed, but label the 21-day line `Measuring`/equivalent or explicitly bind `Validated` to `5d only` before the 21-day values. Do not alter producer data or invent a new verdict.

### First-pass strengths not to disturb

- Four-universe identity/order/counts render coherently from four distinct embedded payloads: S&P 500 `65`, Nasdaq-100 `12`, Russell-2000 `93`, Thematic Baskets `49`, in that exact DOM order.
- S&P `coverage.n_thin=48` remains separate from the 65 in-table rows; 31 of those in-table rows carry `reliability=low`. The visible coverage sentence says 48 are omitted, while the row marker says `Low confidence`, without adding a causal explanation.
- The Baskets payload has no `n_gateable`/`n_thin` contract and the candidate emits no Baskets thin/correction disclosure.
- Confluence stock-pick figures copy `double_gated.double_buy[].combined_score` and use production's `Conviction / 综合把握` label; visible values `0.60` and `0.54` match the fixture.
- Overview action rendering reads the producer lane arrays directly, folds `hold` then `avoid` into one `Stand aside` lane, retains producer order, and uses full-array lengths for counts. Theme score is presented as `Strength / 强度`; sector rows do not receive a fabricated numeric score.
- No correction/revision UI claim was found. Model-analysis wording is scoped to the model output rather than the deterministic narrative score.

## First-pass limits

- Production-before screenshots establish composition but not live network/access behavior; no production mutation or authenticated request was authorized.
- This pass did not evaluate sibling critics or any rationale/QA receipts by design.
- The initial independent renderer used local file transport and embedded fixtures; external production navigation was intentionally not executed.

