# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

Utilities for John Carroll Boys Volleyball (JCVB) program management:
newsletter distribution (SendGrid), the public static site
(sites.anvilor.com/jcvb, Azure blob container `jcvb`), Anvilor Forms
managed from the command line, and the TeamSnap schedule export.

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

# RSVP roll-up (head count, players covered, duplicate/no-player RSVPs)
uv run python -m jcvb.rsvp_report [--slug <slug>] [--json]

# Camp feedback QR flyer (letter landscape, 300 DPI)
uv run python -m jcvb.qr_flyer

# TeamSnap schedule export (three CSVs → .outputs/teamsnap/)
uv run python -m jcvb.teamsnap_calendar
sh scripts/teamsnap-export.sh ~/Desktop          # cron-safe wrapper
```

Secrets live in the gitignored `.env` (see `.env.example`). `jcvb.forms`
needs `ANVILOR_API_KEY` + `ANVILOR_ORG_OID` for the JCVB Anvilor org.
`jcvb.teamsnap_calendar` needs `JCVB_CALENDAR_URL` — the published iCloud
feed URL, which is itself a bearer token, so it never goes in source.

## TeamSnap schedule export

`src/jcvb/teamsnap_calendar.py` reads the published calendar and writes one
CSV per TeamSnap importer — Games, Practices, Other Events. They are three
separate templates with different required columns; a practice put in the
Games template is rejected ("Team 2 Type is required, Team 1 and Team 2
cannot be the same"), which is what sank the first hand-built attempt.

Classification runs on the emoji-stripped SUMMARY:

- Game — `JC vs. <opponent>` → Home, `JC @ <opponent>` → Away, or a
  championship/semi-final/playoff title → opponent `TBD` with both sides
  blank (the importer reads blank as TBD).
- Practice — matches `practice|tryout|workout|lift|training|weightroom`.
- Other — everything else (Media Day, the Welcome Reception, …).

Times, durations, and recurrence come straight from the feed; RRULEs and
their per-occurrence overrides are expanded by `recurring-ical-events`.
All-day entries are skipped by default — in this calendar they shadow a
timed event on the same day — and listed in the run summary.

One gotcha lives entirely in the wizard, not the file: its team-mapping
step lists each distinct team value and defaults unmatched ones to *Skip*.
Leaving `John Carroll Boys Volleyball (Varsity)` on Skip drops every row,
and the report blames "All rows with a value of ... were selected to be
skipped" — which reads like a validation error but isn't. Set that
dropdown to the real team before continuing.

Venues are the other importer trap: it cannot create venues or sub-venues,
and it rejects a Venue with no Sub-Venue. Calendar locations are postal
addresses that match nothing in TeamSnap, so a location is only emitted
when `teamsnap-venues.json` maps it to a real Venue **and** Sub-Venue.
Otherwise both stay blank and the address goes into Notes, which always
imports. Unmapped locations are named in the warnings after every run.

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
