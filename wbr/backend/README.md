# WBR backend deployment bridge

This is a minimal, read-only HTTP bridge for Render. It intentionally returns empty arrays when no imported data files exist. It does not fabricate fixtures, scores, odds, forecasts, or provider status.

## Routes
- GET /health
- GET /api/v1/health
- GET /api/v1/sources
- GET /api/v1/matches
- GET /api/v1/odds
- GET /api/v1/forecasts
- GET /api/v1/providers
- GET /api/v1/matches/canonical
- GET /api/v1/odds/matched

Place validated JSON snapshots in the data/ directory. Provider credentials must be configured as server-side environment variables only. This bridge does not yet call external providers; connect and test the provider adapters before calling it a live-data service.
