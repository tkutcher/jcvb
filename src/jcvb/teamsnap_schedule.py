"""Build TeamSnap import CSVs with JV and Varsity as separate events.

`teamsnap_calendar` exports the published iCloud feed, where a matchup is one
combined entry ("JC vs. Landon") covering both levels. TeamSnap wants one event
per team, so this builds from the two sources that already carry the levels
apart:

  * games   — `site/content/schedule/<season>.toml`, the curated schedule that
              drives the public site (opponent, home/away, JV + Varsity times).
              Curated, so a correction TK makes for the site flows through here
              instead of being re-fixed per export.
  * practices — the school's master schedule CSV, which lists a JV row and a
              Varsity row per day with their own times and gyms. The season TOML
              does not carry practices at all.

Output is one file per level per template, since a TeamSnap import targets a
single team:

    teamsnap-varsity-games.csv      teamsnap-varsity-practices.csv
    teamsnap-jv-games.csv           teamsnap-jv-practices.csv

Usage:
    uv run python -m jcvb.teamsnap_schedule
    uv run python -m jcvb.teamsnap_schedule --master ~/Desktop/master.csv
    uv run python -m jcvb.teamsnap_schedule --out-dir ~/Desktop --json

Importer traps worth remembering (see also CLAUDE.md):
  * The three templates are NOT interchangeable — a practice in the Games
    template is rejected.
  * A Venue with no Sub-Venue is a hard error, so an unmapped location goes to
    Notes instead (same rule as `teamsnap_calendar`).
  * In the wizard's team-mapping step, set the John Carroll value to the real
    team. Left on *Skip* it drops every row and blames the data.
"""

import argparse
import csv
import datetime
import json
import pathlib
import re
import sys
import tomllib

from jcvb._consts import REPO_ROOT
from jcvb.teamsnap_calendar import (
    GAME_ARRIVAL_MIN,
    GAME_HEADER,
    PRACTICE_HEADER,
    VENUE_MAP_PATH,
    load_venue_map,
)

SCHEDULE_DIR = REPO_ROOT / "site" / "content" / "schedule"
DEFAULT_MASTER = (
    pathlib.Path.home()
    / "TK/tk-vault/orgs/JCVB/coach/admin/from-jc/2026_2027 Master Schedule(Fall 2026).csv"
)
DEFAULT_OUT_DIR = REPO_ROOT / "outputs"
DEFAULT_SEASON = 2026

TEAM = "John Carroll Boys Volleyball"
LEVELS = ("Varsity", "JV")

# The master gives a game a start but no end. Both levels are scheduled 90
# minutes apart all season (JV 4:00 / Varsity 5:30), which is the match window
# the program actually uses, and TeamSnap needs a duration for the start time
# to stick.
GAME_DURATION = "01:30"

# Home is always The John Carroll School, so its sub-venue is the gym (Upper /
# Lower). Away sites are one gym as far as this schedule is concerned, and
# TeamSnap rejects a Venue with no Sub-Venue, so they default to "Main Gym"
# unless teamsnap-venues.json names the court.
AWAY_SUB_VENUE = "Main Gym"

# Gym codes used in the master's Location column.
GYM_NAMES = {"UG": "Upper Gym", "LG": "Lower Gym"}
NO_LOCATION = {"", "n/a", "tbd", "na"}

_TIME_RANGE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})\s*(?P<meridiem>AM|PM)$",
    re.IGNORECASE,
)
_TIME_ONE = re.compile(r"^(?P<start>\d{1,2}:\d{2})\s*(?P<meridiem>AM|PM)$", re.IGNORECASE)
_PRACTICE_TYPES = {"practice", "tryouts"}
_GAME_TYPES = {"game", "scrimmage", "playoffs"}


# --- shared helpers ------------------------------------------------------------


def _fmt_date(value: datetime.date) -> str:
    return value.strftime("%m/%d/%Y")


def _fmt_time(value: datetime.time | None) -> str:
    return "" if value is None else value.strftime("%I:%M %p")


def _parse_clock(text: str) -> datetime.time | None:
    """"5:00 PM" -> time(17, 0). TBD/blank/CANCELED -> None."""
    match = _TIME_ONE.match(text.strip())
    if not match:
        return None
    hour, minute = (int(p) for p in match.group("start").split(":"))
    if match.group("meridiem").upper() == "PM" and hour != 12:
        hour += 12
    elif match.group("meridiem").upper() == "AM" and hour == 12:
        hour = 0
    return datetime.time(hour, minute)


