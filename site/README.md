# JCVB Website

Public-facing static site for the John Carroll Boys Volleyball program:
**Home**, **Brand Guidelines**, **Newsletters**, and the **2026 Season Schedule**.

Built by a small Python static-site generator that renders pre-built HTML from
Jinja2 templates, Markdown newsletters, and TOML data. The output is fully
self-contained (self-hosted fonts + assets, no external/CDN calls).

## Build

```bash
uv sync                       # installs deps (jinja2, markdown, pillow, …)
uv run python -m jcvb.site_build
```

Output is written to `/build/` at the repo root (git-ignored). The site is served
under a **base path** (`base_path` in `site.toml`, currently `/jcvb` for
`sites.anvilor.com/jcvb`), so pages land in `build/jcvb/` and every link/asset URL
is prefixed with `/jcvb`. Set `base_path = ""` to serve from a domain root.

The generator also: optimizes team photos (resizes 20 MP originals → web JPEGs),
generates a printable white-background schedule graphic
(`…/assets/img/2026-JCVB-schedule.svg`), and content-hashes the CSS/JS URLs for
cache-busting.

## Preview locally

```bash
python -m http.server 4173 --directory build
# open http://localhost:4173/jcvb/   (mirrors the deployed sub-path)
```

## Layout

| Path | Purpose |
| --- | --- |
| `content/site.toml` | Team info, nav, external links, coaches, highlights |
| `content/schedule/2026.toml` | 2026 game data |
| `content/newsletters/*.md` | Ported newsletters (date from filename; headline/summary auto-derived, optional front matter overrides) |
| `templates/` | Jinja2 templates + `partials/` (nav, footer, volleyball-swirl macro) |
| `static/css` · `static/js` · `static/img` | Design system, motion, images |
| `_assets/jcvb-brand/` | Source brand kit (logos, fonts, `jcvb-volleyball-icon.svg`) |
| `_assets/pics/` | Source team photos + `coaches/` headshots (mapped in `site_build.py`) |
| `/build/` (repo root) | Generated output (deploy root) |

## Brand

- Colors: JC Black `#0A0203`, JC Gold `#C4B781`, Deep Gold `#B9975B`, Cream `#F5F1E6`
- Fonts (self-hosted): Crete Round (display), ITC Franklin Gothic (body/UI), Quaint Gothic (accent)
- See the live **Brand** page (`/brand/`) for the full system.

## Adding a newsletter

Drop a `YYYY-MM-DD-*.md` file into `content/newsletters/` and rebuild. The date,
headline, and summary are derived automatically; add YAML front matter
(`headline:` / `summary:`) to override.

## Notes

- Deployment (anvilor sites / CI) is intentionally not wired up yet.
- Never commit secrets; the repo `.env` is not referenced by the build.
