# Inner Insights Content Factory

Automated content pipeline for Claudia Infinity / Inner Insights (@claudiainfinityai, "The Collective" Love Transmissions).

Flow: Transmissions .docx (Drive) → `01-scripts/parse_transmissions.py` → Runway avatar API (her 3 avatars + Luna, Maya voice)
→ `03-media/make_reel.py` (9:16 reel, blurred backdrop, burned-in captions + title) + `02-content/render_post.py` (1080x1350 post)
→ Vercel Blob → Metricool CSV import. Quora handled separately (no API): assisted Playwright poster.

## Layout
- `01-scripts/` — parser + parsed sets (`setN.json`, gitignored until repo is private). Source of truth = Drive folder "Transmissions".
- `02-content/` — post renderer, generated post metadata, Metricool CSV exports
- `03-media/` — reel pipeline + rendered videos/images (media gitignored, lives in Vercel Blob)
- `config/` — `avatars.json` (Runway avatar ids, voice, output geometry, sources), `backgrounds/`

## Runway facts (verified Aug 20 2026)
- Developer API org is separate from the web app; avatars must be created via `POST /v1/avatars` from a reference image.
- `avatar_videos` (gwm1_avatars) outputs 1088x704 landscape, 24fps. ~2 credits per 40s clip. No ratio/duration params.
- Output URLs expire in 24-48h: always download immediately.

## Setup
Copy `.env.example` to `.env` and fill in `RUNWAY_API_KEY`. Never commit `.env`. Needs ffmpeg + Python 3 with Pillow.
