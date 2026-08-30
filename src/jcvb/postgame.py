"""Post-game processing: one game file in, every downstream artifact out.

After a match there are four jobs — file the data, put the result and a recap
on the site, fill in the Keys-to-the-Game report card, and report the score to
the school. All four read the same source: `site/content/games/<slug>.toml`,
written once from the scorebook and the assistant coach's tally sheet.

Everything derivable is derived here rather than retyped: set results, the
match score, season records, the report-card rows that are pure arithmetic on
the tallies, and the prefilled Google Form URL. What is left for a human is
what a human actually has to judge — the recap prose and the eight report-card
rows no stat sheet can answer.

Usage:
    uv run python -m jcvb.postgame summary     <slug>
    uv run python -m jcvb.postgame report-card <slug> [--out PATH]
    uv run python -m jcvb.postgame form-url    <slug>
    uv run python -m jcvb.postgame check       <slug>
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tomllib
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from jcvb import audience
from jcvb._consts import REPO_ROOT

GAMES_DIR = REPO_ROOT / "site" / "content" / "games"

# The game file is authored in Obsidian, in that game's folder, next to the
# scans and the notes it came from — that is where TK is working. The repo keeps
# a synced copy so the site still builds from a clean checkout without the vault
# mounted. The vault wins on conflict; it is the one being edited.
VAULT_GAMES_ROOT = Path(
    os.environ.get(
        "JCVB_VAULT_GAMES",
        Path.home() / "TK" / "tk-vault" / "orgs" / "JCVB" / "coach" / "daily-plans",
    )
)

# The school's score-reporting form. Field ids come from the form's own
# FB_PUBLIC_LOAD_DATA_ blob; re-scrape them if the form is ever rebuilt.
FORM_ID = "1FAIpQLSf-r46lM29qZY-cgBqOljTEDDCoNVU4KCA6rVM8i29poG2XYQ"
FORM_URL = f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform"
FORM_FIELDS = {
    "date": "entry.1868809592",       # date field — prefills as _year/_month/_day
    "gender": "entry.1016469640",
    "level": "entry.603921588",
    "sport": "entry.2146639926",
    "opponent": "entry.792620277",
    "score": "entry.642238910",
    "recap": "entry.209333594",
    "overall_record": "entry.1790222161",
    "conference_record": "entry.988434167",
    "next_game": "entry.659027650",
    "other": "entry.1867249442",
}

SITE_BASE = "https://sites.anvilor.com/jcvb"

def slugify(date_value: date, opponent: str) -> str:
    """`2026-08-26-harford-tech` — the id a game file and its site page share."""
    cleaned = "".join(
        c.lower() if c.isalnum() else "-" for c in opponent
    ).strip("-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return f"{date_value.isoformat()}-{cleaned}"


STAT_KEYS = (
    "aces",
    "service_errors",
    "kills",
    "blocks",
    "attack_errors",
    "communication_errors",
    "net_violations",
    "doubles_lifts",
)

# What the public site may show. The rest — service and attack errors, net
# violations, communication errors, doubles — are judgment calls a coach tallies
# to coach from, not a record of what happened, and they belong to the team.
# Aces, kills and blocks are the objective ones. `Game.public_stats()` is the
# only stat surface the site templates get, so this is enforced rather than
# merely intended.
PUBLIC_STAT_KEYS = ("aces", "kills", "blocks")

# Who each generated artifact is for (see jcvb/audience.py). The stats note
# carries the full error tallies and the transcription doubts, so it is a
# coaches' document; the report card is read with the team; the site is public.
STATS_NOTE_AUDIENCE = "coaches"
REPORT_CARD_AUDIENCE = "team"

# Obsidian applies these as CSS classes on the note, which is what scopes
# obsidian/jcvb.css to the generated notes and nothing else in the vault.
REPORT_CARD_CSS_CLASS = "jcvb-report-card"
STATS_NOTE_CSS_CLASS = "jcvb-stats-note"
SITE_AUDIENCE = "public"


@dataclass
class Game:
    slug: str
    date: date
    opponent: str
    designation: str
    home_away: str
    sets: list[tuple[int, int]]          # (JC, opponent) per set
    stats: dict[str, list[int]]
    recap_headline: str = ""
    recap_body: str = ""
    card_writeup: str = ""      # internal, Team audience — never the public recap
    notes: dict[str, str] = field(default_factory=dict)
    manual_marks: dict[str, str] = field(default_factory=dict)
    scorebook: object = None
    serve_receive: object = None
    official: dict = field(default_factory=dict)   # Hudl Assist match totals

    # --- derived ------------------------------------------------------------
    @property
    def sets_played(self) -> int:
        return len(self.sets)

    @property
    def set_results(self) -> list[str]:
        return ["W" if jc > opp else "L" for jc, opp in self.sets]

    @property
    def sets_won(self) -> int:
        return self.set_results.count("W")

    @property
    def sets_lost(self) -> int:
        return self.set_results.count("L")

    @property
    def won(self) -> bool:
        return self.sets_won > self.sets_lost

    @property
    def result(self) -> str:
        return "W" if self.won else "L"

    @property
    def match_score(self) -> str:
        """Sets, winner first — the form asks for `JC 3-2` / `Opponent 3-2`."""
        high, low = sorted((self.sets_won, self.sets_lost), reverse=True)
        return f"{high}-{low}"

    @property
    def jc_set_score(self) -> str:
        """Sets from JC's side — `2-3` — for anything on our own site."""
        return f"{self.sets_won}-{self.sets_lost}"

    @property
    def score_line(self) -> str:
        winner = "JC" if self.won else self.opponent
        return f"{winner} {self.match_score}"

    @property
    def form_score(self) -> str:
        """What goes in the school form's Score box: the match score, winner
        first, with every set spelled out —
        `Harford Tech 3-2 (23-25, 25-22, 25-19, 16-25, 5-15)`.
        """
        return f"{self.score_line} ({self.set_scores})"

    @property
    def set_scores(self) -> str:
        """`23-25, 25-22, …` from JC's point of view."""
        return ", ".join(f"{jc}-{opp}" for jc, opp in self.sets)

    @property
    def is_conference(self) -> bool:
        return self.designation == "conference"

    @property
    def counts_toward_record(self) -> bool:
        """Scrimmages are not results — they never touch a record."""
        return self.designation != "scrimmage"

    @property
    def recap_url(self) -> str:
        return f"{SITE_BASE}/games/{self.slug}/"

    def totals(self) -> dict[str, int]:
        return {key: sum(values) for key, values in self.stats.items()}

    @property
    def has_official(self) -> bool:
        return bool(self.official)

    def public_stats(self) -> dict[str, list[int]]:
        """Per-set splits for the public table — the live tally sheet.

        Empty once official totals exist: the tally is counted in the gym and
        the official book off the film, and they do not always agree. Publishing
        set columns that sum to a different number than the published total is
        worse than publishing no split at all.
        """
        if self.has_official:
            return {}
        return {
            key: self.stats[key]
            for key in PUBLIC_STAT_KEYS
            if self.stats.get(key)
        }

    def public_totals(self) -> dict[str, int]:
        """Official totals when we have them, otherwise the tally sheet's."""
        if self.has_official:
            return {
                key: self.official[key]
                for key in PUBLIC_STAT_KEYS
                if key in self.official
            }
        return {
            key: sum(values)
            for key, values in self.stats.items()
            if key in PUBLIC_STAT_KEYS and values
        }

    def stat(self, key: str, set_index: int) -> int:
        return self.stats[key][set_index]


