---
description: Draft the next JCVB practice plan in the vault, in the established style
argument-hint: "[YYYY-MM-DD] [--force] [notes for the plan]"
---

Draft the next JC Volleyball practice plan in the Obsidian vault.

Arguments (all optional): `$ARGUMENTS`
- A `YYYY-MM-DD` date → plan that day instead of the default.
- `--force` → rewrite the plan even if the file already exists.
- Any other text → TK's steer for this plan (emphases, absences, schedule
  changes). Treat it as authoritative over anything you infer.

## Paths

- Vault: `~/TK/tk-vault`
- Plans: `~/TK/tk-vault/orgs/JCVB/coach/daily-plans/`
- File: `<date>.JCVB.md` (game days use a folder `<date>.JCVB/<date>.JCVB.md`)

## 1. Pick the date

Default is **tomorrow**. Skip Saturday and Sunday — if tomorrow is a weekend,
target the next weekday.

Stop without writing if:
- The plan file (or its game-day folder) already exists and `--force` was not
  passed. Report the existing plan's Obsidian link and stop.
- The target date is a **game day** in
  `orgs/JCVB/internal/2026 JCVB Season Schedule/2026-JCVB-game-schedule.md`.
  Game days use a different format (lineups, report card). Say so, summarize
  the matchup, and ask whether to draft a game-day plan instead.

## 2. Read the context

Read all of these before drafting:
- The **last 2–3 plans** in `coach/daily-plans/` — they carry the current
  weekly theme word, the absentee table, and what was just covered.
- The most recent game folder's `*--Report-Card.md` and `*-Stats.md` if the
  team has played since the last practice, or if the last practice has not yet
  debriefed it.
- `coach/notes/2026 JCVB Serving Status.md` — who is on yellow/red lights.
- `coach/notes/JCVB Progressions.md`, `JCVB Passing Progressions.md`,
  `JCVB Warm Up Routine.md`.
- `coach/strategy/Things-To-Teach.md`, `coach/strategy/playbook/JCVB-Playbook.md`.
- `coach/JCVB Classroom Topics.md` — for the mental-skills item.
- The game schedule table — for the *Upcoming* section.

## 3. Draft the plan

Match the structure of the recent plans exactly — `2026-08-27.JCVB.md` and
`2026-09-01.JCVB.md` are the mature form. Anatomy, in order:

1. Frontmatter: `created`, `aliases: []`, `tags:`
2. HTML header table — the weekly **theme word** in caps with an emoji,
   left/center; `_gfx/jcvb-logo-hz-on-white.png` right
3. `[[JCVB]] YYYY-MM-DD`, then a reference link row
   (`[[JCVB-Playbook]] | [[JCVB Progressions]] | [[2026 JCVB Serving Status]]`)
4. **Absentees** table (Player / Est. Return), carried forward and updated
5. ***Upcoming*** — next game(s) with times
6. ***Plan*** — timed blocks, `**3:30-3:45**` style, opening with 🧠 Classroom
   and closing with a wrap-up block
7. Footer link row:
   `[[JCVB-Playbook]] | [[Basic-Volleyball-Knowledge]] | [[Things-To-Teach]]`

Conventions that matter:
- Practice window is **3:30–5:30** in season (tryouts/preseason varied).
- Classroom is 15 min and mixes logistics, a volleyball concept, and a mental-
  skills item (breathing, visualization, journal).
- Emoji prefixes recur: 🧠 classroom, 📋 logistics/debrief,
  🎥 visualization, 🫁 breathing, 📝 journal, 🏐 volleyball concept.
- Wrap-up commonly includes net takedown for time, prehab, stretch — and the
  2025 lesson in `Things-To-Teach.md` was “do some team building after every
  practice.”

Rules for the content:
- **Theme word**: carry forward the current week's word. If the target date
  starts a new week (Monday), pick one that fits what the team needs next and
  flag that you changed it.
- **Absentees**: copy the table forward; drop anyone whose est. return has
  passed, and apply anything TK said in `$ARGUMENTS`.
- **Plan blocks**: real timed blocks covering 3:30–5:30, opening with a 15-min
  🧠 Classroom and closing with a wrap-up. Make actual coaching decisions —
  the emphases should follow from the last report card's weak columns, what the
  last practice did *not* cover, and the next opponent. Link to the canonical
  notes rather than restating drills.
- After a match, the classroom leads with a 📋 debrief that cites the report
  card and names 2–3 fixes and 2–3 things to keep.
- Include a mental-skills item (🫁 breathing / 🎥 visualization / 📝 journal)
  drawn from `JCVB Classroom Topics.md`, rotating rather than repeating.
- Do not invent results, stats, or roster facts. If something is unknown, leave
  a short bracketed prompt for TK rather than guessing.

## 4. Report back

Write the file, then reply with:
- The date and theme word.
- A 3–5 bullet summary of what the practice emphasizes and *why* (tie it to the
  report card / recent practices).
- Anything TK needs to confirm or fill in.
- A clickable Obsidian link:
  `obsidian://open?vault=tk-vault&file=orgs%2FJCVB%2Fcoach%2Fdaily-plans%2F<date>.JCVB`

Keep the reply short. The plan is the deliverable.
