"""Export the published JCVB iCloud calendar into TeamSnap import CSVs.

TeamSnap's bulk importer takes three *separate* templates — Games,
Practices, and Other Events — each with its own required columns. This
reads the published calendar feed, classifies every event, and writes one
CSV per template so each can be uploaded to the matching importer.

Usage:
    uv run python -m jcvb.teamsnap_calendar
    uv run python -m jcvb.teamsnap_calendar --from 2026-08-01 --to 2026-11-30
    uv run python -m jcvb.teamsnap_calendar --out-dir ~/Desktop --all
    uv run python -m jcvb.teamsnap_calendar --json

The feed URL is a published-calendar token (anyone holding it can read the
calendar), so it lives in the gitignored .env as JCVB_CALENDAR_URL rather
than in source. `--url` overrides it for one run.

Venues: the importer cannot create venues or sub-venues, and it rejects a
row that has a Venue with no Sub-Venue. Calendar locations are raw postal
addresses, which match nothing in TeamSnap. So a location is only emitted
as Venue + Sub-Venue when `teamsnap-venues.json` maps it; otherwise both
are left blank and the address is appended to Notes, which always imports.
Map a venue once it exists in TeamSnap and re-run.
"""

import argparse
import csv
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.request

import recurring_ical_events
from dotenv import dotenv_values
from icalendar import Calendar

from jcvb._consts import REPO_ROOT

VENUE_MAP_PATH = REPO_ROOT / "teamsnap-venues.json"
DEFAULT_OUT_DIR = REPO_ROOT / ".outputs" / "teamsnap"

DEFAULT_TEAM = "John Carroll Boys Volleyball"
DEFAULT_DIVISION = "Varsity"

# Minutes before start that players report. TeamSnap accepts whole 5-minute
# increments from 5 to 120; blank means "don't set an arrival time".
GAME_ARRIVAL_MIN = 60
PRACTICE_ARRIVAL_MIN = None
OTHER_ARRIVAL_MIN = None

# The address of a home game, used to sanity-check "vs." events that are
# actually scheduled somewhere else (neutral sites, tournaments).
HOME_VENUE_MARKER = "john carroll"

# Classification, applied in order to the summary with emoji stripped.
# "JC vs. Landon" / "JC @ Gilman" carry the opponent and the home/away side.
_GAME_VS = re.compile(r"^JC\s+vs\.?\s+(?P<opponent>.+)$", re.IGNORECASE)
_GAME_AT = re.compile(r"^JC\s+@\s*(?P<opponent>.+)$", re.IGNORECASE)
# Postseason events name a round rather than an opponent — still games, but
# against a team that isn't known yet.
_GAME_TBD = re.compile(r"champion|semi-?final|quarter-?final|playoff", re.IGNORECASE)
_PRACTICE = re.compile(r"practice|tryout|workout|lift|training|weightroom", re.IGNORECASE)

_EMOJI = re.compile(
    "[\U0001f000-\U0001faff☀-➿️‍\U0001f900-\U0001f9ff]+"
)


# --- fetching ------------------------------------------------------------------


def resolve_url(url: str | None = None) -> str:
    """Feed URL from --url, the environment, or .env, normalized to https."""
    if not url:
        url = os.environ.get("JCVB_CALENDAR_URL") or dotenv_values(
            REPO_ROOT / ".env"
        ).get("JCVB_CALENDAR_URL")
    if not url:
        raise SystemExit(
            "No calendar URL. Set JCVB_CALENDAR_URL in .env (see .env.example) "
            "or pass --url."
        )
    return re.sub(r"^webcal://", "https://", url.strip())


