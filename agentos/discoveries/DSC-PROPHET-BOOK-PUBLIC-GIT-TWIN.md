---
key: PROPHET-BOOK-PUBLIC-GIT-TWIN
claim: >
  The canonical macro repository (mastermindx-market-intelligence/macro) is
  PUBLIC ("private": false, "visibility": "public" via authenticated API,
  2026-08-21). raw.githubusercontent.com therefore serves the ENTIRE committed
  site/ tree anonymously: site/prophet/index.json answered HTTP 200 with
  2,242,608 bytes — byte-identical in size to the same night's R2 object —
  and site/premiumdata/us_stocks.json answered HTTP 200 with 1,065,497 bytes.
  The pre-rename owner URLs (chriswong6031-creator/macro) 301-redirect to the
  canonical repo, which is why Mastermind's anonymous vendor sync
  (data_layer/macro_refresh.py: git clone --depth 1 --filter=blob:none
  --sparse https://github.com/chriswong6031-creator/macro.git, 3-hourly cron,
  no credentials) still works. Closing the public R2 object (B1) therefore
  does NOT close anonymous access to the plan book or to the premium payloads:
  the git raw plane is a byte-identical twin. The estate already NAMES this
  plane: config/r2_delivery_plane_classification.v1.json family
  prophet_full_board_repository_static (MACRO_GIT_RAW:site/prophet/*,
  PREMIUM_PRODUCT) with migration_dependency "Stop future public
  tracking/fallbacks ... give Mastermind an authenticated private sync
  preserving vendored path/schema".
falsifier: >
  An anonymous GET of
  https://raw.githubusercontent.com/mastermindx-market-intelligence/macro/main/site/prophet/index.json
  returning 404/403 (repo private or path withdrawn) retires the exposure
  half. A recorded ruling that repo-public is deliberate and the premium
  boundary is defined as origin+R2 only would retire the policy half — but
  would need site/premiumdata's public-git availability squared with the
  regwall that 401s the same bytes on the origin.
so_what: >
  ESCALATED to Sol + Chairman as the decisive residual of B1: the §8b
  BOUNDARY PASS ("no unauthenticated path to withheld Prophet plan rows was
  constructible under production configuration") is NOT issuable while the
  git raw plane serves the same bytes, regardless of R2 closure. Repo
  visibility is a Chairman-level lever with enumerated blast radius — flip it
  unilaterally and at minimum: (1) the VPS production pull breaks (origin
  https://github.com/mastermindx-market-intelligence/macro.git with no
  embedded credential — the live site FREEZES), (2) Mastermind's 3-hourly
  anonymous vendor clone breaks (trading-input feed degrades fail-open and
  silently stale), (3) chriswong6031-creator.github.io/macro Pages dies (the
  Terminal's flow_idx last-resort fallback). The lawful path: Sol/Chairman
  rule on visibility; in the same wave give the VPS pull a credential (deploy
  key), give Mastermind the authenticated private sync the registry already
  prescribes, and re-point or retire the Pages fallback. No session may flip
  visibility as a side effect of B1.
kind: constraint
confidence: verified
verified_at: 2026-08-21
verified_by: "gh api repos/mastermindx-market-intelligence/macro --jq '{private,visibility}' → public; anonymous curl raw.githubusercontent.com/.../site/prophet/index.json → 200 2,242,608B and .../site/premiumdata/us_stocks.json → 200 1,065,497B; curl -I api.github.com/repos/chriswong6031-creator/macro → 301; Mastermind clone URL + 3h cron: data_layer/macro_refresh.py:262-264 + app/scheduler.py:1379; VPS remote: git -C /opt/macro remote get-url origin"
scope:
  - "macro"
  - "terminal"
  - "mastermind"
related:
  - "DSC:PROPHET-INDEX-PUBLIC-R2-TWIN"
  - "DEC:B1-PROPHET-PUBLIC-SPLIT"
  - "WS:PROPHET-US-V4-RECOVERY"
---

Found by the Day-5 B1 consumer census (Sol-ordered, census-before-deletion).
The R2 leak (DSC:PROPHET-INDEX-PUBLIC-R2-TWIN) is one of THREE anonymous
paths; this one is the widest (every committed site/ byte, premiumdata
included) and is load-bearing for a trading system's inputs. B1's R2-side
cutover proceeds as ruled; this record is the named reason the boundary
certification cannot yet convert to PASS.
