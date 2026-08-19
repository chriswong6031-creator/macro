# GD-1 repair analysis

Terminal for this wave: **REPAIR_UNRESOLVED_AT_CUTOFF** (2026-08-19).

## Impulse

SK Hynix board on **2026-08-19** resolved acquire-and-cancel of about 40 trillion won of treasury shares (~24.07 million shares, ~3.3% of issued), execution about three months starting **2026-08-20**, then full cancel.

- **Primary clock:** not in this checkout (no DART/KIND artifact).
- **Secondary clock:** BusinessKorea updated 2026-08-19 16:59 KST, https://www.businesskorea.co.kr/news/articleView.html?idxno=275082
- **quality_state:** CLOCK_PARTIAL
- **Earlier related clocks (not this impulse):** Reuters 2026-08-07 "actively reviewing" additional returns in Q3; April 2026 pledge. Those are review/pledge, not the 40tn resolution.

## Packet §17 sequence (must stay separate)

| Step | Status on 2026-08-19 |
|---|---|
| 1. issuer-only | **BLOCKED on prices** — `000660.KS` not in store. Impulse exists as a disclosure, not as a priced issuer bounce. |
| 2. memory / semiconductor cohort | US 08-19 bar absent. US 08-18 was the **damage** session (SMH −4.09%, SOXX −4.96%), before the BOD. |
| 3. regional index | KOSPI 08-19 −4.75% (volume light, possibly incomplete) — this is the breakdown session, not repair. |
| 4. US futures / next US cash | 08-19 US cash **absent** from this checkout. |
| 5. rates / volatility | DGS30 last print 5.31 on 08-17; VIX 15.19. No 08-19 rates row used. |
| 6. breadth / correlation | LC 08-18 still BROKEN, carnage EMA 57%. No 08-19 LC row. |
| 7. persist 1s / 2s | **Cannot start.** Impulse day = regional down day. |

A broad index bounce carried by one supported mega-cap is **not** confirmed repair. We do not even have that bounce in-repo.

## Failed-repair vs durable-repair

GD-H7 cannot be scored on this incident yet. The impulse is same-day as the regional breakdown. Two settled sessions have not elapsed.

Prior July 2026 SK Hynix / KOSPI episode remains a **separate** case (named in `research/SECOND_ACT_NOTE.md`). Do not merge it into this repair path.

## What would confirm / fail from here

- **REPAIR_CONFIRMED:** issuer + cohort + KR + next US session + LC/breadth not re-breaking, persisting two settled sessions.
- **REPAIR_FAILED:** new low in the exposed cohort after 2026-08-20 buyback start, before those confirmations.