def fetch_ics(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
        return response.read()


# --- parsing -------------------------------------------------------------------
# Everything below is pure over already-fetched bytes, so the export is
# testable without hitting the network.


def _text(component, key: str) -> str:
    value = component.get(key)
    return "" if value is None else str(value).strip()


def _clean_summary(summary: str) -> str:
    """Drop the leading 🏐/🏆 decorations the calendar uses."""
    return _EMOJI.sub("", summary).strip()


def _split_location(location: str) -> tuple[str, str]:
    """Split an iCal LOCATION into (first line, full one-line address)."""
    location = location.replace("\\n", "\n").replace("\\,", ",")
    lines = [ln.strip() for ln in location.splitlines() if ln.strip()]
    if not lines:
        return "", ""
    return lines[0], ", ".join(lines)


def expand_events(
    ics_bytes: bytes, start: datetime.date, end: datetime.date
) -> list[dict]:
    """Expand the feed (recurrences and their overrides included) into a
    flat, date-sorted list of plain dicts."""
    calendar = Calendar.from_ical(ics_bytes)
    occurrences = recurring_ical_events.of(calendar).between(start, end)

    events = []
    for occurrence in occurrences:
        dtstart = occurrence["DTSTART"].dt
        dtend_prop = occurrence.get("DTEND")
        dtend = dtend_prop.dt if dtend_prop is not None else None
        # An all-day event is a bare date, not a datetime.
        all_day = not isinstance(dtstart, datetime.datetime)

        duration_min = None
        if dtend is not None and not all_day:
            duration_min = int((dtend - dtstart).total_seconds() // 60)

        summary = _text(occurrence, "SUMMARY")
        venue_name, address = _split_location(_text(occurrence, "LOCATION"))
        events.append(
            {
                "uid": _text(occurrence, "UID"),
                "summary": summary,
                "title": _clean_summary(summary),
                "start": dtstart,
                "date": dtstart if all_day else dtstart.date(),
                "all_day": all_day,
                "duration_min": duration_min,
                "description": _text(occurrence, "DESCRIPTION")
                .replace("\\n", " / ")
                .strip(),
                "venue_name": venue_name,
                "address": address,
            }
        )
    events.sort(key=lambda e: (e["date"], str(e["start"])))
    return events


def classify(event: dict) -> tuple[str, dict]:
    """Return ("game" | "practice" | "other", details) for one event."""
    title = event["title"]

    match = _GAME_VS.match(title)
    if match:
        return "game", {"opponent": match.group("opponent").strip(), "side": "Home"}

    match = _GAME_AT.match(title)
    if match:
        return "game", {"opponent": match.group("opponent").strip(), "side": "Away"}

    if _GAME_TBD.search(title):
        # Site is not settled until the bracket is, so leave Home/Away blank —
        # the importer reads blank as TBD.
        return "game", {"opponent": "TBD", "side": ""}

    if _PRACTICE.search(title):
        return "practice", {}

    return "other", {}


# --- formatting ----------------------------------------------------------------


def _fmt_date(value) -> str:
    return value.strftime("%m/%d/%Y")


def _fmt_time(event: dict) -> str:
    if event["all_day"]:
        return ""
    # TeamSnap wants a 12-hour clock; strftime pads the hour, "04:00 PM".
    return event["start"].strftime("%I:%M %p")


def _fmt_duration(event: dict) -> str:
    minutes = event["duration_min"]
    if event["all_day"] or not minutes:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _fmt_arrival(minutes: int | None, event: dict) -> str:
    # Arrival time only means something alongside a start time.
    if minutes is None or event["all_day"]:
        return ""
    return str(minutes)


def _venue_fields(event: dict, venue_map: dict) -> tuple[str, str, str]:
    """Return (venue, sub_venue, note_suffix).

    A Venue with no Sub-Venue is a hard import error, so an unmapped
    location becomes a note instead of a dropped address.
    """
    if not event["venue_name"]:
        return "", "", ""
    mapped = venue_map.get(event["venue_name"])
    if mapped and mapped.get("venue") and mapped.get("sub_venue"):
        return mapped["venue"], mapped["sub_venue"], ""
    return "", "", event["address"]


def _notes(event: dict, venue_map: dict) -> tuple[str, str, str]:
    venue, sub_venue, address_note = _venue_fields(event, venue_map)
    parts = [p for p in (event["description"], address_note) if p]
    return venue, sub_venue, " — ".join(parts)


GAME_HEADER = [
    "Team 1 Name*", "Team 1 Division*", "Team 1 Type*", "Team 1 Home/Away",
    "Team 2 Name", "Team 2 Division", "Team 2 Type", "Team 2 Home/Away",
    "Date* (mm/dd/yyyy)", "Start Time (HH:MM am/pm)", "Duration (HH:MM)",
    "Arrival Time (MM)", "Venue", "Sub-Venue", "Notes", "Exclude from Standings",
]

PRACTICE_HEADER = [
    "Practice Name", "Team*", "Team Division", "Date* (mm/dd/yyyy)",
    "Start Time (HH:MM am/pm)", "Duration (HH:MM)", "Arrival Time (MM)",
    "Venue", "Sub-Venue", "Notes",
]

OTHER_HEADER = [
    "Event Name", "Team*", "Division", "Date* (mm/dd/yyyy)",
    "Start Time (HH:MM am/pm)", "Duration (HH:MM)", "Arrival Time (MM)",
    "Venue", "Sub-Venue", "Notes",
]


def _game_row(event: dict, details: dict, team: str, division: str, venue_map: dict):
    venue, sub_venue, notes = _notes(event, venue_map)
    side = details["side"]
    opposite = {"Home": "Away", "Away": "Home"}.get(side, "")
    return [
        team, division, "Internal", side,
        details["opponent"], "", "External", opposite,
        _fmt_date(event["date"]), _fmt_time(event), _fmt_duration(event),
        _fmt_arrival(GAME_ARRIVAL_MIN, event), venue, sub_venue, notes, "No",
    ]


def _practice_row(event: dict, team: str, division: str, venue_map: dict):
    venue, sub_venue, notes = _notes(event, venue_map)
    return [
        event["title"], team, division, _fmt_date(event["date"]),
        _fmt_time(event), _fmt_duration(event),
        _fmt_arrival(PRACTICE_ARRIVAL_MIN, event), venue, sub_venue, notes,
    ]


def _other_row(event: dict, team: str, division: str, venue_map: dict):
    venue, sub_venue, notes = _notes(event, venue_map)
    return [
        event["title"], team, division, _fmt_date(event["date"]),
        _fmt_time(event), _fmt_duration(event),
        _fmt_arrival(OTHER_ARRIVAL_MIN, event), venue, sub_venue, notes,
    ]


def build_rows(
    events: list[dict],
    team: str = DEFAULT_TEAM,
    division: str = DEFAULT_DIVISION,
    venue_map: dict | None = None,
    include_all_day: bool = False,
) -> dict:
    """Sort events into the three template shapes, with warnings."""
    venue_map = venue_map or {}
    games, practices, other = [], [], []
    warnings: list[str] = []
    skipped: list[str] = []
    unmapped: set[str] = set()

    # All-day entries in this calendar duplicate a timed event on the same day
    # ("Tryouts!" over "Tryout Day 1"), so they'd import as second copies.
    timed_days = {e["date"] for e in events if not e["all_day"]}

    for event in events:
        if event["all_day"] and not include_all_day:
            if event["date"] in timed_days:
                skipped.append(
                    f"{_fmt_date(event['date'])} {event['title']} "
                    "(all-day, duplicates a timed event)"
                )
            else:
                skipped.append(f"{_fmt_date(event['date'])} {event['title']} (all-day)")
            continue

        kind, details = classify(event)
        venue, sub_venue, _ = _venue_fields(event, venue_map)
        if event["venue_name"] and not venue:
            unmapped.add(event["venue_name"])

        if kind == "game":
            games.append(_game_row(event, details, team, division, venue_map))
            if details["side"] == "Home" and event["address"]:
                if HOME_VENUE_MARKER not in event["address"].casefold():
                    warnings.append(
                        f"{_fmt_date(event['date'])} {event['title']} is marked Home "
                        f"but is scheduled at {event['venue_name']}"
                    )
            if not event["duration_min"] and not event["all_day"]:
                warnings.append(
                    f"{_fmt_date(event['date'])} {event['title']} has no end time; "
                    "Duration left blank, so Start Time was dropped too"
                )
        elif kind == "practice":
            practices.append(_practice_row(event, team, division, venue_map))
        else:
            other.append(_other_row(event, team, division, venue_map))

    for name in sorted(unmapped):
        warnings.append(
            f'Venue "{name}" is not in teamsnap-venues.json — address moved to '
            "Notes, Venue/Sub-Venue left blank"
        )

    return {
        "games": games,
        "practices": practices,
        "other": other,
        "warnings": warnings,
        "skipped": skipped,
    }


# --- writing -------------------------------------------------------------------


def load_venue_map(path: pathlib.Path = VENUE_MAP_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("venues", {})


def write_csvs(built: dict, out_dir: pathlib.Path) -> list[pathlib.Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, header, rows in (
        ("games", GAME_HEADER, built["games"]),
        ("practices", PRACTICE_HEADER, built["practices"]),
        ("other-events", OTHER_HEADER, built["other"]),
    ):
        path = out_dir / f"teamsnap-{name}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(rows)
        written.append(path)
    return written


# --- cli -----------------------------------------------------------------------


def _parse_date(value: str) -> datetime.date:
    return datetime.date.fromisoformat(value)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="jcvb.teamsnap_calendar",
        description="Export the published calendar into TeamSnap import CSVs.",
    )
    parser.add_argument("--url", help="calendar feed URL (defaults to JCVB_CALENDAR_URL)")
    parser.add_argument(
        "--from", dest="start", type=_parse_date,
        help="first date to export (YYYY-MM-DD, default today)",
    )
    parser.add_argument(
        "--to", dest="end", type=_parse_date,
        help="last date to export (YYYY-MM-DD, default 18 months out)",
    )
    parser.add_argument("--team", default=DEFAULT_TEAM)
    parser.add_argument("--division", default=DEFAULT_DIVISION)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--all-day", action="store_true",
        help="keep all-day events instead of skipping them as duplicates",
    )
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args(argv)

    start = args.start or datetime.date.today()
    end = args.end or (start + datetime.timedelta(days=548))

    events = expand_events(fetch_ics(resolve_url(args.url)), start, end)
    built = build_rows(
        events,
        team=args.team,
        division=args.division,
        venue_map=load_venue_map(),
        include_all_day=args.all_day,
    )
    written = write_csvs(built, args.out_dir)

    if args.json:
        print(json.dumps({
            "range": [start.isoformat(), end.isoformat()],
            "counts": {k: len(built[k]) for k in ("games", "practices", "other")},
            "files": [str(p) for p in written],
            "warnings": built["warnings"],
            "skipped": built["skipped"],
        }, indent=2))
        return 0

    print(f"{start} .. {end} — {len(events)} events from the feed")
    for path, count in zip(
        written, (len(built["games"]), len(built["practices"]), len(built["other"]))
    ):
        print(f"  {count:>4}  {path}")
    if built["skipped"]:
        print(f"\nSkipped {len(built['skipped'])}:")
        for line in built["skipped"]:
            print(f"  - {line}")
    if built["warnings"]:
        print(f"\nWarnings ({len(built['warnings'])}):")
        for line in built["warnings"]:
            print(f"  ! {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