def vault_game_paths(root: Path = VAULT_GAMES_ROOT) -> dict[str, Path]:
    """slug -> game file, for every game folder in the vault."""
    if not root.exists():
        return {}
    return {
        path.stem: path
        for folder in sorted(root.iterdir())
        if folder.is_dir()
        for path in sorted(folder.glob("*.toml"))
    }


def resolve_game_path(
    slug: str, games_dir: Path = GAMES_DIR, vault_root: Path = VAULT_GAMES_ROOT
) -> Path:
    """The file to read and write: the vault's copy when there is one."""
    return vault_game_paths(vault_root).get(slug, games_dir / f"{slug}.toml")


def sync_from_vault(games_dir: Path = GAMES_DIR, root: Path = VAULT_GAMES_ROOT):
    """Copy vault game files into the repo so the site builds without it.

    Returns the slugs that changed. A quiet no-op when the vault is not mounted,
    so a build elsewhere just uses whatever is committed.
    """
    copied = []
    for slug, path in vault_game_paths(root).items():
        target = games_dir / f"{slug}.toml"
        source_text = path.read_text(encoding="utf-8")
        if not target.exists() or target.read_text(encoding="utf-8") != source_text:
            games_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(source_text, encoding="utf-8")
            copied.append(slug)
    return copied


def load_game(
    slug: str, games_dir: Path = GAMES_DIR, vault_root: Path = VAULT_GAMES_ROOT
) -> Game:
    path = resolve_game_path(slug, games_dir, vault_root)
    if not path.exists():
        raise SystemExit(f"No game file at {path}")
    return parse_game(tomllib.loads(path.read_text(encoding="utf-8")), slug)


def parse_game(data: dict, slug: str) -> Game:
    game = data["game"]
    stats = {key: list(data.get("stats", {}).get(key, [])) for key in STAT_KEYS}
    sets = [tuple(pair) for pair in game["sets"]]

    for key, values in stats.items():
        if values and len(values) != len(sets):
            raise SystemExit(
                f"{slug}: stats.{key} has {len(values)} entries but the match "
                f"went {len(sets)} sets"
            )

    raw_date = game["date"]
    parsed = (
        raw_date if isinstance(raw_date, date)
        else datetime.strptime(raw_date, "%Y-%m-%d").date()
    )
    game_obj = Game(
        slug=slug,
        date=parsed,
        opponent=game["opponent"],
        designation=game.get("designation", "conference"),
        home_away=game.get("home_away", "home"),
        sets=sets,
        stats=stats,
        recap_headline=data.get("recap", {}).get("headline", ""),
        recap_body=data.get("recap", {}).get("body", "").strip(),
        card_writeup=data.get("card", {}).get("writeup", "").strip(),
        official={k: v for k, v in data.get("official", {}).items() if k != "source"},
        notes=data.get("notes", {}),
        manual_marks=data.get("report_card", {}),
    )
    game_obj.scorebook = Scorebook(data.get("scorebook", {}), sets, slug)
    game_obj.serve_receive = ServeReceive(
        data.get("serve_receive", {}), len(sets), slug
    )
    return game_obj


