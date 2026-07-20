# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Utilities for John Carroll Boys Volleyball (JCVB) program management:
newsletter distribution (SendGrid), the public static site
(sites.anvilor.com/jcvb, Azure blob container `jcvb`), and Anvilor Forms
managed from the command line.

## Commands

```bash
uv sync
uv run --group dev pytest tests/ -q

# Newsletters + site
uv run python -m jcvb.newsletter --test        # dry-run send
sh scripts/deploy.sh                           # build + deploy site

# Anvilor forms
uv run python -m jcvb.forms list
uv run python -m jcvb.forms validate <slug>
uv run python -m jcvb.forms publish <slug>     # create/update + publish live
uv run python -m jcvb.forms responses <slug> --data-only

# Camp feedback QR flyer (letter landscape, 300 DPI)
uv run python -m jcvb.qr_flyer
```

Secrets live in the gitignored `.env` (see `.env.example`). `jcvb.forms`
needs `ANVILOR_API_KEY` + `ANVILOR_ORG_OID` for the JCVB Anvilor org.

## Creating a new Anvilor form

1. Add `forms/<slug>.json` — the document stored on the `anvilor_forms`
   collection. Copy the shape from `forms/camp-feedback-2026.json`:
   `{"anvilor_form": {title, tags, disable_anonymous_submissions,
   submission_handling_config, display_config}}` with the visual config at
   `display_config.rui_config` (ngx-rui v1: `{rui_version: "v1", model, form}`).
   - `model` is a JSON Schema (draft 2020-12): every bound field needs a
     property (titles become default labels; `required` drives validation).
   - `form` is the control tree. Field pointers like `/liked_most` must match
     model properties.
2. `uv run python -m jcvb.forms validate <slug>` — mirrors the platform's
   vocabulary + model/form consistency checks.
3. `uv run python -m jcvb.forms publish <slug>` — creates the document,
   records its OID in `forms/registry.json` (commit it), and publishes live
   at `https://forms.anvilor.com/<oid>`. Re-running updates + republishes.

### ngx-rui v1 control vocabulary

- Layout: `vbox`, `hbox`, `panel` (label), `tabs` — children in `items`.
- Inputs: `single_line_text`, `multi_line_text` (`autosize`,
  `autosize_min_rows`/`_max_rows`), `standard_number`, `numeric_stepper`,
  `standard_us_phone`, `standard_date`, `standard_datetime`,
  `standard_checkbox`, `standard_file_upload`, `standard_address`.
- Selects (require `select_options: [{value, display}]`):
  `standard_radio_buttons` (≤5 options), `single_select_dropdown`,
  `multi_select_dropdown`, `multi_select_checkboxes` (binds array),
  `button_toggle` (2–4 short options), `likert` (`rows: [{field, label}]`
  + `scale` instead of select_options; binds an object).
- Display: `raw_content` (`content`: HTML string or EEL expression), `button`.
- Common node props: `control`, `field` (RFC 6901 pointer), `id`, `label`,
  `visible`/`disabled` (bool or EEL, e.g.
  `{"#field_value": {"path": "/x"}}`).

Authoritative reference (local platform checkout):
`~/DICORP/gitlab/anvilor/anvilor-platform/src/anvilor/platform/cxs/anvilor_forms/ai/data/rui_v1_controls.json`.

## Rules

1. The Anvilor API is plain REST (`anvilor-api-key`/`anvilor-org-oid`
   headers) — keep `src/jcvb/forms.py` dependency-light; do not add the
   private DICORP `anvilor-client` package to this personal repo.
2. Eel-operator calls (`publish_live`) take BSON extended JSON — ObjectIds
   travel as `{"$oid": "..."}`.
3. `forms/registry.json` maps slug → published form OID. Never hand-edit
   OIDs; publishing writes them back. Commit registry updates.
4. Public-facing surveys set `disable_anonymous_submissions: false`.
5. Brand: JC black `#0A0203`, JC gold `#C4B781` (deep gold `#B9975B`).
   Assets in `site/_assets/jcvb-brand/`. Tagline: "One Program. One
   Standard. Patriots Volleyball."
