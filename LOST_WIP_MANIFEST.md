# Lost uncommitted WIP — 2026-06-28 worktree cleanup error

During worktree cleanup, a preservation script's `git add` silently aborted (it
listed `brain/portfolio/research` pathspecs that don't exist in older worktrees,
which makes `git add` stage nothing), but the script still ran `git worktree
remove --force`, deleting the uncommitted working-tree edits before they were
committed. `git fsck` found 0 dangling blobs (never staged → not in git's object
store) and VS Code Local History had no entries (edited by agents, not the editor).

**NOT affected:** all 8 recovered features merged to main (#596,#598,#600,#605-#609),
all committed branch content (already in main — these were dead/already-live branches),
the committed branch tips (recoverable via git).

**Lost (uncommitted source edits only), by worktree:**

SUBSTANTIAL (unique, not in main):
- claude/quizzical-swirles-7c7dfa : NEW engine/sector_rotation.py + edits to engine/setups.py,
  scripts/build_site.py, scripts/build_stock_library.py, templates/dashboard.html.j2 (~160 lines)
- feat/conviction-v2 : collectors/edgar_eps.py (+137), NEW collectors/test_edgar_eps.py,
  NEW scripts/risk_penalty_phase0.py, NEW scripts/washout_reclaim_phase0.py
- claude/infallible-panini-cd05c8 : templates/ipo.html.j2 redesign (+204/-62)
- claude/festive-turing-247f38 : masterminds engine + templates overhaul (~392 lines across
  engine/{china_masterminds,masterminds}.py, scripts/build_*masterminds.py, templates/*masterminds*)

MINOR (small tweaks / superseded):
- claude/agitated-wu-1ad407 : ipo/report_base/_vector_polish templates + theme.css (~63 lines)
- claude/heuristic-poitras-6fe551 : playbook.py/build_site/dashboard/sector (new file was already in main)
- business-cycle-model : engine/business_cycle.py (+23)
- claude/bold-meitner-78c1b2 : engine/narrative_rotation.py (+14)
- claude/busy-perlman-e033c6 : dashboard/stock templates (+8)
- claude/bold-kare-d8e7ec : dashboard.html.j2 (+2)
- feat/market-drivers : factors.html.j2 (+1)

**Recovery option:** if you have a Time Machine / external backup from before
2026-06-28, the deleted worktree directories under
`.claude/worktrees/<name>/` and `~/Documents/Cluade/macro-conviction-wt/`
would contain these edits.
