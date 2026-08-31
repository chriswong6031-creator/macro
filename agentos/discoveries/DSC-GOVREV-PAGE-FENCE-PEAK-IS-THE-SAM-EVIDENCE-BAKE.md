---
key: GOVREV-PAGE-FENCE-PEAK-IS-THE-SAM-EVIDENCE-BAKE
claim: >
  site/government_revenue.html oscillates by ~38 KB between two bake regimes — the render
  lane leaves it near 277 KB while the `govrev: SAM opportunity evidence` live lane pushes it
  to 302,890 B against a 303,104 B fence — so the true headroom is 214 bytes at peak, not the
  ~25.9 KB a reading taken at HEAD reports.
falsifier: >
  Walk the artifact's own history and compare sizes by commit class:
  `git log --format=%H -60 -- site/government_revenue.html` then
  `git show <sha>:site/government_revenue.html | wc -c`. If `govrev: SAM opportunity evidence`
  commits do not sit ~25 KB above the neighbouring render-sync commits, or if no commit
  exceeds ~280 KB, the claim is refuted.
so_what: >
  Any change that adds bytes to the Government Revenue page must be sized against 302,890 B,
  never against the size at HEAD. A rail sized at a render-lane trough passes every local
  check and then blows RAW_HTML_BUDGET_BYTES on the next SAM evidence commit — an
  intermittent, lane-dependent failure whose green was produced by measuring at the wrong
  moment. Prefer a consumer that adds zero bytes to that page, and never respond by bumping
  the fence.
kind: constraint
verified_at: 2026-08-27
verified_by: >
  Sizes read from the git object store across the last 60 changes to the artifact:
  f5f11112da45 = 302,890 B (214 headroom) and 5d9628af92c2 = 302,713 B (391) on
  `govrev: SAM opportunity evidence`; 8229cce709af (HEAD) = 277,217 B (25,887) and
  3d972b6b2b87 = 277,040 B on `render-sync`; minimum observed 264,727 B; span 38,163 B.
  Fence pinned at scripts/build_government_revenue.py:118 and tests/test_fms_ui.py:39
  (RAW_HTML_BUDGET_BYTES = 303_104), enforced on html_path.stat().st_size at
  scripts/build_government_revenue.py:1123.
scope:
  - macro
  - government-revenue-foresight
  - site/government_revenue.html
  - scripts/build_government_revenue.py
confidence: verified
---

The fence is enforced by the builder on the file as written
(`scripts/build_government_revenue.py:1123`), so both bake regimes are measured against the
same 303,104-byte budget.

| commit | class | bytes | headroom |
|---|---|---|---|
| `f5f11112da45` | `govrev: SAM opportunity evidence` | **302,890** | **214** |
| `5d9628af92c2` | `govrev: SAM opportunity evidence` | 302,713 | 391 |
| `57ab8b9130b0` | D5 Virginia-class dossier | 299,855 | 3,249 |
| `8229cce709af` | `render-sync` (HEAD at census) | 277,217 | 25,887 |
| min of last 60 | — | 264,727 | 38,377 |

The live SAM-opportunity lane embeds evidence the render lane does not, which is why the same
page is 38 KB larger depending on which lane baked it last. The 302,713 figure carried in the
2026-08-27 Defense program-control dispatch is therefore accurate, not stale — a session that
measures at HEAD will wrongly conclude the dispatch is out of date and that ~25 KB of headroom
is available. It is not.

This is independent support for the standing instruction to shrink or split the Government
Revenue composition rather than raise the fence: the page is already within 214 bytes of its
budget at peak, and the peak is produced by a routine nightly lane, not by an unusual event.

Related: [[DSC-GOVREV-SBIR-RAIL-IS-A-SHIPPED-COLLECTOR-ONLY-WAVE]].
