# Pinned Prophet Board reference — W8 session start

**Pinned at session start, after `git fetch origin main`.**
Do not substitute a remembered screenshot or an older RIG cycle SHA.

| What | Value |
|---|---|
| `origin/main` at pin | `cc6f53f619f439683a4da7aa366843aef6079768` |
| R4 closure PR | [#5560](https://github.com/mastermindx-market-intelligence/macro/pull/5560) **MERGED** 2026-08-14T05:45:30Z |
| R4 squash-merge commit on `origin/main` | **`168a9be006914441051cff393927ce465e39138e`** |
| Tree SHA of `mockups/refs/institutionalize/us_stocks` on that commit (and still on `origin/main`) | **`d540f493a097cb37f3f91e4c7bc81a39b876d069`** |
| Later commits touching the Prophet Board reference files | **none** (`git log 168a9be..origin/main -- mockups/refs/institutionalize/us_stocks` empty) |

## File blob SHAs at the pin (origin/main)

| File | blob SHA |
|---|---|
| `mockups/refs/institutionalize/us_stocks/index.html` | `6232d899b6cd674c422ed4de7b99602a2bd1085e` |
| `mockups/refs/institutionalize/us_stocks/board.css` | `e68d52ca01edeb08520ef93436c257b2eebca589` |
| `mockups/refs/institutionalize/us_stocks/board.js` | `e6213eced711c60334886666e01db3f73c77af0e` |
| `mockups/refs/institutionalize/us_stocks/board-data.js` | `32914fcba27ee0845b6eb5568620878762be60b7` |
| `mockups/refs/institutionalize/us_stocks/DESIGN_NOTES.md` | `f8f32c877c4e90b6ec2dbfe724b25229aee409ac` |
| `templates/_prophet_card.html.j2` | `ecefe69b0729da0070ebecfd97069fba8bc355cb` |
| `templates/_prophet_receipts.html.j2` | `ebca28d271969a41a419c666d158ef660a07b24e` |

## Note on the PR-body SHA `9995603e`

PR #5560's body names frozen SHA `9995603e1bf64fc4b718785a0534d38ae3e3006a`. That is the **pre-squash branch head**. It is **not** on this clone and is **not** an ancestor of `origin/main`. The current-on-main pin is the squash merge `168a9be00691` / tree `d540f493a097`.

## How this session used the pin

Radar's card/layout language was read from those blobs at session start — not from memory, not from the R3 evidence tree `6ad6b51b`, not from `mockups/refs/prophet_board_priority/` production shots.

Verified:

```bash
git fetch origin main
git rev-parse origin/main
git rev-parse origin/main:mockups/refs/institutionalize/us_stocks
git log -1 --format='%H %s' origin/main -- mockups/refs/institutionalize/us_stocks
```
