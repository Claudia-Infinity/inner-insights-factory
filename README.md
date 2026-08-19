# Inner Insights Content Factory

Automated content pipeline for Inner Insights (@claudiainfinityai).

Flow: scripts (Google Doc) → avatar videos (Runway API) + statics → captions burned in → Vercel Blob → Metricool CSV import.

## Layout
- `01-scripts/` — parsed scripts (source of truth is the shared Google Doc)
- `02-content/` — generated post metadata, Metricool CSV exports
- `03-media/` — rendered videos/images (gitignored, lives in Vercel Blob)
- `config/` — avatar personas, template specs, pipeline config

## Setup
Copy `.env.example` to `.env` and fill in keys. Never commit `.env`.
