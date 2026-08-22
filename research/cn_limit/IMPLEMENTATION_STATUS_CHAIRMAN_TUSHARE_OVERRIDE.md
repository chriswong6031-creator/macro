# Chairman TuShare override — implementation status

Authority freeze is present on this branch. **Do not merge this branch as completion yet.**

Remaining required implementation before merge:

1. Remove the license-document authorization subsystem from `collectors/china_tushare_spine.py`.
2. Replace its license-gate tests with anti-resurrection tests while retaining technical gates.
3. Remove any workflow arguments/secrets used only for authorization receipt/trust allowlist.
4. Amend the full-A spine contract and CN-Limit R6 active architecture/registry/command packet.
5. Reconcile `WS-CN-LIMIT-ALPHA` so DEP-EXACT is technical-readiness-only, not waiting on a vendor letter.
6. Refresh generated governance docs and run the repo-wide stale-reference census.
7. Run targeted tests, AgentOS validation, contract/fence checks and CI.

Implementation commission:
`agentos/handoffs/CN-LIMIT-ALPHA-2026-08-21-CHAIRMAN-TUSHARE-OVERRIDE.md`.
