---
key: PROPHET-D5-CANONICAL-B1-EARNINGS-OVERLAP-ABSENT
claim: >
  The 2026-08-30 assertion that every committed natural B1 generation has zero
  accepted Earnings-covered ticker_at_observation overlap is false. That absence
  reading was produced by a structurally invalid falsifier that iterated the
  all_candidates.json envelope (a prophet.all_candidates/v1 dict) instead of
  .episodes. Envelope-aware reads of every currently committed natural generation
  find ACTIVE prophet.candidate_episode/v1 rows for AAPL, KBH, PHM and TOL; DHI
  remains absent. Ticker_at_observation overlap is not a lawful D5 join and does
  not by itself authorize implementation. The file key is retained as the original
  absence-investigation identifier; it is not a current-tense zero-overlap claim.
falsifier: >
  From the macro repository root run `python3 -c 'import json,pathlib,sys;
  covered={"AAPL","DHI","PHM","KBH","TOL"}; root=pathlib.Path("data/us_prophet_rank/episodes/generations");
  unwrap=lambda d: (d.get("episodes") if isinstance(d, dict) else d); hits={};
  [hits.setdefault(p.parent.name, sorted(covered & {str(r.get("ticker_at_observation") or "").upper()
  for r in (lambda e: e if isinstance(e, list) else sys.exit("unrecognized all_candidates envelope"))(unwrap(json.loads(p.read_text())))}))
  for p in sorted(root.glob("peg:*/all_candidates.json"))]; print(hits); sys.exit(0 if any(hits.values()) else 1)'`.
  An empty hits map, or every generation mapping to [], disproves the present
  ticker_at_observation overlap claim. A parser that iterates the top-level
  envelope instead of .episodes is not a valid falsifier.
so_what: >
  Do not use zero accepted B1×Earnings overlap as a present D5 gate. Do not join
  B1 to Earnings on ticker_at_observation. Hold implementation at
  NO_LAWFUL_REAL_VERTICAL until the owner-native issuer-CIK bridge and the remaining
  frozen Cell F identity/evidence gates are satisfied; ticker overlap alone does
  not authorize adapter code.
kind: data
verified_at: 2026-08-31
verified_by: >
  Envelope-aware command above against the three committed natural generations
  peg:c025bb50c45f319f989a4848249b8a85b65354143e3262f2ad09d07841311b08,
  peg:9afeb4f89ecc434c119f563424990d7b10b58bc75a30a0f275c74cf73465cfcc,
  and peg:881d604cc56968cfe921188f59e992c1652329416fa2bb2b4e9059a46616acc2.
  Each file is schema prophet.all_candidates/v1 with an episodes list of 467
  ACTIVE prophet.candidate_episode/v1 rows. Hits were AAPL/KBH/PHM/TOL in every
  generation; DHI was absent. The 2026-08-30 GitHub-search "no row" receipt at
  macro@418def12139f8a9d1ddc7a3abc82e57442095c96 is withdrawn as a structural
  false negative, not preserved as historical zero-overlap evidence.
scope:
  - macro
  - WS:PROPHET-US-V4-RECOVERY
  - data/us_prophet_rank/episodes/generations/
  - engine/company_intelligence/issuer_profiles.py
  - future prophet.intelligence_vector/v1
confidence: verified
---

## Boundary of the finding

This discovery no longer asserts canonical absence. It records that the 2026-08-30
zero-overlap claim failed its own runnable-falsifier duty: `all_candidates.json`
is a dict envelope (`coverage`, `episodes`, `generated_from`, `schema`,
`definition_era`), and iterating that object treats string keys as episode rows.

The live observation is **ticker_at_observation overlap on the accepted B1 episode
plane** for four of five Earnings-covered listed securities. That is still not a
lawful D5 vertical. Amendment A13 and the entrance hold forbid joining on ticker,
parsing `issuer_id` as a CIK, reading identity parquet, or copying the Earnings
issuer registry. `identity_epoch_state` on the overlapping rows is `provisional`.
The Data OS `IssuerMaster` public reader still has no issuer-to-CIK accessor.

DHI remains absent from the accepted episode plane. That is a coverage/intake fact,
not a reason to treat the other four names as missing.

The historical 2026-08-25 TURN WATCH observation remains useful archaeology and is
still not a D5 join key. Source-input presence and ticker_at_observation presence
are both weaker than a canonical economic-identity plus owner-native CIK join.