def _parse_span(text: str) -> tuple[datetime.time | None, str]:
    """"3:30-5:30 PM" -> (time(15, 30), "02:00"). Single times get no duration.

    The master writes one meridiem for the pair, so both halves take it — and a
    range that crosses noon ("11:00-1:00 PM") would be wrong, which does not
    occur in a 3:30/4:30 PM practice schedule.
    """
    text = text.strip()
    match = _TIME_RANGE.match(text)
    if not match:
        return _parse_clock(text), ""
    meridiem = match.group("meridiem")
    start = _parse_clock(f"{match.group('start')} {meridiem}")
    end = _parse_clock(f"{match.group('end')} {meridiem}")
    if start is None or end is None:
        return start, ""
    minutes = (
        datetime.datetime.combine(datetime.date.min, end)
        - datetime.datetime.combine(datetime.date.min, start)
    ).seconds // 60
    return start, f"{minutes // 60:02d}:{minutes % 60:02d}"


def load_opponent_map(path: pathlib.Path = VENUE_MAP_PATH) -> dict:
    """Opponent name -> venue for away games, from the same JSON file."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("opponents", {})


def _resolve(mapped: dict | None, label: str, sub_venue_default: str = "") -> tuple[str, str, str]:
    """(venue, sub_venue, note) for one mapping.

    A Venue with no Sub-Venue is a hard import error, so a half-filled mapping
    stays out of those columns and the site is named in Notes instead.
    """
    if not mapped or not mapped.get("venue"):
        return "", "", label
    sub_venue = mapped.get("sub_venue") or sub_venue_default
    if not sub_venue:
        return "", "", mapped["venue"]
    return mapped["venue"], sub_venue, ""


def _venue_fields(location: str, venue_map: dict) -> tuple[str, str, str]:
    """Venue for a home location — a gym code (UG/LG) or its long name."""
    label = GYM_NAMES.get(location, location)
    if not label or label.strip().casefold() in NO_LOCATION:
        return "", "", ""
    return _resolve(venue_map.get(label) or venue_map.get(location), label)


def _game_venue_fields(
    event: dict,
    venue_map: dict,
    opponent_map: dict,
    away_sub_venue: str = "",
) -> tuple[str, str, str]:
    """Home games resolve their own gym; away games resolve the opponent's site.

    A playoff round has no site until the bracket is set, so it gets neither.
    """
    if event["designation"] == "playoffs":
        return "", "", ""
    if event["home_away"] == "away":
        return _resolve(
            opponent_map.get(event["opponent"]),
            f"at {event['opponent']}",
            away_sub_venue,
        )
    return _venue_fields(event["venue"], venue_map)


def _join_notes(*parts: str) -> str:
    return " — ".join(p.strip() for p in parts if p and p.strip())


# --- games, from the curated season schedule ----------------------------------


def load_schedule(season: int = DEFAULT_SEASON) -> tuple[dict, list[dict]]:
    data = tomllib.loads((SCHEDULE_DIR / f"{season}.toml").read_text(encoding="utf-8"))
    return data.get("meta", {}), data.get("games", [])


def game_events(games: list[dict]) -> list[dict]:
    """Flatten each matchup into one event per level that actually plays."""
    events = []
    for game in games:
        for level in LEVELS:
            raw = (game.get(level.lower()) or "").strip()
            if not raw:  # varsity-only or JV-only night
                continue
            events.append(
                {
                    "level": level,
                    "date": datetime.date.fromisoformat(game["date"]),
                    "time": _parse_clock(raw),
                    "time_tbd": _parse_clock(raw) is None,
                    "opponent": game["opponent"],
                    "home_away": game.get("home_away", ""),
                    "designation": game.get("designation", ""),
                    "venue": game.get("venue", ""),
                    "note": game.get("note", ""),
                }
            )
    events.sort(key=lambda e: (e["date"], str(e["time"])))
    return events


def _game_row(
    event: dict,
    venue_map: dict,
    travel: dict,
    opponent_map: dict | None = None,
    away_sub_venue: str = "",
) -> list[str]:
    side = {"home": "Home", "away": "Away"}.get(event["home_away"], "")
    opposite = {"Home": "Away", "Away": "Home"}.get(side, "")
    venue, sub_venue, venue_note = _game_venue_fields(
        event, venue_map, opponent_map or {}, away_sub_venue
    )
    # A playoff round is not an opponent — TeamSnap reads blank as TBD.
    playoff = event["designation"] == "playoffs"
    opponent = "TBD" if playoff else event["opponent"]
    round_note = event["opponent"] if playoff else ""
    scrimmage = event["designation"] == "scrimmage"
    notes = _join_notes(
        round_note,
        "Scrimmage" if scrimmage else "",
        event["note"],
        venue_note,
        travel.get((event["date"], event["level"]), ""),
    )
    start = "" if event["time_tbd"] else _fmt_time(event["time"])
    return [
        TEAM, event["level"], "Internal", side,
        opponent, "", "External", opposite,
        _fmt_date(event["date"]), start,
        "" if not start else GAME_DURATION,
        "" if not start else str(GAME_ARRIVAL_MIN),
        venue, sub_venue, notes,
        # A scrimmage does not count; playoff results do.
        "Yes" if scrimmage else "No",
    ]


# --- practices, from the school master ----------------------------------------


def read_master(path: pathlib.Path) -> list[dict]:
    """Boys Volleyball rows from the school master, one dict per row."""
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.reader(handle):
            if len(raw) < 8 or "boys volleyball" not in raw[2].casefold():
                continue
            try:
                month, day, year = (int(p) for p in raw[0].split("/"))
            except ValueError:  # a week banner or header row
                continue
            rows.append(
                {
                    "date": datetime.date(year, month, day),
                    "type": raw[1].strip(),
                    "level": raw[3].strip(),
                    "description": raw[4].strip(),
                    "time": raw[5].strip(),
                    "location": raw[6].strip(),
                    "note": raw[7].strip(),
                    "dismissal": raw[11].strip() if len(raw) > 11 else "",
                    "departure": raw[12].strip() if len(raw) > 12 else "",
                    "transport": raw[13].strip() if len(raw) > 13 else "",
                }
            )
    rows.sort(key=lambda r: (r["date"], r["time"]))
    return rows


def travel_notes(master: list[dict]) -> dict:
    """(date, level) -> "depart 2:00 PM; transport JDT", for away games."""
    notes = {}
    for row in master:
        if row["type"].casefold() not in _GAME_TYPES:
            continue
        parts = []
        if row["dismissal"] and row["dismissal"] != "TBD":
            parts.append(f"dismissal {row['dismissal']}")
        if row["departure"] and row["departure"] != "TBD":
            parts.append(f"depart {row['departure']}")
        if row["transport"]:
            parts.append(f"transport {row['transport']}")
        if parts:
            notes[(row["date"], row["level"])] = "; ".join(parts)
    return notes


def _practice_row(row: dict, level: str, venue_map: dict) -> list[str]:
    start, duration = _parse_span(row["time"])
    venue, sub_venue, venue_note = _venue_fields(row["location"], venue_map)
    tryout = row["type"].casefold() == "tryouts"
    name = "Tryouts" if tryout else f"{level} Practice"
    notes = _join_notes(
        row["note"],
        venue_note,
        "All levels" if tryout and row["level"].casefold() == "all" else "",
    )
    return [
        name, TEAM, level, _fmt_date(row["date"]),
        _fmt_time(start), duration, "", venue, sub_venue, notes,
    ]


# --- assembly -----------------------------------------------------------------


def build(
    games: list[dict],
    master: list[dict],
    venue_map: dict | None = None,
    opponent_map: dict | None = None,
    away_sub_venue: str = "",
) -> dict:
    venue_map = venue_map or {}
    opponent_map = opponent_map or {}
    travel = travel_notes(master)
    out = {level: {"games": [], "practices": []} for level in LEVELS}
    warnings: list[str] = []
    skipped: list[str] = []
    unmapped: dict[str, str] = {}

    for event in game_events(games):
        out[event["level"]]["games"].append(
            _game_row(event, venue_map, travel, opponent_map, away_sub_venue)
        )
        venue, _, _ = _game_venue_fields(
            event, venue_map, opponent_map, away_sub_venue
        )
        if not venue and event["designation"] != "playoffs":
            key = event["opponent"] if event["home_away"] == "away" else event["venue"]
            section = "opponents" if event["home_away"] == "away" else "venues"
            unmapped[key] = section
        if event["time_tbd"]:
            warnings.append(
                f"{_fmt_date(event['date'])} {event['level']} {event['opponent']}: "
                "time still TBD — imported as a date-only event, update it once the "
                "bracket is set"
            )

    for row in master:
        kind = row["type"].casefold()
        if kind not in _PRACTICE_TYPES:
            if kind not in _GAME_TYPES:
                skipped.append(f"{_fmt_date(row['date'])} {row['description']} ({row['type']})")
            continue  # games come from the curated schedule, not the master
        start, _ = _parse_span(row["time"])
        if start is None:
            skipped.append(
                f"{_fmt_date(row['date'])} {row['description']} "
                f"({row['time'] or 'no time'})"
            )
            continue
        level = row["level"].strip()
        # Tryouts predate the JV/Varsity split, so both teams get them.
        targets = LEVELS if level.casefold() in ("all", "") else (level,)
        venue, _, _ = _venue_fields(row["location"], venue_map)
        label = GYM_NAMES.get(row["location"], row["location"])
        if not venue and label and label.strip().casefold() not in NO_LOCATION:
            unmapped[label] = "venues"
        for target in targets:
            if target not in out:
                warnings.append(
                    f"{_fmt_date(row['date'])} unknown level {level!r} — row skipped"
                )
                continue
            out[target]["practices"].append(_practice_row(row, target, venue_map))

    for name, section in sorted(unmapped.items()):
        warnings.append(
            f'No venue for "{name}" — Venue/Sub-Venue left blank and the site '
            f'moved to Notes. Add it under "{section}" in '
            f"{VENUE_MAP_PATH.name} (both venue AND sub_venue) and re-run."
        )

    tryouts = sum(
        1 for r in master
        if r["type"].casefold() == "tryouts" and r["level"].casefold() in ("all", "")
    )
    if tryouts:
        warnings.append(
            f"{tryouts} all-level tryout rows written to BOTH practice files — "
            "drop them from whichever team you import second"
        )
    return {"levels": out, "warnings": warnings, "skipped": skipped}


def write_csvs(built: dict, out_dir: pathlib.Path) -> list[pathlib.Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for level, sheets in built["levels"].items():
        for kind, header in (("games", GAME_HEADER), ("practices", PRACTICE_HEADER)):
            path = out_dir / f"teamsnap-{level.lower()}-{kind}.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(sheets[kind])
            written.append(path)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="jcvb.teamsnap_schedule",
        description="TeamSnap import CSVs with JV and Varsity split apart.",
    )
    parser.add_argument("--season", type=int, default=DEFAULT_SEASON)
    parser.add_argument(
        "--master", type=pathlib.Path, default=DEFAULT_MASTER,
        help="school master schedule CSV (practices come from here)",
    )
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--away-sub-venue", default=AWAY_SUB_VENUE,
        help=(
            "sub-venue for away sites whose mapping has none "
            f"(default {AWAY_SUB_VENUE!r}); pass an empty string to leave those "
            "rows' Venue/Sub-Venue blank instead."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not args.master.exists():
        raise SystemExit(f"Master schedule not found: {args.master}")

    _, games = load_schedule(args.season)
    master = read_master(args.master)
    built = build(
        games,
        master,
        venue_map=load_venue_map(),
        opponent_map=load_opponent_map(),
        away_sub_venue=args.away_sub_venue,
    )
    written = write_csvs(built, args.out_dir)

    counts = {
        level: {kind: len(rows) for kind, rows in sheets.items()}
        for level, sheets in built["levels"].items()
    }
    if args.json:
        print(json.dumps({
            "season": args.season,
            "master": str(args.master),
            "counts": counts,
            "files": [str(p) for p in written],
            "warnings": built["warnings"],
            "skipped": built["skipped"],
        }, indent=2))
        return 0

    print(f"{args.season} season — games from the site schedule, practices from")
    print(f"{args.master}")
    for path in written:
        with path.open(encoding="utf-8") as handle:
            rows = sum(1 for _ in handle) - 1
        print(f"  {rows:>4}  {path}")
    if built["skipped"]:
        print(f"\nSkipped {len(built['skipped'])} (no usable time):")
        for line in built["skipped"]:
            print(f"  - {line}")
    if built["warnings"]:
        print(f"\nWarnings ({len(built['warnings'])}):")
        for line in built["warnings"]:
            print(f"  ! {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
