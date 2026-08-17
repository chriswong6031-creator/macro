# W8 finding dispositions

Author-session first pass. See `CRITIQUE.md`. Commissioning critics may add IDs;
do not reuse these numbers for a different finding.

| ID | Sev | Disposition | Evidence |
|---|---|---|---|
| PRC-W8-001 | major | ACCEPT_FOR_W8 | Glance why-lines for C1/C2/board extras rewritten to plain word; remaining mechanical lines are lawful §14 copy. W9 glance pass. |
| PRC-W8-002 | major | SUPERSEDED | Originally `--pv-buy`; author then bound `--ok`. Independent VTC-004 moved candidate/featured to `--er-life`. Do not re-bind `--ok`. |
| PRC-W8-003 | minor | RETAIN | Contract §14 lane name “Deep Washout”; card freshness says “confirmed 4H”. |
| PRC-W8-004 | minor | RETAIN | C4 chip is visible, `aria-disabled`, `data-role=stratification_only`. |
| PRC-W8-005 | minor | SUPERSEDED | Quiet no longer forces Probe Set to 0 (independent PRC-001). Fixture 42 remains page-level metadata until W4. |
| PRC-W8-006 | minor | RETAIN | Drawer clocks are ISO by design. |
| VTC-W8-001 | major | RETAIN | 232px Prophet card min; wrap is the sister pattern; 390 is 1-col. |
| VTC-W8-002 | minor | RETAIN | Featured = Best-lane live candidate only. |
| VTC-W8-003 | minor | RETAIN | Light mobile ZH is verification. |
| VTC-W8-004 | minor | RETAIN | Disabled C4 must remain visible. |

Independent critic must-fix nits (PR #5737 commissioning pass) — applied on this revision:

| ID | Sev | Disposition | Evidence |
|---|---|---|---|
| PRC-001 | major | FIXED | Quiet no longer forces Probe Set to 0. Empty well and headline agree. `verify.py` R16. Mutation M14. |
| PRC-002 | major | FIXED | `rows.sort` by lifecycle (live first) then expert. `verify.py` R17. Mutation M15. |
| PRC-003 / VTC-009 | major | FIXED | Best lane is `Best · unranked` with a dashed count. `verify.py` R18. Mutation M16. |
| PRC-004 / VTC-003 | major | FIXED | Featured aura = `inLane(best)`. Same set as Best. `verify.py` R19. Mutation M17. |
| PRC-006 | major | FIXED | Stale fixture has a spark; stale-null copy is “Path is stale”. `verify.py` R20. Mutation M18. |
| PRC-010 | major | FIXED | Dead `#ticker` link removed. DESIGN_NOTES §5 honest: PRC-301 is not closed. `verify.py` R21. Mutation M19. |
| PRC-007 / PRC-008 | major | FIXED | W9 CAN COPY no longer lists the reduced card as §14 complete. Missing slots are BLOCKED_DATA / ACCRUING. `verify.py` R22. Mutation M20. |
| VTC-002 | major | FIXED | One board-level Priority ACCRUING line; card slot is an em-dash. `verify.py` R23. Mutation M21. |
| VTC-004 | major | FIXED | Candidate / featured / C3 use `--er-life`, not `--ok` or `--pv-buy`. `verify.py` R12f/R24. Mutation M13. |
| VTC-005 / VTC-006 | major | FIXED | `overflow-x: hidden` removed. C2 variant left the overlay. Footer wraps. Overlay wrap restored to sister (`flex-wrap: wrap`). `verify.py` R25. Mutations M12, M24, M25. |

Continuation critic C (artifact `5ef3626`, REVISE) — bounded repairs on this PR, not a second architecture:

| ID | Sev | Disposition | Evidence |
|---|---|---|---|
| VTC-C-001 | blocker | FIXED | Overlay restored to sister wrap (`calc(100% - 122px)`). Expert-chip-on-lifecycle collision is gone. Quote-on-lifecycle is RGXB-001, not this row. |
| VTC-C-002 | blocker | FIXED | `title=` removed. Priority uses `data-tip-en/zh` + sister lens popover + `tabindex="0"`. Expert slug is not a tooltip. `verify.py` R26 / P12. Mutation M26. |
| VTC-C-003 | major | NOT_ACCEPTED_AS_BLOCKER | Featured = Best was the commissioned PRC-004 / VTC-003 fix. Best count stays dashed (unranked) until W6. Do not reverse. |
| VTC-C-006 | major | FIXED | ≤720px keeps `.bh-purpose`; `.er-sister` may hide. Playwright P8b. |
| RGX-001 / BLK-001 | blocker | SUPERSEDED | `min-width: auto` stopped expert-on-lifecycle clip and created quote-on-lifecycle overflow. See RGXB-001. |
| RGX-002 / MAJ-001 | major | FIXED | Spark null branches: stale / unavailable / raw / degraded / terminal. “No path yet” only for a true missing spark. P13. Mutation M27. |
| RGX-003 | major | FIXED | Provisional Candidate chip is dashed; confirmed is filled. `[data-bar]` CSS. P14. Mutation M28. |

Continuation critics of freeze `9c8990d` (product A BLOCK, visual B BLOCK) — bounded repairs on this PR:

| ID | Sev | Disposition | Evidence |
|---|---|---|---|
| RGXB-001 / VTC-C-001 | blocker | FIXED | Overlay LIFECYCLE axis hidden (duplicate of body `.pv-life`). Pre-candidate chip (~110px) fits the `calc(100% - 122px)` rail. P11 vs `.pv-ovr .pv-quote` + `ovl.scrollWidth`, at 1024/1280/1440. Mutation M29. |
| RGXB-002 | blocker | FIXED | P11 previously compared `.er-lifechip` vs `.er-xchip` in the same rail (structurally 0). Now compares left rail vs quote and rail overflow. R29 pins that predicate in source. |
| RGXB-003 | major | FIXED | `tests/test_entry_radar_w8_rig.py` serves the ref tree and runs `verify.py --url` when Playwright is installed; otherwise the live battery is an explicit skip, not a silent pass. Static R29 still runs in CI. |
| RGXB-004 | nit | FIXED | DESIGN_NOTES §2: UNAVAILABLE is the freshness footer, not the lifecycle chip word. |
| VTC-D-002 | major | FIXED | DESIGN_NOTES §5 no longer claims VTC-304 is fully inherited. Pre-candidate `--pv-wait` vs stale `--warn` is disclosed. |

Visual re-attest of freeze `a8c763dc` (`opus-designer-w8-reattest-5737-B`): **PASS_WITH_CONDITIONS**. Prior BLOCK lifted. Four minor W9-facing conditions (VTC-B-401..404) recorded in `reviews/visual_taste.yml` and `W9_IMPLEMENTATION_HANDOFF.md`. No freeze re-cut.

Do not self-approve. Do not start W9. Product re-attest of `a8c763dc` is still required before `verdict.yml`.