def load_season(games_dir: Path = GAMES_DIR, season: int | None = None) -> list[Game]:
    games = [load_game(p.stem, games_dir) for p in sorted(games_dir.glob("*.toml"))]
    if season is not None:
        games = [g for g in games if g.date.year == season]
    return sorted(games, key=lambda g: g.date)


def records(games: list[Game], through: date | None = None) -> dict[str, str]:
    """Overall and conference records, scrimmages excluded."""
    played = [g for g in games if g.counts_toward_record]
    if through is not None:
        played = [g for g in played if g.date <= through]
    overall = [g for g in played if g.won]
    conference = [g for g in played if g.is_conference]
    return {
        "overall": f"{len(overall)}-{len(played) - len(overall)}",
        "conference": (
            f"{len([g for g in conference if g.won])}-"
            f"{len([g for g in conference if not g.won])}"
        ),
    }


# --- scorebook -----------------------------------------------------------------
# The book records, for each service term, the serving team's running score. So
# the diffs of one team's term-end scores ARE its scoring runs, and interleaving
# the two teams' terms replays the set point by point.


def runs(cumulative: list[int]) -> list[int]:
    """Term-end scores -> the length of each scoring run."""
    out, previous = [], 0
    for value in cumulative:
        out.append(value - previous)
        previous = value
    return out


def longest_run(cumulative: list[int]) -> int:
    return max(runs(cumulative), default=0)


def race_to(cumulative_jc: list[int], cumulative_opp: list[int],
            first_serve: str, target: int = 15) -> str | None:
    """Who reached `target` first — 'jc', 'opp', or None if neither did.

    Service terms strictly alternate: a team serves until it loses a rally.
    """
    order = ("jc", "opp") if first_serve == "jc" else ("opp", "jc")
    queues = {"jc": list(cumulative_jc), "opp": list(cumulative_opp)}
    score = {"jc": 0, "opp": 0}
    while any(queues.values()):
        for team in order:
            if not queues[team]:
                continue
            score[team] = queues[team].pop(0)
            if score[team] >= target:
                return team
    return None


class Scorebook:
    """Per-set service terms, read off the official book."""

    def __init__(self, data: dict, sets: list[tuple[int, int]], slug: str):
        self.jc = [list(term) for term in data.get("jc", [])]
        self.opp = [list(term) for term in data.get("opp", [])]
        self.first_serve = list(data.get("first_serve", []))
        self._validate(sets, slug)

    def _validate(self, sets: list[tuple[int, int]], slug: str) -> None:
        """A transcription is only trustworthy if each side's last term-end
        score equals the set score in the book's final box."""
        if not self.jc:
            return
        for i, (jc_score, opp_score) in enumerate(sets):
            for label, terms, expected in (
                ("jc", self.jc, jc_score),
                ("opp", self.opp, opp_score),
            ):
                if i >= len(terms):
                    raise SystemExit(f"{slug}: scorebook.{label} is missing set {i + 1}")
                if terms[i] and terms[i][-1] != expected:
                    raise SystemExit(
                        f"{slug}: scorebook.{label} set {i + 1} ends at "
                        f"{terms[i][-1]} but the set score says {expected}"
                    )

    def __bool__(self) -> bool:
        return bool(self.jc)

    def jc_longest(self, i: int) -> int:
        return longest_run(self.jc[i])

    def opp_longest(self, i: int) -> int:
        return longest_run(self.opp[i])

    def race_winner(self, i: int, target: int = 15) -> str | None:
        serve = self.first_serve[i] if i < len(self.first_serve) else "jc"
        return race_to(self.jc[i], self.opp[i], serve, target)


# --- serve receive -------------------------------------------------------------
# The libero-tracking sheet rates every reception 0-3, one digit per pass, per
# player per set. The team rating for a set is the mean of those digits — so the
# sheet is transcribed verbatim and the arithmetic happens here.

SR_TARGET = 2.0


class ServeReceive:
    """Per-set reception ratings, as written on the tracking sheet."""

    def __init__(self, data: dict, sets_played: int, slug: str):
        self.passers: dict[str, list[str]] = {}
        self.aces_against: list[int] = list(data.get("aces_against", []))
        for name, per_set in data.items():
            if name == "aces_against":
                continue
            if len(per_set) != sets_played:
                raise SystemExit(
                    f"{slug}: serve_receive.{name} covers {len(per_set)} sets "
                    f"but the match went {sets_played}"
                )
            cleaned = [str(entry).strip() for entry in per_set]
            for entry in cleaned:
                bad = [c for c in entry if c not in "0123"]
                if bad:
                    raise SystemExit(
                        f"{slug}: serve_receive.{name} has {bad[0]!r} — "
                        "reception ratings are 0-3"
                    )
            self.passers[name] = cleaned

    def __bool__(self) -> bool:
        return bool(self.passers)

    def _digits(self, set_index: int) -> list[int]:
        return [
            int(c)
            for per_set in self.passers.values()
            for c in per_set[set_index]
        ]

    def receptions(self, set_index: int) -> int:
        return len(self._digits(set_index))

    def rating(self, set_index: int) -> float | None:
        digits = self._digits(set_index)
        return sum(digits) / len(digits) if digits else None

    def match_rating(self) -> float | None:
        digits = [
            int(c) for per_set in self.passers.values() for entry in per_set
            for c in entry
        ]
        return sum(digits) / len(digits) if digits else None

    def by_passer(self, set_index: int) -> dict[str, float]:
        out = {}
        for name, per_set in self.passers.items():
            entry = per_set[set_index]
            if entry:
                out[name] = sum(int(c) for c in entry) / len(entry)
        return out


