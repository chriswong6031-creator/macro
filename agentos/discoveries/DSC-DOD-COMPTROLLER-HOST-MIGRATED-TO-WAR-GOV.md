---
key: DOD-COMPTROLLER-HOST-MIGRATED-TO-WAR-GOV
claim: >
  The DoD Comptroller's official budget surface migrated hosts under the
  Department of War rebrand: comptroller.defense.gov now answers HTTP 403
  (AkamaiGHost) with NO redirect on every probed path (root and
  /Budget-Materials/), while comptroller.war.gov serves the identical DNN CMS
  tree (/Portals/45/Documents/defbudget/…, full FY1998–FY2027 archive) with
  clean 200s that are CLI-fetchable from the Mac Studio (no TLS-fingerprint
  block observed on this host, unlike www.defense.gov / www.war.gov front
  pages). The current cycle is the FY2027 President's Budget (posted April
  2026); the documents self-identify the publisher as "Office of the Under
  Secretary of War (Comptroller)", not the Defense-era name.
falsifier: >
  A fresh curl -sI https://comptroller.defense.gov/Budget-Materials/ returning
  200 or a Location redirect to war.gov, or comptroller.war.gov beginning to
  403 CLI fetches of /Portals/45/Documents/defbudget/ paths.
so_what: >
  Every current or future DoD-source rail (D6 budget, and later D6-B+ rails
  such as contract announcements or DOT&E) must target the war.gov host
  family; anything hardcoded to comptroller.defense.gov hard-fails with 403
  regardless of fiscal year, and there is no server-side redirect to save it.
  collectors/dod_budget.py ALLOWED_SOURCE_HOSTS already contains both hosts,
  so receipts stay valid, but acquisition must use comptroller.war.gov.
  Receipt publisher strings must follow the source-native War-era
  self-identification for FY2027+ documents. The D0R registry row's
  "official page" URL (comptroller.defense.gov) is stale as an acquisition
  target.
kind: constraint
confidence: verified
verified_at: 2026-08-24
verified_by: >
  curl -sI probes 2026-08-24T14:41Z: comptroller.defense.gov root and
  Budget-Materials 403 AkamaiGHost, no Location; comptroller.war.gov
  /Portals/45/Documents/defbudget/FY2027/FY2027_p1.pdf HTTP/2 200
  content-length 2796050 (sha256 b8d5248257590856ee33ddb1b401ec2efcdfea219c05b5bc8ea1068d9000d0a6
  on full download) and FY2027_r1.pdf 200 content-length 3127023 (sha256
  1aa8846edb69d4c3a54e03b383b0cabb77f93433162b8139ab8cbb55bcc7882a); page-1
  text of both PDFs prints "Office of the Under Secretary of War
  (Comptroller)" (PyMuPDF text-layer read, local reference copies).
scope:
  - macro
---
