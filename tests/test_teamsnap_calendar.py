import datetime

import pytest

from jcvb import teamsnap_calendar as tc

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
UID:game-home
SUMMARY:\xf0\x9f\x8f\x90 JC vs. Landon
LOCATION:The John Carroll School\\n703 E Churchville Rd\\, Bel Air\\, MD 21014
DTSTART;TZID=America/New_York:20260930T160000
DTEND;TZID=America/New_York:20260930T190000
END:VEVENT
BEGIN:VEVENT
UID:game-away
SUMMARY:\xf0\x9f\x8f\x90 JC @ Gilman
LOCATION:Gilman School\\n5407 Roland Ave\\, Baltimore\\, MD 21210
DTSTART;TZID=America/New_York:20261002T160000
DTEND;TZID=America/New_York:20261002T173000
END:VEVENT
BEGIN:VEVENT
UID:game-tbd
SUMMARY:\xf0\x9f\x8f\x86 MIAA Championship
DTSTART;TZID=America/New_York:20261106T163000
DTEND;TZID=America/New_York:20261106T180000
END:VEVENT
BEGIN:VEVENT
UID:practice-weekly
SUMMARY:Practice
DTSTART;TZID=America/New_York:20260921T153000
DTEND;TZID=America/New_York:20260921T173000
RRULE:FREQ=WEEKLY;COUNT=3;BYDAY=MO
END:VEVENT
BEGIN:VEVENT
UID:other
SUMMARY:Varsity Media Day
DTSTART;TZID=America/New_York:20260824T140000
DTEND;TZID=America/New_York:20260824T150000
END:VEVENT
BEGIN:VEVENT
UID:allday-dupe
SUMMARY:\xf0\x9f\x8f\x86MIAA V Championship
DTSTART;VALUE=DATE:20261106
DTEND;VALUE=DATE:20261107
END:VEVENT
END:VCALENDAR
"""

SEASON = (datetime.date(2026, 8, 1), datetime.date(2026, 12, 31))


@pytest.fixture
def events():
    return tc.expand_events(ICS, *SEASON)


def test_expands_recurrence_into_one_event_per_occurrence(events):
    practices = [e for e in events if e["title"] == "Practice"]
    assert [e["date"] for e in practices] == [
        datetime.date(2026, 9, 21),
        datetime.date(2026, 9, 28),
        datetime.date(2026, 10, 5),
    ]


def test_strips_emoji_and_keeps_local_wall_clock(events):
    game = next(e for e in events if e["uid"] == "game-home")
    assert game["title"] == "JC vs. Landon"
    assert tc._fmt_time(game) == "04:00 PM"
    assert tc._fmt_duration(game) == "03:00"


def test_classification():
    def kind(title):
        return tc.classify({"title": title})

    assert kind("JC vs. Landon") == ("game", {"opponent": "Landon", "side": "Home"})
    assert kind("JC @ Gilman") == ("game", {"opponent": "Gilman", "side": "Away"})
    assert kind("V Semi-Finals") == ("game", {"opponent": "TBD", "side": ""})
    assert kind("Practice")[0] == "practice"
    assert kind("Tryout Day 1")[0] == "practice"
    assert kind("JCVB Offseason Lift")[0] == "practice"
    assert kind("Varsity Media Day")[0] == "other"


def test_rows_land_in_the_right_template(events):
    built = tc.build_rows(events)
    assert len(built["games"]) == 3
    assert len(built["practices"]) == 3
    assert len(built["other"]) == 1
    # Every template's rows must be the same width as its header.
    assert all(len(r) == len(tc.GAME_HEADER) for r in built["games"])
    assert all(len(r) == len(tc.PRACTICE_HEADER) for r in built["practices"])
    assert all(len(r) == len(tc.OTHER_HEADER) for r in built["other"])


def test_all_day_duplicate_is_skipped(events):
    built = tc.build_rows(events)
    assert any("MIAA V Championship" in s for s in built["skipped"])
    assert not any("Exclude" in row for row in built["games"])


def test_home_away_sides_are_opposites(events):
    built = tc.build_rows(events)
    home, away, tbd = built["games"]
    assert (home[3], home[7]) == ("Home", "Away")
    assert (away[3], away[7]) == ("Away", "Home")
    # An undecided bracket leaves both sides blank rather than guessing.
    assert (tbd[3], tbd[7]) == ("", "")


def test_team_2_always_has_a_type(events):
    # The first import attempt failed on rows with a blank Team 2 Type.
    built = tc.build_rows(events)
    assert all(row[6] == "External" for row in built["games"])
    assert all(row[0] and row[4] and row[0] != row[4] for row in built["games"])


def test_unmapped_venue_becomes_a_note_not_a_venue(events):
    built = tc.build_rows(events)
    home = built["games"][0]
    assert (home[12], home[13]) == ("", "")
    assert "703 E Churchville Rd" in home[14]
    assert any("teamsnap-venues.json" in w for w in built["warnings"])


def test_mapped_venue_needs_both_halves(events):
    venue_map = {
        "The John Carroll School": {"venue": "John Carroll", "sub_venue": "Main Gym"},
        "Gilman School": {"venue": "Gilman", "sub_venue": ""},
    }
    built = tc.build_rows(events, venue_map=venue_map)
    home, away, _ = built["games"]
    assert (home[12], home[13]) == ("John Carroll", "Main Gym")
    assert home[14] == ""
    # A half-mapped venue stays blank — Venue without Sub-Venue is a hard error.
    assert (away[12], away[13]) == ("", "")
    assert "5407 Roland Ave" in away[14]


def test_neutral_site_home_game_is_flagged():
    ics = ICS.replace(b"The John Carroll School\\n703", b"Archbishop Spalding\\n8080")
    built = tc.build_rows(tc.expand_events(ics, *SEASON))
    assert any("marked Home" in w for w in built["warnings"])


def test_resolve_url_rewrites_webcal():
    assert tc.resolve_url("webcal://example.com/x").startswith("https://")


def test_writes_three_files(tmp_path, events):
    written = tc.write_csvs(tc.build_rows(events), tmp_path)
    assert [p.name for p in written] == [
        "teamsnap-games.csv",
        "teamsnap-practices.csv",
        "teamsnap-other-events.csv",
    ]
    assert all(p.read_text().startswith(("Team 1 Name", "Practice Name", "Event Name"))
               for p in written)