# --- report card ---------------------------------------------------------------
# Rows evaluate to True (✅), False (❌), or None ("can't tell from the tallies").
# A None row is filled from [report_card] in the game file, so a second run of
# this command reproduces the same card rather than re-asking.


def _max_per_set(key: str, limit: int):
    return lambda game, i: game.stat(key, i) <= limit


def _min_per_set(key: str, limit: int):
    return lambda game, i: game.stat(key, i) >= limit


def _race_to_15(game: Game, i: int):
    """From the book when it's transcribed; otherwise only a set that ended
    under 15 settles itself."""
    if game.scorebook:
        winner = game.scorebook.race_winner(i)
        if winner is not None:
            return winner == "jc"
    jc, _ = game.sets[i]
    return False if jc < 15 else None


def _sr_rating(game: Game, i: int):
    if not game.serve_receive:
        return None
    rating = game.serve_receive.rating(i)
    return None if rating is None else rating >= SR_TARGET


def _own_run_of_5(game: Game, i: int):
    return game.scorebook.jc_longest(i) >= 5 if game.scorebook else None


def _no_opponent_run_of_5(game: Game, i: int):
    return game.scorebook.opp_longest(i) < 5 if game.scorebook else None


CRITERIA = [
    ("controllables", "No rotation errors or sub issues", "rotation", None),
    ("controllables", "Meet in the center", "meet_center", None),
    ("controllables", "No complaints", "no_complaints", None),
    ("controllables", "Good energy, effort, focus", "energy", None),
    ("free_points", "No net violations", "net", _max_per_set("net_violations", 0)),
    (
        "free_points",
        "No missed points for <br>communication errors",
        "communication",
        _max_per_set("communication_errors", 0),
    ),
    ("free_points", "Max 3 AE/Set", "attack_errors", _max_per_set("attack_errors", 3)),
    ("free_points", "Max 2 SE/Set", "service_errors", _max_per_set("service_errors", 2)),
    ("game_control", "2+ blocks", "blocks", _min_per_set("blocks", 2)),
    ("game_control", "5+ (big-boy) kills", "kills", _min_per_set("kills", 5)),
    ("game_control", "SR rating >= 2.0", "sr_rating", _sr_rating),
    (
        "game_control",
        "More aces than SE",
        "aces_over_se",
        lambda game, i: game.stat("aces", i) > game.stat("service_errors", i),
    ),
    ("game_control", "Win the race to 15", "race_to_15", _race_to_15),
    ("game_control", "Go on a 5+ point run", "run_5", _own_run_of_5),
    ("game_control", "No opponent 5-point run", "no_opp_run", _no_opponent_run_of_5),
    ("game_control", "One great defensive play or rally save", "defensive_play", None),
]

SECTION_HEADS = {
    "free_points": "**Avoiding Free Points**",
    "game_control": "**Game Control**",
}

MARK_TRUE, MARK_FALSE, MARK_UNKNOWN = "✅", "❌", "—"

RATING_BANDS = [
    (6.0, "Poor 👎"),
    (8.0, "OK 😐"),
    (10.5, "Good 👍"),
    (12.5, "Great 👏"),
    (14.0, "Dominant 💪"),
    (float("inf"), "Near Perfect 💯"),
]


def _parse_manual(value: str, sets_played: int) -> list[bool | None]:
    """`"✅✅❌"` / `"YYN"` / `"..."` -> per-set marks, padded with None."""
    marks: list[bool | None] = []
    for char in str(value).replace(" ", ""):
        if char in ("✅", "Y", "y", "1"):
            marks.append(True)
        elif char in ("❌", "N", "n", "0"):
            marks.append(False)
        else:
            marks.append(None)
    marks += [None] * (sets_played - len(marks))
    return marks[:sets_played]


def evaluate(game: Game) -> list[dict]:
    """One row per criterion: auto-evaluated, then overridden by the game file."""
    rows = []
    for section, label, key, rule in CRITERIA:
        marks = [rule(game, i) if rule else None for i in range(game.sets_played)]
        if key in game.manual_marks:
            manual = _parse_manual(game.manual_marks[key], game.sets_played)
            # The tallies win: a manual mark only fills a cell the stat sheet
            # could not answer. To change an auto row, fix the stat — it feeds
            # the site too.
            marks = [auto if auto is not None else m for auto, m in zip(marks, manual)]
        rows.append(
            {
                "section": section,
                "label": label,
                "key": key,
                "marks": marks,
                "auto": rule is not None,
                "note": game.notes.get(key, ""),
            }
        )
    return rows


