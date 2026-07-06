# Oracle brainstorm inbox

High-volume external-brainstorm pipeline. Drop each ChatGPT/Codex reply from
`python -m scripts.oracle_brainstorm_pack --explore [--focus K]` here as a
`.json` file (a JSON list of compound specs; several concatenated lists in one
file are fine). The `*.json` are gitignored — they are raw scratch input.

Then ingest (dedup vs live registry + within-batch, validate, flag scale &
2021+-coverage issues) and screen:

    python -m scripts.oracle_ingest_brainstorm --inbox research/oracle_inbox --out /tmp/oracle_ingest
    python -m scripts.oracle_screen --all-pending --compounds-dir /tmp/oracle_ingest/compounds \
        --data-dir <MAIN>/data --dry-run

Survivors that clear the promotion floor go through
`scripts/oracle_gauntlet_compound.py` (OOS + placebo). Reminder: any rule using
breadth_50 / cohesion / cohesion_chg / turnover_z / cohesion_rebuild is 2021+
only and cannot clear the era gate (see memory oracle-panel-column-coverage).
