---
key: W2C-M0D0-SPY-REST-FORMING-BAR-SEAL-STABLE
claim: >
  On XNYS session 2026-08-20, GET /v2/aggs/ticker/SPY/range/1/day/2026-08-20/2026-08-20?adjusted=false
  was a live forming daily aggregate (first non-empty bar 13:30:41Z, 546 unique
  canonical results[] digests, last price revision 20:10:56Z, last activity
  revision 03:01:52Z D+1) that then held a single digest through the 04:00–04:05Z
  D+1 source seal (19/19) and through 04:44:49Z (155/155).
falsifier: >
  shasum -a 256 research/market_memory/W2C_M0D0_SPY_REST_REVISION_TRAJECTORY_2026-08-20.tsv
  differs from 69402b2e9d519b48181d9bf64b1608514c2bd6c495c4faab50e17bf4b8ec5755,
  or that TSV's first non-empty row is not 13:30:41Z digest
  499b14721c22b54c35672a546c31786eab72198575fec9d0f2c2e3dcaa36590d, or any
  04:00:00Z–04:04:58Z row carries a digest other than
  56152e7292db903dee1fee2af4ae6e4319c55bceb140ea911f4acae48b9184d0.
so_what: >
  Do not treat first REST availability as W2C readiness. Do not persist the
  546 forming-bar revisions as production source generations. Seal once under
  [04:00:00Z, 04:05:00Z) D+1. Grouped daily is a non-authoritative cross-check.
kind: data
verified_at: 2026-08-21
verified_by: >
  python3 reconstruction of /tmp/m0d0_spy_rest_2026-08-20.jsonl (841 polls,
  last write 2026-08-21T04:44:50Z) into
  research/market_memory/W2C_M0D0_SPY_REST_REVISION_TRAJECTORY_2026-08-20.tsv;
  sha256 69402b2e9d519b48181d9bf64b1608514c2bd6c495c4faab50e17bf4b8ec5755;
  547 lines = header + 546 distinct digests; 0 reappearances.
scope:
  - macro
  - "WS:MARKET-MEMORY-W2C"
  - research/market_memory/W2C_M0D0_SPY_REST_REVISION_TRAJECTORY_2026-08-20.tsv
confidence: verified
---

# 2026-08-20 REST daily bar formed live, then sealed at 04:00Z

This is the measured M0D-0 trajectory. Durable bytes:

`research/market_memory/W2C_M0D0_SPY_REST_REVISION_TRAJECTORY_2026-08-20.tsv`

sha256 `69402b2e9d519b48181d9bf64b1608514c2bd6c495c4faab50e17bf4b8ec5755`

## Timing

| Event | UTC | Digest / values |
|---|---|---|
| Probe start (empty) | 2026-08-20T13:09:02Z | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` resultsCount=0 |
| First non-empty | 2026-08-20T13:30:41Z | `499b14721c22b54c35672a546c31786eab72198575fec9d0f2c2e3dcaa36590d` HTTP 200 / 1; O/H/L/C 765.96/766.14/765.94/766.12; V/n 1104104.391941/17761 |
| Last H change | 2026-08-20T15:04:12Z | H finished 768.15 |
| Last L change | 2026-08-20T20:00:50Z | L 762.04 at regular close |
| Last price (C) revision | 2026-08-20T20:10:56Z | C 762.78 → 762.60 |
| Last vw change | 2026-08-21T00:01:17Z | 764.9393 |
| Last activity (V/n) revision | 2026-08-21T03:01:52Z | V 45520302.607881; n 600817; digest `56152e7292db903dee1fee2af4ae6e4319c55bceb140ea911f4acae48b9184d0` |
| Source seal | 2026-08-21T04:00:00Z–04:04:58Z | 19/19 that same digest |
| Post-seal through stop | 2026-08-21T04:05:14Z–04:44:49Z | 155/155 that same digest |

O was 765.96 from first print through stop. `bar.t` was always
`1787198400000` (2026-08-20T04:00:00Z, midnight ET). Session identity is
request date D, not `bar.t`.

One RTH transport timeout at 16:50:58Z (152s gap) sat inside the forming
bar and did not enter the seal.

## Grouped cross-check (non-authoritative)

First grouped SPY at the same 13:30:41Z instant. Final O/H/L/C/V/n/vw
agreed with the sealed single-ticker bar. Grouped `t` was always
`1787256000000` (16:00 ET). One RTH lag at 14:40:00Z. Do not seal from
grouped.

## Architecture consequence

First availability at the opening bell explains the 546 unique digests. It
does not make the bar W2C-ready. The 04:00–04:05Z D+1 source seal is the
readiness boundary. Production persists one sealed capture per session, not
one capture per poll.