def score(rows: list[dict], sets_played: int) -> dict:
    checks = sum(1 for row in rows for mark in row["marks"] if mark is True)
    unresolved = sum(1 for row in rows for mark in row["marks"] if mark is None)
    rating = checks / sets_played if sets_played else 0.0
    band = next(label for ceiling, label in RATING_BANDS if rating <= ceiling)
    return {
        "checks": checks,
        "unresolved": unresolved,
        "rating": rating,
        "band": band,
        "provisional": unresolved > 0,
    }


STAT_LABELS = {
    "aces": "Aces",
    "kills": "Kills (big boy)",
    "blocks": "Blocks (big boy)",
    "service_errors": "Service errors",
    "attack_errors": "Attack errors",
    "communication_errors": "Communication errors",
    "net_violations": "Net violations",
    "doubles_lifts": "Doubles / lifts",
}


def _match_totals_block(game: Game) -> list[str]:
    """Team numbers for the match, with the per-set rate beside each.

    Per set, not per match, is the comparable figure within one card — a
    five-setter racks up more of everything than a sweep.
    """
    totals = game.totals()
    sets = game.sets_played
    lines = [
        "### Match totals",
        "",
        f"| Team | Total | Per set ({sets}) |",
        "| --- | :-: | :-: |",
    ]
    for key, label in STAT_LABELS.items():
        if not game.stats.get(key):
            continue
        lines.append(f"| {label} | {totals[key]} | {totals[key] / sets:.1f} |")

    sr = game.serve_receive
    if sr and sr.match_rating() is not None:
        receptions = sum(sr.receptions(i) for i in range(sets))
        lines.append(
            f"| **Serve receive** | **{sr.match_rating():.2f}** | "
            f"{receptions} receptions |"
        )
        if sr.aces_against:
            conceded = sum(sr.aces_against)
            lines.append(
                f"| Aces against | {conceded} | {conceded / sets:.1f} |"
            )
    return lines


def _season_block(game: Game, season: list[Game]) -> list[str]:
    """Per-match averages across the season so far, this game included."""
    played = [g for g in season if g.date <= game.date]
    if len(played) < 2:
        return []

    matches = len(played)
    sets = sum(g.sets_played for g in played)
    lines = [
        "",
        f"### Season to date — {matches} matches, {sets} sets",
        "",
        "| Team | Per match | Per set |",
        "| --- | :-: | :-: |",
    ]
    for key, label in STAT_LABELS.items():
        total = sum(g.totals().get(key, 0) for g in played)
        lines.append(f"| {label} | {total / matches:.1f} | {total / sets:.1f} |")

    rated = [
        (g.serve_receive, i)
        for g in played
        if g.serve_receive
        for i in range(g.sets_played)
        if g.serve_receive.rating(i) is not None
    ]
    if rated:
        receptions = sum(sr.receptions(i) for sr, i in rated)
        weighted = sum(sr.rating(i) * sr.receptions(i) for sr, i in rated)
        lines.append(
            f"| **Serve receive** | **{weighted / receptions:.2f}** | "
            f"{receptions} receptions |"
        )
    return lines


def render_report_card(game: Game, season: list[Game] | None = None) -> str:
    rows = evaluate(game)
    result = score(rows, game.sets_played)
    date_label = game.date.strftime("%-m/%-d")
    side = "vs" if game.home_away == "home" else "@"

    if result["provisional"]:
        headline = (
            f"{result['checks']} ✅ so far — rating pending "
            f"({result['unresolved']} cells still to mark)"
        )
    else:
        headline = f"{result['rating']:.1f} - {result['band']}"

    lines = [
        "---",
        f"created: {game.date.isoformat()}",
        "aliases: []",
        audience.frontmatter_line(REPORT_CARD_AUDIENCE),
        "cssclasses:",
        f"  - {REPORT_CARD_CSS_CLASS}",
        "tags:",
        "  - jcvb-report-card",
        "---",
        "",
        "## JC Varsity Volleyball Keys to the Game",
        "",
        f"**{date_label} {side} {game.opponent}**: {headline}",
        f"*{game.card_writeup or '(write-up to come)'}*",
        "",
        f"**Sets:** {game.set_scores} ({game.score_line})",
        "",
    ]

    lines.append("| Controllables |  |  |")
    lines.append("| --- | :-: | --- |")

    current = "controllables"
    for row in rows:
        if row["section"] != current:
            lines.append("|  |  |  |")
            lines.append(f"| {SECTION_HEADS[row['section']]} |  |  |")
            current = row["section"]
        marks = " ".join(
            MARK_TRUE if m is True else MARK_FALSE if m is False else MARK_UNKNOWN
            for m in row["marks"]
        )
        lines.append(f"| {row['label']} | {marks} | {row['note']} |")

    lines += [
        "",
        "",
        "---",
        "",
        "**Key** (Result = count-of-✅ / sets-played)",
        "",
        "|  <6.0   | \\(6.0, 8.0\\] | \\(8.0, 10.5\\] | \\(10.5, 12.5\\] | "
        "\\(12.5, 14.0\\] |     \\>14.0      |",
        "| :-----: | :----------: | :-----------: | :------------: | "
        ":------------: | :-------------: |",
        "| Poor 👎 |    OK 😐     |    Good 👍    |    Great 👏    |  "
        "Dominant 💪   | Near Perfect 💯 |",
    ]

    if result["provisional"]:
        missing = sorted(
            {row["key"] for row in rows if any(m is None for m in row["marks"])}
        )
        lines += [
            "",
            "",
            f"> [!todo] {result['unresolved']} cells are still blank (—) above.",
            "> They are the ones no stat sheet can answer, so they need your call:"
            f" **{', '.join(missing)}**.",
            "> Replace each — with ✅ or ❌, one per set, right here in this table."
            " Then tell Claude the card is filled in and the rating gets added up"
            " (or run"
            f" `uv run python -m jcvb.postgame absorb-card {game.slug} <this file>`).",
            "> Everything else is computed from the tallies and the book — change"
            " those numbers, not these marks.",
        ]

    tallies = f"Shaw-Tallies-vs-{game.opponent.replace(' ', '-')}"
    lines += ["", "", "---", ""]
    lines += _match_totals_block(game)
    if season:
        lines += _season_block(game, season)

    lines += ["", "", f"![[{tallies}.jpg]]", ""]
    return "\n".join(lines)


