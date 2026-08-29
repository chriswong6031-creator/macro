# W4.2 / LER-C1 — Private evidence spool: operator provisioning runbook

**Operation:** `ler-c1-private-spool-20260828-sol-001` · **Workstream:** `WS:LIVE-ENTRY-RADAR`
**Security basis:** `DSC:RADAR-SPOOL-PUBLIC-R2` (anonymous HTTP 200 on the Day-4 envelope
re-verified at LER-C1 pickup) · masterplan §3.4 · delivery-plane family
`entry_radar_evidence_spool` (`config/r2_delivery_plane_classification.v1.json`).

## What the merged code does (no provisioning required)

- `engine/entry_radar/spool.py` routes every raw-evidence key
  (`live_flow/entry_radar_events/**`, `live_flow/entry_radar_nominations/**`)
  through a **dedicated private store** bound by the four env names
  `ENTRY_RADAR_R2_ENDPOINT` / `ENTRY_RADAR_R2_ACCESS_KEY_ID` /
  `ENTRY_RADAR_R2_SECRET_ACCESS_KEY` / `ENTRY_RADAR_R2_BUCKET`
  (all four required together — partial config counts as absent).
- With the dedicated store **unconfigured**, an evidence WRITE **refuses the
  shared public-classified bucket** (typed `::warning` at line start) and falls
  back to `$ENTRY_RADAR_SPOOL_DIR` (private on-host disk) when set; with
  neither, the envelope is withheld fail-closed and `spool_then_commit`
  withholds the transitions — **the lane never publishes evidence anonymously
  again, at the cost of being dark until provisioning**.
- READS (Prophet Lab `resolve_radar_spool`, and W5's seam) resolve the
  dedicated store when configured, else the **shared authenticated client**
  as the explicit legacy path — historical envelopes stay readable with
  credentials; never an anonymous fallback.

## Operator acts (in order)

1. **Create the private bucket** in the Cloudflare R2 account (suggested name
   `entry-radar-evidence`). Do **NOT** enable a public development URL or any
   custom-domain public binding on it.
2. **Mint a scoped API token** for that bucket only (Object Read & Write). The
   existing shared token stays untouched; this mirrors the accepted
   BioCatalyst/13F dedicated-store shape.
3. **Bind the env on the VPS** (values never through Git/Slack/logs):
   - writer: the evaluator unit's environment
     (`macro-live-entry-radar.service` drop-in / `/etc/macro-live.env`);
   - Lab API: `/etc/macro-api.env` (the `macro-api` service reads the spool
     through `engine/prophet_lab/sources.py`).
   Add the four `ENTRY_RADAR_R2_*` names, then restart both units.
   Interim alternative (Stage A): set only `ENTRY_RADAR_SPOOL_DIR` +
   `PROPHET_LAB_RADAR_SPOOL_DIR` to one private on-host directory — evidence
   keeps flowing privately on disk while the bucket/token are provisioned.
4. **Verify** (receipts for the C1 acceptance packet):
   - writer: next in-window pass with a delta logs `published live_flow/entry_radar_events/...`
     with no `::warning` refusal;
   - Lab: `/api/prophet/lab/v1` health names `backend=r2` with the dedicated
     bucket (or `backend=local` in Stage A);
   - anonymous: `curl -s -o /dev/null -w '%{http_code}' https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/live_flow/entry_radar_events/<new-session-key>` → non-200
     (the new object is not on the public bucket at all).
5. **Historical exposure cleanup (separate operator act, B1-tombstone
   precedent):** delete the pre-cutover `live_flow/entry_radar_events/**` and
   `live_flow/entry_radar_nominations/**` objects from the shared bucket once
   W5/Lab no longer need the legacy reads (after LER-C3 reconnects to the
   private store). Until deletion, the historical Day-4 envelope remains
   anonymously readable and `DSC:RADAR-SPOOL-PUBLIC-R2` remains unretired.

## What this wave does NOT do

No detector/hash change; no Prophet paths; no W5 nightly rebind (LER-C3); no
cold-gap/cadence work (LER-C2); no new client implementation (one
`_build_client` serves both stores); no second W5 reader/store.
