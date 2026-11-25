# WBR backend deployment bridge

Minimal read-only HTTP bridge for Render. It returns empty arrays when no imported data files exist. It does not fabricate fixtures, scores, odds, forecasts, or provider status.

Routes: /health, /api/v1/health, /api/v1/sources, /api/v1/matches, /api/v1/odds, /api/v1/forecasts, /api/v1/providers, /api/v1/matches/canonical, /api/v1/odds/matched.

Place validated JSON snapshots in data/. Provider credentials must remain server-side. This bridge does not yet call external providers; it is not a live-data feed.