def render_stats_note(game: Game) -> str:
    """The vault's copy of the match — generated, so it cannot drift from the
    game file the site and the report card read."""
    side = "vs." if game.home_away == "home" else "@"
    label = game.designation.title()
    opponent_file = game.opponent.replace(" ", "-")
    lines = [
        "---",
        f"created: {game.date.isoformat()}",
        "aliases: []",
        audience.frontmatter_line(STATS_NOTE_AUDIENCE),
        "cssclasses:",
        f"  - {STATS_NOTE_CSS_CLASS}",
        "tags:",
        "  - jcvb-game-stats",
        "---",
        "",
        f"# {game.date.strftime('%-m/%-d/%y')} — JC {side} {game.opponent} ({label})",
        "",
        f"**Result:** {game.result} {game.jc_set_score} · "
        f"{'Home' if game.home_away == 'home' else 'Away'}",
        "",
        "> [!info] Generated from "
        f"`site/content/games/{game.slug}.toml` — edit there and re-run",
        f"> `uv run python -m jcvb.postgame stats-note {game.slug}`.",
        "",
        "## Set scores",
        "",
        "| Set | JC  | Opp | Result |",
        "| :-: | :-: | :-: | :----: |",
    ]
    for i, (jc, opp) in enumerate(game.sets, start=1):
        lines.append(f"|  {i}  | {jc:>3} | {opp:>3} |   {game.set_results[i - 1]}    |")

    header = "| Stat | " + " | ".join(f"S{i}" for i in range(1, game.sets_played + 1))
    lines += [
        "",
        "## Stat lines",
        "",
        header + " | Total |",
        "| --- |" + " :-: |" * game.sets_played + " :---: |",
    ]
    totals = game.totals()
    for key in STAT_KEYS:
        values = game.stats[key]
        if not values:
            continue
        cells = " | ".join(str(v) for v in values)
        lines.append(f"| {key.replace('_', ' ').title()} | {cells} | {totals[key]} |")

    sr = game.serve_receive
    if sr:
        lines += [
            "",
            "## Serve receive",
            "",
            "Every reception rated 0-3; the team rating is the mean.",
            "",
            "| | " + " | ".join(f"S{i + 1}" for i in range(game.sets_played))
            + " | Match |",
            "| --- |" + " :-: |" * game.sets_played + " :---: |",
            "| Team rating | "
            + " | ".join(
                f"{sr.rating(i):.2f}" if sr.rating(i) is not None else "—"
                for i in range(game.sets_played)
            )
            + f" | **{sr.match_rating():.2f}** |",
            "| Receptions | "
            + " | ".join(str(sr.receptions(i)) for i in range(game.sets_played))
            + f" | {sum(sr.receptions(i) for i in range(game.sets_played))} |",
        ]
        if sr.aces_against:
            lines.append(
                "| Aces against | "
                + " | ".join(str(v) for v in sr.aces_against)
                + f" | {sum(sr.aces_against)} |"
            )
        lines += [
            "",
            f"Target is {SR_TARGET:.1f}. Source: `IMG_7116.heic` (libero tracking).",
        ]

    if game.notes.get("transcription"):
        lines += ["", "### Transcription notes", "", game.notes["transcription"]]
    if game.recap_body:
        lines += ["", "## Coach's notes", "", game.recap_body]
    lines += [
        "",
        f"Scans: `Shaw-Tallies-vs-{opponent_file}.png`, "
        f"`{game.date.isoformat()}--vs-{opponent_file}-Scorebook.pdf`",
        "",
    ]
    return "\n".join(lines)


# --- reading a card back -------------------------------------------------------
# TK fills the judgment cells in the rendered card, because that is the document
# in front of him. This reads those edits back into the game file so the card
# stays generated and nothing has to be typed twice.


