---
key: TERMINAL-INGEST-EMITTERS-RUN-AS-SCRIPTS
claim: >
  mastermind-terminal's fundamentals emitters are invoked BY PATH, not as modules -
  `ingest/refresh_fund.sh` and `ops/nightly_fund.sh` both run `"$PY" "$INGEST/gen_fund_us.py"` -
  so at runtime `sys.path[0]` is `ingest/`, NOT the repo root. A shared helper imported as
  `from ingest.earnings_calendar import ...` therefore resolves fine under pytest, which puts
  the repo root on `sys.path` (CI even documents this: `python -m pytest tests/ -q` "from the
  repo root: that is what puts the root on sys.path"), and raises `ModuleNotFoundError:
  No module named 'ingest'` in the nightly - aborting the whole US fundamentals lane before
  its rsync, with green CI. The house remedy already exists in the same directory
  (`gen_slices_all.py`, `regen_flagship_slices.py`, `build_polygon_universe.py`):
  `CA_ROOT = Path(__file__).resolve().parents[1]`, `sys.path.insert(0, str(CA_ROOT))`, then the
  import with `# noqa: E402`. Related: `gen_fund_*.py` resolve their output as
  `CA_ROOT / "terminal" / "public" / "data"`, so an emitter run from a worktree writes into
  that worktree and cannot touch production - which makes a full dry run against the real
  yfinance cache free of risk.
falsifier: >
  `cd ingest && python3 -c "import gen_fund_us"` succeeding while `gen_fund_us.py` carries a
  bare `from ingest.<mod> import ...` with no `sys.path` bootstrap; or `grep -n 'gen_fund_us'
  ops/nightly_fund.sh ingest/refresh_fund.sh` showing `python -m ingest.gen_fund_us` rather
  than a path invocation.
so_what: >
  Any refactor that factors shared code out of an `ingest/` emitter MUST add the house
  bootstrap and MUST be verified with `cd ingest && python3 -c "import <emitter>"`. A green
  pytest run is NOT evidence here - it is precisely the signal that hides this defect, and the
  failure mode is a silent whole-lane production outage rather than a test failure. Recorded
  in the Terminal repo's own AGENTS.md as of PR #477.
kind: landmine
verified_at: 2026-08-26
verified_by: "reproduced as ModuleNotFoundError via `cd ingest && python3 -c 'import gen_fund_us'`; fixed and re-verified in mastermind-terminal PR #477"
scope:
  - mastermind-terminal
  - mastermind-terminal:ingest/**
  - mastermind-terminal:ops/nightly_fund.sh
confidence: verified
---

The shape of the trap is that the safe-looking verification is the one that lies. `pytest` is
run from the repo root by contract, so it puts the root on `sys.path` and the package import
resolves; the nightly invokes the same file by path and it does not. Green CI is therefore
positive evidence for the wrong environment. Verify the environment that actually runs the code:

```
cd ingest && python3 -c "import gen_fund_us"
```
