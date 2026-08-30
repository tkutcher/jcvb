---
name: postgame
description: Process a JCVB match after it's played — file the scans, transcribe the tally sheet and scorebook into a game file, publish the result and recap to the site, generate the Keys to the Game report card, and stage the school's score-reporting form. Use when TK provides a scorebook scan, an assistant-coach tally sheet, and a verbal recap of a game.
---

# Post-game processing

One game file drives everything. Transcribe once, generate the rest.

**Never invent a stat.** If a tally cell is unreadable, transcribe your best
reading and flag the cell — do not average, guess, or quietly drop it.

## Inputs TK provides

1. A scan of the official scorebook (set scores are authoritative here).
2. A scan of the assistant coach's tally sheet — AE, SE, Big Boy kills, Big Boy
   blocks, net violations, communication errors, doubles/lifts, per set.
3. A verbal recap in his own words.

## Step 1 — Write the game file

Create `site/content/games/<YYYY-MM-DD>-<opponent-slug>.toml`. Copy the shape
from `2026-08-26-harford-tech.toml`. It holds the set scores `[[JC, opponent], …]`,
the per-set tallies, the recap prose, and the report-card rows that need eyes.

Read set scores from the book's running-score boxes, not from the tally sheet's
W/L row — then check they agree. They should; say so if they don't.

Transcribe the point-by-point too, into `[scorebook]`: for each set, the running
score at the **end of each service term**, per team, plus who served first. The
book records a serving team's points in the server's row, so those diffs are the
scoring runs, and interleaving the two teams replays the set. That is what
settles three report-card rows — race to 15, our 5+ run, their 5+ run — which
otherwise need a human. `postgame` refuses to load a set whose last term-end
score disagrees with the set score, so a misread digit surfaces immediately
rather than quietly skewing a run.

The tally sheets are photographed on a clipboard and skew, so circled totals
drift into the next column. Cross-check every circled total against its tally
marks. Where they disagree, put your reading in the file and list the cell under
"Transcription notes" in the vault stats file so TK can settle it.

```bash
uv run python -m jcvb.postgame check <slug>     # validates shape + set counts
uv run python -m jcvb.postgame summary <slug>   # result, totals, what's unfilled
```

## Step 2 — File everything in the vault

Game folder: `~/TK/tk-vault/orgs/JCVB/coach/daily-plans/<YYYY-MM-DD>.JCVB/`

| File | What |
| --- | --- |
| `<date>.JCVB.md` | the COMMUNICATE plan (already there pre-game) |
| `<date>--vs-<Opponent>-Stats.md` | transcription + set scores + notes |
| `<date>--vs-<Opponent>-Report-Card.md` | generated in step 4 |
| `Shaw-Tallies-vs-<Opponent>.jpg` | the tally scan |
| `<date>--vs-<Opponent>-Scorebook-p<N>.jpg` | the scorebook scan, one per page |

Scans arrive as chat attachments and are **not on disk** — you cannot save them
yourself. Ask TK to drop them in the folder, then rename them to the names above;
the report card embeds `Shaw-Tallies-vs-<Opponent>.jpg` by that exact name.

Serve receive comes on its own libero-tracking sheet: every reception rated 0-3,
one digit per pass, per player per set. Transcribe it verbatim into
`[serve_receive]` — the team rating for a set is the mean of the digits, computed
in `ServeReceive`, and it settles the SR row on the card. That sheet's bottom row
is **aces conceded**, not aces served; keep it in `aces_against` and never mix it
with `stats.aces`.

### Official stats (Hudl Assist), a day or two later

Hudl Assist returns the authoritative box score after the match. Name the export
so a season of them sorts and parses:

    <YYYY-MM-DD>--vs-<Opponent>-Hudl-<Scope>.csv

matching the scorebook and tally scans. `<Scope>` is the cut it covers —
`Match-Totals`, `Set-1`, `Serve-Receive`. Hudl's own filenames ("JCS vs HTHS —
All Athletes — Whole Match — Averages.csv") collide across a season.

```bash
uv run python -m jcvb.hudl note <csv> --out "<game folder>/<date>--vs-<Opponent>-Official-Stats.md"
uv run python -m jcvb.hudl board          # season + trending S% on the serving board
uv run python -m jcvb.hudl list
```

**These files never go to the site.** They carry every player's error counts, so
they are Coaches-level: read them for highlights and season aggregates, publish
nothing from them but kills, aces and blocks.

Official numbers win over the in-game tally sheet for anything public — the
tallies are counted live, Hudl is counted off the film. When they disagree, say
so rather than picking silently.