def _marks_to_string(cell: str) -> str:
    out = ""
    for char in cell:
        if char == MARK_TRUE:
            out += "✅"
        elif char == MARK_FALSE:
            out += "❌"
        elif char == MARK_UNKNOWN:
            out += "."
    return out


def absorb_card(game: Game, card_text: str) -> dict:
    """Pull marks and notes out of a filled-in report card.

    Auto rows are read but never absorbed — the tallies decide those — and a
    disagreement is reported rather than applied. A row missing from the card
    (deleted while editing) leaves the game file untouched.
    """
    by_label = {row["label"]: row for row in evaluate(game)}
    updates: dict[str, str] = {}
    notes: dict[str, str] = {}
    conflicts: list[str] = []
    seen: set[str] = set()

    for line in card_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        row = by_label.get(cells[0])
        if row is None:
            continue
        seen.add(row["key"])
        marks = _marks_to_string(cells[1])
        note = cells[2].strip() if len(cells) > 2 else ""
        if note:
            notes[row["key"]] = note
        if row["auto"]:
            rendered = _marks_to_string(
                "".join(
                    MARK_TRUE if m is True else MARK_FALSE if m is False
                    else MARK_UNKNOWN
                    for m in row["marks"]
                )
            )
            if marks and marks != rendered:
                conflicts.append(
                    f"{row['label']}: card says {marks}, the tallies say "
                    f"{rendered} — fix the stat, not the card"
                )
            continue
        if marks:
            updates[row["key"]] = marks

    missing = [
        row["key"]
        for row in by_label.values()
        if not row["auto"] and row["key"] not in seen
    ]
    return {
        "marks": updates,
        "notes": notes,
        "card": _card_writeup_from(card_text),
        "conflicts": conflicts,
        "missing_rows": missing,
    }


WRITEUP_RE = re.compile(r"^\*(?!\*)(?P<text>.+?)\*\s*$", re.MULTILINE)


def _card_writeup_from(card_text: str) -> dict:
    """The italic line under the header is TK's internal write-up."""
    match = WRITEUP_RE.search(card_text)
    if not match:
        return {}
    text = match.group("text").strip()
    if not text or text.startswith("("):
        return {}
    return {"writeup": text}


SECTION_RE = re.compile(r"^\[([a-z_]+)\]\s*$", re.MULTILINE)


def _split_sections(text: str) -> list[tuple[str | None, str]]:
    """[(section name or None for the preamble, body text), …] preserving order."""
    parts: list[tuple[str | None, str]] = []
    last_name: str | None = None
    last_end = 0
    for match in SECTION_RE.finditer(text):
        parts.append((last_name, text[last_end:match.start()]))
        last_name = match.group(1)
        last_end = match.start()
    parts.append((last_name, text[last_end:]))
    return parts


def _set_key(body: str, key: str, value: str) -> str:
    """Set `key = "value"` inside one section body, keeping any trailing comment.

    Keys repeat across sections — `sr_rating` is both a mark and a note — so this
    only ever edits within the section it was handed.
    """
    escaped = value.replace('"', "'")
    pattern = re.compile(
        rf'^(?P<lead>{re.escape(key)}\s*=\s*)'
        rf'(?:"""(?:.|\n)*?"""|"[^"\n]*")'
        rf'(?P<trail>[^\n]*)$',
        re.MULTILINE,
    )
    if pattern.search(body):
        return pattern.sub(lambda m: f'{m.group("lead")}"{escaped}"{m.group("trail")}',
                           body, count=1)
    return body.rstrip("\n") + f'\n{key} = "{escaped}"\n'


def apply_to_game_file(
    slug: str,
    absorbed: dict,
    games_dir: Path = GAMES_DIR,
    vault_root: Path = VAULT_GAMES_ROOT,
) -> Path:
    """Write absorbed marks and notes back into the game file, in place."""
    path = resolve_game_path(slug, games_dir, vault_root)
    sections = _split_sections(path.read_text(encoding="utf-8"))
    wanted = {
        "report_card": absorbed["marks"],
        "notes": absorbed["notes"],
        "card": absorbed.get("card", {}),
    }
    seen = {name for name, _ in sections}

    updated = []
    for name, body in sections:
        for key, value in wanted.get(name, {}).items():
            body = _set_key(body, key, value)
        updated.append(body)

    text = "".join(updated)
    for section, values in wanted.items():
        if values and section not in seen:
            lines = "\n".join(f'{k} = "{v}"' for k, v in values.items())
            text = text.rstrip("\n") + f"\n\n[{section}]\n{lines}\n"
    path.write_text(text, encoding="utf-8")
    return path


# --- google form ---------------------------------------------------------------


