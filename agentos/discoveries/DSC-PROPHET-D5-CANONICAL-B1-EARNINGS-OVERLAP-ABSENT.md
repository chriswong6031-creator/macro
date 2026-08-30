---
key: PROPHET-D5-CANONICAL-B1-EARNINGS-OVERLAP-ABSENT
claim: >
  The first three committed natural B1 generations contain zero accepted
  prophet.candidate_episode/v1 episodes for any Earnings-covered listed security
  in {AAPL, DHI, PHM, KBH, TOL}, so the earlier upstream-input overlap observation
  never established a lawful real B1-to-Earnings D5 vertical.
falsifier: >
  From the macro repository root run `python3 -c 'import json,pathlib,sys;
  covered={"AAPL","DHI","PHM","KBH","TOL"}; root=pathlib.Path("data/us_prophet_rank/episodes/generations");
  hits={p.parent.name:sorted(covered & {str(r.get("ticker_at_observation") or "").upper()
  for r in json.loads(p.read_text())}) for p in root.glob("peg:*/all_candidates.json")};
  hits={k:v for k,v in hits.items() if v}; print(hits); sys.exit(1 if hits else 0)'`.
  Any non-empty result for a committed natural generation disproves the current
  absence claim and requires a fresh issuer-level identity and event-workspace census.
so_what: >
  Hold D5 implementation at NO_LAWFUL_REAL_VERTICAL. Reopen only after a current
  natural B1 generation contains at least one Earnings-covered security resolved
  through canonical economic identity and the Data OS owner exposes the required
  issuer-to-CIK bridge; neither gate alone authorizes adapter code.
kind: data
verified_at: 2026-08-30
verified_by: >
  Exact-ref GitHub reads at macro@418def12139f8a9d1ddc7a3abc82e57442095c96:
  data/us_prophet_rank/episodes/generations/peg:c025bb50c45f319f989a4848249b8a85b65354143e3262f2ad09d07841311b08/all_candidates.json,
  peg:9afeb4f89ecc434c119f563424990d7b10b58bc75a30a0f275c74cf73465cfcc/all_candidates.json,
  and peg:881d604cc56968cfe921188f59e992c1652329416fa2bb2b4e9059a46616acc2/all_candidates.json;
  exact searches for AAPL, DHI, PHM, KBH and TOL returned no row in each 467-episode
  generation. The corresponding latest_receipt.json files record natural publication
  at 2026-08-28T14:28:48Z, 2026-08-29T15:41:20Z and 2026-08-30T07:20:29Z.
scope:
  - macro
  - WS:PROPHET-US-V4-RECOVERY
  - data/us_prophet_rank/episodes/generations/
  - engine/company_intelligence/issuer_profiles.py
  - future prophet.intelligence_vector/v1
confidence: verified
---

## Boundary of the finding

This discovery proves absence from the **canonical accepted B1 episode plane**. It
does not yet prove whether the covered names disappeared because the 2026-08-26
TURN WATCH input omitted them, because Data OS identity resolution refused them, or
because another intake gate suppressed them. That upstream attribution remains
unverified and is not needed to decide the D5 entrance gate: no accepted episode
means there is no lawful real episode-to-Earnings join to ship.

The historical 2026-08-25 TURN WATCH observation remains useful archaeology. It is
not current product evidence because all three natural B1 generations were built
from the later 2026-08-26 source and the owner-issued episode generation is the D5
join boundary.
