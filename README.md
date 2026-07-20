# `jcvb`

Utilities for JC Volleyball program management.

- **Newsletters** — `scripts/distribute_newsletter.sh` (SendGrid)
- **Public site** — `site/` sources, deployed to sites.anvilor.com/jcvb
  (`scripts/deploy.sh`)
- **Anvilor forms** — committed configs in `forms/`, published via
  `uv run python -m jcvb.forms publish <slug>` (see CLAUDE.md)
- **Camp QR flyer** — `uv run python -m jcvb.qr_flyer` renders a
  print-ready letter-landscape graphic in `build/`

Secrets go in `.env` — copy `.env.example` and fill in real values.