def form_prefill_url(game: Game, season_games: list[Game] | None = None) -> str:
    season = season_games if season_games is not None else load_season()
    rec = records(season, through=game.date)
    next_game = _next_game(season, game)

    params: list[tuple[str, str]] = [("usp", "pp_url")]
    field_id = FORM_FIELDS["date"]
    params += [
        (f"{field_id}_year", str(game.date.year)),
        (f"{field_id}_month", str(game.date.month)),
        (f"{field_id}_day", str(game.date.day)),
    ]
    params += [
        (FORM_FIELDS["gender"], "Boys"),
        (FORM_FIELDS["level"], "Varsity"),
        (FORM_FIELDS["sport"], "Volleyball"),
        (FORM_FIELDS["opponent"], game.opponent),
        (FORM_FIELDS["score"], game.form_score),
        (FORM_FIELDS["recap"], form_recap_text(game)),
        (FORM_FIELDS["overall_record"], rec["overall"]),
        (FORM_FIELDS["conference_record"], rec["conference"]),
        (FORM_FIELDS["next_game"], next_game),
        (FORM_FIELDS["other"], f"Full recap and stats: {game.recap_url}"),
    ]
    return f"{FORM_URL}?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def form_recap_text(game: Game) -> str:
    """Recap prose with the per-set scores appended — the form asks for one
    box, and the school's write-ups always want the set breakdown."""
    label = "Scrimmage" if game.designation == "scrimmage" else "Match"
    parts = [game.recap_body] if game.recap_body else []
    parts.append(f"{label} scores: {game.set_scores}.")
    parts.append(f"Full recap and stats: {game.recap_url}")
    return " ".join(parts)


SCHEDULE_DIR = REPO_ROOT / "site" / "content" / "schedule"


def _next_game(season: list[Game], game: Game, schedule_dir: Path = SCHEDULE_DIR) -> str:
    """The next match on the schedule — the form wants date, opponent, time.

    Read from the season schedule, not from played games: the next one has by
    definition not been played yet, so it has no game file.
    """
    path = schedule_dir / f"{game.date.year}.toml"
    if path.exists():
        scheduled = tomllib.loads(path.read_text(encoding="utf-8")).get("games", [])
        later = sorted(
            (g for g in scheduled if g["date"] > game.date.isoformat()),
            key=lambda g: g["date"],
        )
        if later:
            nxt = later[0]
            when = datetime.strptime(nxt["date"], "%Y-%m-%d").date().strftime("%-m/%-d")
            side = "vs" if nxt.get("home_away") == "home" else "@"
            time = nxt.get("varsity") or nxt.get("jv") or "TBD"
            return f"{when} {side} {nxt['opponent']} {time}".strip()

    later_played = [g for g in season if g.date > game.date]
    if not later_played:
        return ""
    nxt_played = later_played[0]
    side = "vs" if nxt_played.home_away == "home" else "@"
    return f"{nxt_played.date.strftime('%-m/%-d')} {side} {nxt_played.opponent}"


# --- cli -----------------------------------------------------------------------


def _summary(game: Game) -> str:
    rows = evaluate(game)
    result = score(rows, game.sets_played)
    totals = game.totals()
    lines = [
        f"{game.date}  {'vs' if game.home_away == 'home' else '@'} {game.opponent}"
        f"  ({game.designation})",
        f"  Result       {game.score_line}   {game.set_scores}",
        f"  Report card  {result['rating']:.1f} - {result['band']}"
        + ("  (provisional)" if result["provisional"] else ""),
        "  Totals       "
        + ", ".join(f"{key.replace('_', ' ')} {totals[key]}" for key in STAT_KEYS),
    ]
    if result["provisional"]:
        missing = sorted(
            {row["key"] for row in rows if any(m is None for m in row["marks"])}
        )
        lines.append(f"  Needs you    {', '.join(missing)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="jcvb.postgame", description="Post-game processing from one game file."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("summary", "result, totals, and the report-card rating"),
        ("form-url", "prefilled score-reporting form URL"),
        ("check", "validate the game file without writing anything"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("slug")
    for name, help_text in (
        ("report-card", "render the Keys to the Game card"),
        ("stats-note", "render the vault's stats note"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("slug")
        p.add_argument("--out", type=Path, help="write here instead of stdout")
    p = sub.add_parser(
        "absorb-card", help="read a filled-in card back into the game file"
    )
    p.add_argument("slug")
    p.add_argument("card", type=Path, help="the report card TK filled in")
    sub.add_parser("sync", help="copy vault game files into the repo")

    args = parser.parse_args(argv)

    if args.command == "sync":
        copied = sync_from_vault()
        print(f"synced {len(copied)} game file(s) from {VAULT_GAMES_ROOT}")
        for slug in copied:
            print(f"  {slug}")
        return 0

    game = load_game(args.slug)

    if args.command == "summary":
        print(_summary(game))
    elif args.command == "form-url":
        print(form_prefill_url(game))
    elif args.command == "check":
        print(f"{args.slug}: OK — {game.sets_played} sets, {game.score_line}")
    elif args.command == "absorb-card":
        absorbed = absorb_card(game, args.card.read_text(encoding="utf-8"))
        path = apply_to_game_file(args.slug, absorbed)
        print(f"absorbed {len(absorbed['marks'])} row(s) into {path}")
        for line in absorbed["conflicts"]:
            print(f"  ! {line}")
        if absorbed["missing_rows"]:
            print(
                "  ? not in the card, left as they were: "
                + ", ".join(absorbed["missing_rows"])
            )
    elif args.command in ("report-card", "stats-note"):
        if args.command == "report-card":
            text = render_report_card(game, season=load_season())
        else:
            text = render_stats_note(game)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
