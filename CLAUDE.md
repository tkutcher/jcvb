# CLAUDE.md — JC Volleyball (JCVB)

Guidance for Claude Code working on anything "JC Volleyball."

## What JCVB Is

John Carroll School (Bel Air, MD) **Boys Volleyball** program — MIAA conference.
Tim Kutcher ("Coach Kutch", TK) is head coach. Work spans two locations:

| Location | What lives there |
| --- | --- |
| `/Users/tkutcher/TK/git-repos/jcvb` (this repo) | Code: static site generator + newsletter distribution |
| `~/TK/tk-vault/orgs/JCVB` (Obsidian vault) | Coaching + program ops: practice plans, scouting, roster, strategy, admin |

The vault is **synced via Obsidian Sync, not git** — edits there are live, so
never bulk-rewrite vault files. The repo is git; commit only when asked.

## This Repo

Python (uv/`pyproject.toml`, package at `src/jcvb`). Two jobs:

1. **Static site** → `sites.anvilor.com/jcvb`
   - `uv run python -m jcvb.site_build` (or `scripts/build.sh`) → `/build/jcvb/`
   - `scripts/dev.sh` builds + serves at `http://localhost:4173/jcvb`
   - `scripts/deploy.sh` pushes to Azure Blob (service-principal creds in `.env`)
   - Content: `site/content/site.toml`, `site/content/schedule/2026.toml`,
     `site/content/newsletters/*.md`. See `site/README.md` for the full layout.
2. **Newsletter distribution** — `scripts/distribute_newsletter.sh [--test]`
   sends `Next-Newsletter.md` via SendGrid, files it into
   `site/content/newsletters/`, commits, then builds + deploys.
   Always run `--test` first.

Secrets (SendGrid, Azure SP) live in `.env`, which is git-ignored. Never write
real credentials into files — use `REPLACE_ME` placeholders

### Commands

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

### TeamSnap schedule export

`src/jcvb/teamsnap_calendar.py` reads the published calendar and writes one
CSV per TeamSnap importer — Games, Practices, Other Events. They are three
separate templates with different required columns; a practice put in the
Games template is rejected ("Team 2 Type is required, Team 1 and Team 2
cannot be the same"), which is what sank the first hand-built attempt.



## The Vault Side (`orgs/JCVB`)

| Path | Purpose |
| --- | --- |
| `JCVB.md` | Hub note — links to everything, external forms/spreadsheets |
| `coach/daily-plans/` | **Practice & game-day plans**, `YYYY-MM-DD.JCVB.md` |
| `coach/notes/` | Progressions, warm-up routine, serving status, stat definitions |
| `coach/strategy/` | `playbook/JCVB-Playbook.md`, `Things-To-Teach.md`, `Basic-Volleyball-Knowledge.md` |
| `coach/roster/`, `coach/admin/` | Rosters, MIAA paperwork, receipts, governance |
| `internal/2026 JCVB Season Schedule/` | `2026-JCVB-game-schedule.md` — the authoritative game table |
| `newsletter/Next-Newsletter.md` | Draft staged for the next send |
| `public/newsletters/` | Sent newsletters (source of the repo's `site/content/newsletters/`) |
| `_archives/2025-JCVB-Archives/` | Last season — good style reference, do not edit |

## Practice Plans

The core recurring artifact. One note per team day in `coach/daily-plans/`,
named `YYYY-MM-DD.JCVB.md`. Game days get a folder of the same stem holding the
plan, lineups, report card, and scorebook images.

Anatomy of a practice plan (see `2026-08-27`, `2026-09-01` for the mature form):

1. Frontmatter: `created`, `aliases: []`, `tags:`
2. HTML header table — weekly **theme word** in caps with an emoji, left/center;
   `_gfx/jcvb-logo-hz-on-white.png` right
3. `[[JCVB]] YYYY-MM-DD`, then a reference link row
   (`[[JCVB-Playbook]] | [[JCVB Progressions]] | [[2026 JCVB Serving Status]]`)
4. **Absentees** table (Player / Est. Return), carried forward and updated
5. ***Upcoming*** — next game(s) with times
6. ***Plan*** — timed blocks, `**3:30-3:45**` style, opening with
   🧠 Classroom and closing with a wrap-up block
7. Footer link row: `[[JCVB-Playbook]] | [[Basic-Volleyball-Knowledge]] | [[Things-To-Teach]]`

Conventions that matter:
- Practice window is **3:30–5:30** in season (tryouts/preseason varied).
- Classroom is 15 min and mixes logistics, a volleyball concept, and a mental-
  skills item (breathing, visualization, journal) — see `coach/JCVB Classroom Topics.md`.
- Drill blocks link to the canonical notes rather than restating them:
  `[[JCVB Warm Up Routine]]`, `[[JCVB Passing Progressions]]`, `[[JCVB Progressions]]`,
  `[[2026 JCVB Serving Status]]`.
- Emoji prefixes recur: 🧠 classroom, 📋 logistics/debrief, 🎥 visualization,
  🫁 breathing, 📝 journal, 🏐 volleyball concept.
- The day after a match, the classroom block opens with a game debrief that
  cites the `--Report-Card` note and names 2–3 things to fix and things to keep.
- Wrap-up commonly includes net takedown for time, prehab, stretch — the 2025
  lesson in `Things-To-Teach.md` was "do some team building after every practice."

Use `/practice-plan` to draft the next one.

## Working Style Here

- Practice plans and newsletters are **drafts for TK to edit**, not final word.
  Make real coaching calls informed by the recent record; don't leave blanks.
- Prefer linking to existing vault notes over duplicating their content.
- Roster names, absences, and injuries are real minors' info — keep them in the
  vault, never in the public site or a newsletter without TK's say-so.
- When a schedule fact is needed, `2026-JCVB-game-schedule.md` wins over the
  prose schedule note.

## Obsidian Links

Vault name is `tk-vault`. To hand TK a clickable link that opens the app:

```
obsidian://open?vault=tk-vault&file=<vault-relative path, URL-encoded, no .md>
```

e.g. `obsidian://open?vault=tk-vault&file=orgs%2FJCVB%2Fcoach%2Fdaily-plans%2F2026-09-02.JCVB`

