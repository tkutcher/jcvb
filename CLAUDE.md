# CLAUDE.md — JC Volleyball (JCVB)

John Carroll School (Bel Air, MD) **Boys Volleyball**, MIAA. Tim Kutcher
("Coach Kutch", TK) is head coach. Work spans two places:

| Location | What lives there | Rules |
| --- | --- | --- |
| `~/TK/github/jcvb` (this repo) | Static site + newsletter/postgame/forms tooling | git — commit only when asked |
| `~/TK/tk-vault/orgs/JCVB` | Coaching ops: practice plans, scouting, roster, admin | Obsidian Sync, **not** git — edits are live, never bulk-rewrite |

## Recurring jobs → use the command

| Job | Command | Details live in |
| --- | --- | --- |
| Draft the next practice plan | `/practice-plan` | `.claude/commands/practice-plan.md` |
| Process a played match | `/postgame` | `.claude/skills/postgame/SKILL.md` |
| Build + deploy the site | `/deploy` | `.claude/commands/deploy.md` (staging unless told prod) |

Don't re-derive those procedures here — read the command/skill file.

## Repo map

| Path | Purpose |
| --- | --- |
| `src/jcvb/site_build.py` | Static site generator → `build/jcvb/` |
| `src/jcvb/newsletter.py` | SendGrid newsletter send |
| `src/jcvb/postgame.py` | Game file → result page, recap, report card, score form |
| `src/jcvb/hudl.py` | Official Hudl Assist box scores (**internal only**) |
| `src/jcvb/forms.py`, `rsvp_report.py` | Anvilor forms + RSVP roll-up (`forms/*.json`) |
| `src/jcvb/teamsnap_calendar.py`, `teamsnap_schedule.py` | Calendar → TeamSnap import CSVs |
| `src/jcvb/audience.py` | Who each artifact is for (public / team / coaches / hc) |
| `site/content/` | `site.toml`, `schedule/2026.toml`, `games/*.toml`, `newsletters/*.md` |
| `site/README.md` | Full site layout, templates, assets |
| `scripts/` | `build.sh`, `dev.sh` (localhost:4173/jcvb), `deploy.sh`, `distribute_newsletter.sh` |
| `.env` | Secrets, git-ignored (see `.env.example`) |

## Commands

```bash
uv sync
uv run --group dev pytest tests/ -q

uv run python -m jcvb.site_build                 # build only
sh scripts/dev.sh                                # build + serve locally
sh scripts/deploy.sh [staging|prod] [--dry-run]

uv run python -m jcvb.newsletter --test          # ALWAYS test first
sh scripts/distribute_newsletter.sh [--test]     # send + file + commit + deploy

uv run python -m jcvb.forms list|validate <slug>|publish <slug>|responses <slug>
uv run python -m jcvb.rsvp_report [--slug <slug>] [--json]
uv run python -m jcvb.teamsnap_calendar          # 3 CSVs → .outputs/teamsnap/
uv run python -m jcvb.teamsnap_schedule          # JV/Varsity split → outputs/
```

TeamSnap needs three separate CSVs (Games / Practices / Other Events) — the
importer templates have different required columns and reject a practice filed
as a game. Env: `ANVILOR_API_KEY` + `ANVILOR_ORG_OID` for forms,
`JCVB_CALENDAR_URL` (itself a bearer token) for the calendar.

## Vault map (`~/TK/tk-vault/orgs/JCVB`)

| Path | Purpose |
| --- | --- |
| `JCVB.md` | Hub note — links to everything |
| `coach/daily-plans/` | Practice & game-day plans, `YYYY-MM-DD.JCVB.md` |
| `coach/notes/` | Progressions, warm-up routine, serving status, stat definitions |
| `coach/strategy/` | `playbook/JCVB-Playbook.md`, `Things-To-Teach.md`, `Basic-Volleyball-Knowledge.md` |
| `coach/roster/`, `coach/admin/` | Rosters, MIAA paperwork, receipts |
| `internal/2026 JCVB Season Schedule/2026-JCVB-game-schedule.md` | **Authoritative** game table |
| `newsletter/Next-Newsletter.md` | Draft staged for the next send |
| `public/newsletters/` | Sent newsletters (source for `site/content/newsletters/`) |
| `_archives/2025-JCVB-Archives/` | Last season — style reference, do not edit |

## Working style

- Plans and newsletters are **drafts for TK to edit**. Make real coaching calls
  informed by the recent record; don't leave blanks.
- Never invent a stat, result, or roster fact. Flag the unknown instead.
- Roster names, absences, injuries are real minors' info — vault only, never the
  public site or a newsletter without TK's say-so.
- Never write real credentials into files; use `REPLACE_ME` placeholders.
- Link to existing vault notes rather than duplicating their content.
- Schedule conflicts: `2026-JCVB-game-schedule.md` wins.

Clickable vault link (vault name `tk-vault`, path URL-encoded, no `.md`):

```
obsidian://open?vault=tk-vault&file=orgs%2FJCVB%2Fcoach%2Fdaily-plans%2F2026-09-02.JCVB
```
