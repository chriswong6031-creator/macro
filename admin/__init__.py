"""Local admin dashboard for the Macro Regime & Sector-Flow site.

A single-user, localhost-only web app (`python -m admin`) for the site owner to:
  • toggle feature flags in config.yml (AI brief, AI desk, notifications, data sources)
  • set the AI-brief regeneration interval (every 1..7 days)
  • watch GitHub Actions builds + trigger a rebuild/redeploy
  • see data-freshness / pipeline health, an AI-cost estimate, and a page inventory
  • read live Google Analytics 4 traffic (when a service account is configured)

The site itself stays a static, server-less GitHub Pages build — this admin app is a
LOCAL tool that edits the repo's config + drives the GitHub API. It is never deployed.
"""

__version__ = "1.0.0"
