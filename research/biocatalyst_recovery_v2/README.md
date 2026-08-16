# BioCatalyst Recovery + Alpha Engine Masterplan V2

This directory is the canonical repository form of the V2 recovery masterplan assembled on 2026-08-16.

The document is split into eight ordered Markdown parts to keep repository writes reviewable and resilient. Read them strictly in numeric order:

1. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_01.md`
2. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_02.md`
3. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_03.md`
4. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_04.md`
5. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_05.md`
6. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_06.md`
7. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_07.md`
8. `BIOCATALYST_RECOVERY_AND_ALPHA_ENGINE_MASTERPLAN_V2_PART_08.md`

The split files preserve the masterplan's reading order and execution intent. Treat this directory, rather than any stale local copy or historical SHA mentioned inside the document, as the repository source of truth for the recovery program.

## Execution rule

Do **not** treat this masterplan as permission to execute all waves at once.

The program now advances PR-by-PR. The immediate task is P0 production hydration diagnosis/recovery only. After each BioCatalyst PR, stop and have the PR reviewed before issuing the next implementation instruction.

The P0 execution packet and stop conditions are front-loaded in Parts 01–04. Later parts describe the post-recovery parity, temporal graph, asymmetry engine, options integration, validation program, and bounded Prophet integration.

Repository SHAs mentioned in the document are evidence snapshots, not checkout instructions. Always fetch current `origin/main` before starting a new worktree or branch.