The serving board's lights are TK's coaching judgement; `hudl board` fills only
the Season and Trending S% columns and must never touch them.

## Step 3 — Publish result + recap

Every scheduled game already has a detail page at `/games/<slug>/` — times,
venue, stream links — and the whole schedule row (and mobile card) links to it.
Dropping a file in `site/content/games/` fills that page in: box score, recap
prose, full stat table, plus a result chip on the schedule row.

The slug is shared: `postgame.slugify(date, opponent)` builds it on both sides,
so a game file named `<date>-<opponent-slug>.toml` lands on the right page.

```bash
uv run python -m jcvb.site_build
```

The recap must give **every set score**, never just "3-0".

### Tone — this one is not negotiable

A public recap is **always supportive**. Highlight what players and the program
did well; name players for the things they did. Credit an opponent's strengths
rather than framing a loss as our failure, and never single out a player for a
mistake, a bad stretch, or an error count. If TK's own notes are blunt, translate
them into what the team did well and what there is to build on — the internal
report card is where the criticism belongs, and it is for the Team audience, not
the public.

Ask TK for the moments worth naming; he will often flag one (a set-clinching
ace, a big dig). Work it into the prose rather than appending it.

**Serve receive is a primary recap stat.** Lead on it alongside aces, kills and
blocks — it is the number that explains why the offense did or did not work.
Frame it the way any public stat gets framed here: cite the sets where the
passing held up and what it produced, rather than the sets where it did not.

**Public vs internal.** The site publishes only the objective stats — aces,
kills, blocks (`postgame.PUBLIC_STAT_KEYS`). Service errors, attack errors, net
violations, communication errors and doubles are coaching judgment calls, not a
record of what happened: they belong to the team, and stay in the report card and
the vault stats note. Templates only ever receive `public_stats()`, so this holds
by construction — keep it that way, and keep error counts out of recap prose and
the form's recap box too.

## Step 4 — Report card

```bash
uv run python -m jcvb.postgame report-card <slug> \
  --out "~/TK/tk-vault/orgs/JCVB/coach/daily-plans/<date>.JCVB/<date>--vs-<Opponent>-Report-Card.md"
```

Rows that are arithmetic on the tallies are marked automatically (net violations,
communication errors, AE ≤ 3, SE ≤ 2, blocks ≥ 2, kills ≥ 5, aces > SE, and a set
lost without reaching 15). The tallies always win — a manual mark only fills a
cell the stat sheet cannot answer.

With `[scorebook]` transcribed, the run rows resolve too. Four rows are left for
a human: rotation errors, meet in the center, no complaints, and SR rating (that
one needs the libero tracking sheet). Energy and "one great defensive play" are
often answered by TK's own write-up — fill those from his words and cite them in
a trailing comment. Leave the rest as dots — the card prints
"rating pending" rather than grading a half-filled sheet, and TK finishes it in
`[report_card]`.

The rating is `count-of-✅ / sets-played`, banded by the key at the foot of the card.

### The write-up at the top of the card is TK's, and it is internal

`[card] writeup` in the game file — his words, for the Team. It is **never**
derived from `[recap]`: the public recap is written to be supportive for
families, the card is where the blunt read belongs ("we were way too flat"). A
card with no write-up prints `(write-up to come)` rather than borrowing the
recap. `absorb-card` reads an edited write-up back, so TK can rewrite it in
Obsidian and it sticks through the next render.

The card ends with **Match totals** — every team stat with its per-set rate, the
team serve-receive rating, and aces conceded — followed by a **Season to date**
block of per-match and per-set averages once more than one match has been played.
Both are generated; do not hand-maintain them.

## Step 5 — Stage the score form

```bash
uv run python -m jcvb.postgame form-url <slug>
```

Prints a prefilled Google Form URL: date, Boys/Varsity/Volleyball, opponent,
score, recap, records as of that game, and the next game.

The **Score** box must always spell out the individual sets alongside the match
score, winner first — `Harford Tech 3-2 (23-25, 25-22, 25-19, 16-25, 5-15)`.
That is `Game.form_score`; never send the bare match score.

**Open it and stop.** Submitting is TK's click, every time — never submit for
him. Records exclude scrimmages.

## Step 6 — Report back

Give TK: the result with set scores, the recap URL, what the report card scored
and what it still needs, the form link, the two scan filenames to drop in, and
any transcription cell you flagged. Note that the site needs `sh scripts/deploy.sh`
before the form's recap link resolves.
