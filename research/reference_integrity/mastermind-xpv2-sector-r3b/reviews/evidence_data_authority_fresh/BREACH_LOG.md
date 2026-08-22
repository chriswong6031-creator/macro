# Quarantine breach log (first pass)

## B-1 — 2026-08-22, one row of QA_ATTACK_REPORT.md
Cause: `grep -rn 'factor_z' mockups/.../build/` matched `build/QA_ATTACK_REPORT.md:583`
(row QA3-03) because the report lives INSIDE the build dir I was searching for code.
Exposure: exactly one table row, concerning the `action_board.json` bare-NaN tokens.
Materiality: NIL for independence — I had already (a) found the two bare NaN tokens by
byte scan, (b) traced them to `factor_z`, and (c) identified the
production-unreachable-render consequence, BEFORE the grep ran. The leaked row
confirms my own finding; it did not seed it.
Remedy: all subsequent searches exclude the quarantine list via `safegrep`.
