import datetime

import pytest

from jcvb import teamsnap_schedule as ts

GAMES = [
    {
        "date": "2026-09-04", "opponent": "Bel Air", "designation": "scrimmage",
        "home_away": "home", "varsity": "5:00 PM", "jv": "3:30 PM", "venue": "Upper Gym",
    },
    {
        "date": "2026-09-09", "opponent": "Spalding", "designation": "conference",
        "home_away": "away", "varsity": "6:00 PM", "jv": "4:30 PM", "venue": "Away",
    },
    {
        "date": "2026-10-07", "opponent": "Friends", "designation": "conference",
        "home_away": "home", "varsity": "4:30 PM", "jv": "", "venue": "Upper Gym",
        "note": "Varsity only",
    },
    {
        "date": "2026-10-02", "opponent": "Gilman", "designation": "conference",
        "home_away": "away", "varsity": "5:30 PM", "jv": "4:15 PM", "venue": "Away",
    },
    {
        "date": "2026-11-04", "opponent": "Varsity Semi-Finals", "designation": "playoffs",
        "home_away": "tbd", "varsity": "TBD", "jv": "", "venue": "TBD",
        "note": "Varsity only",
    },
]

MASTER = [
    {
        "date": datetime.date(2026, 8, 12), "type": "TRYOUTS", "level": "All",
        "description": "Tryouts: Boys Volleyball", "time": "3:30-5:30 PM",
        "location": "UG", "note": "", "dismissal": "", "departure": "", "transport": "",
    },
    {
        "date": datetime.date(2026, 9, 8), "type": "Practice", "level": "JV",
        "description": "JV Boys Volleyball", "time": "3:30-5:30 PM",
        "location": "LG", "note": "", "dismissal": "", "departure": "", "transport": "",
    },
    {
        "date": datetime.date(2026, 9, 9), "type": "Game", "level": "JV",
        "description": "JV Boys Volleyball at Spalding", "time": "4:30 PM",
        "location": "n/a", "note": "", "dismissal": "1:45 PM",
        "departure": "2:00 PM", "transport": "JDT",
    },
    {
        "date": datetime.date(2026, 9, 4), "type": "Practice", "level": "Varsity",
        "description": "Varsity Boys Volleyball", "time": "CANCELED",
        "location": "", "note": "", "dismissal": "", "departure": "", "transport": "",
    },
]


VENUES = {
    "UG": {"venue": "John Carroll High School", "sub_venue": "Upper Gym"},
    "Upper Gym": {"venue": "John Carroll High School", "sub_venue": "Upper Gym"},
    "LG": {"venue": "John Carroll High School", "sub_venue": "Lower Gym"},
}
OPPONENTS = {
    "Spalding": {"venue": "Archbishop Spalding High School", "sub_venue": "Gym A"},
    "Gilman": {"venue": "Gilman School", "sub_venue": ""},
}


def build(**kwargs):
    return ts.build(GAMES, MASTER, **kwargs)


def rows(level, kind):
    return build()["levels"][level][kind]


def mapped_rows(level, kind, **kwargs):
    return build(venue_map=VENUES, opponent_map=OPPONENTS, **kwargs)["levels"][level][kind]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("3:30-5:30 PM", (datetime.time(15, 30), "02:00")),
        ("5:30-6:30 PM", (datetime.time(17, 30), "01:00")),
        ("4:30 PM", (datetime.time(16, 30), "")),
        ("TBD", (None, "")),
        ("CANCELED", (None, "")),
    ],
)
def test_parse_span(text, expected):
    assert ts._parse_span(text) == expected


def test_each_level_is_its_own_event():
    """The whole point: one matchup becomes a JV row and a Varsity row, each at
    its own start time — not one combined event."""
    jv = [r for r in rows("JV", "games") if r[8] == "09/04/2026"]
    varsity = [r for r in rows("Varsity", "games") if r[8] == "09/04/2026"]
    assert len(jv) == len(varsity) == 1
    assert jv[0][9] == "03:30 PM" and jv[0][1] == "JV"
    assert varsity[0][9] == "05:00 PM" and varsity[0][1] == "Varsity"


def test_varsity_only_night_makes_no_jv_row():
    assert not [r for r in rows("JV", "games") if r[8] == "10/07/2026"]
    assert [r for r in rows("Varsity", "games") if r[8] == "10/07/2026"]


def test_home_away_sides_are_mirrored():
    away = [r for r in rows("JV", "games") if r[8] == "09/09/2026"][0]
    assert away[3] == "Away" and away[7] == "Home"
    home = [r for r in rows("JV", "games") if r[8] == "09/04/2026"][0]
    assert home[3] == "Home" and home[7] == "Away"


def test_scrimmage_is_excluded_from_standings():
    scrimmage = [r for r in rows("JV", "games") if r[8] == "09/04/2026"][0]
    conference = [r for r in rows("JV", "games") if r[8] == "09/09/2026"][0]
    assert scrimmage[15] == "Yes"
    assert conference[15] == "No"


def test_playoff_round_has_tbd_opponent_and_no_side():
    row = [r for r in rows("Varsity", "games") if r[8] == "11/04/2026"][0]
    assert row[4] == "TBD"
    assert row[3] == "" and row[7] == ""
    # No start time means no duration or arrival either, or the import is rejected.
    assert row[9] == row[10] == row[11] == ""
    assert "Varsity Semi-Finals" in row[14]


def test_away_game_carries_travel_notes_from_the_master():
    row = [r for r in rows("JV", "games") if r[8] == "09/09/2026"][0]
    assert "depart 2:00 PM" in row[14] and "transport JDT" in row[14]


def test_unmapped_venue_goes_to_notes_not_the_venue_columns():
    """A Venue with no Sub-Venue is a hard import error."""
    row = [r for r in rows("JV", "games") if r[8] == "09/04/2026"][0]
    assert row[12] == row[13] == ""
    assert "Upper Gym" in row[14]


def test_tryouts_land_in_both_practice_files():
    for level in ("JV", "Varsity"):
        tryouts = [r for r in rows(level, "practices") if r[0] == "Tryouts"]
        assert len(tryouts) == 1
        assert tryouts[0][2] == level


def test_practices_stay_on_their_own_level():
    assert [r for r in rows("JV", "practices") if r[3] == "09/08/2026"]
    assert not [r for r in rows("Varsity", "practices") if r[3] == "09/08/2026"]


def test_canceled_practice_is_skipped_and_reported():
    built = build()
    assert not [r for r in built["levels"]["Varsity"]["practices"] if r[3] == "09/04/2026"]
    assert any("CANCELED" in line for line in built["skipped"])


def test_games_come_from_the_schedule_not_the_master():
    """The master's game rows are ignored, so a curated correction wins and no
    matchup is imported twice."""
    assert len([r for r in rows("JV", "games") if r[8] == "09/09/2026"]) == 1


# --- venues -------------------------------------------------------------------


def test_home_game_gets_the_school_and_its_gym():
    row = [r for r in mapped_rows("JV", "games") if r[8] == "09/04/2026"][0]
    assert row[12] == "John Carroll High School"
    assert row[13] == "Upper Gym"
    assert "Upper Gym" not in row[14]  # not duplicated into Notes


def test_practice_gym_code_resolves_to_a_sub_venue():
    row = [r for r in mapped_rows("JV", "practices") if r[3] == "09/08/2026"][0]
    assert (row[7], row[8]) == ("John Carroll High School", "Lower Gym")


def test_away_game_uses_the_opponents_venue():
    row = [r for r in mapped_rows("JV", "games") if r[8] == "09/09/2026"][0]
    assert (row[12], row[13]) == ("Archbishop Spalding High School", "Gym A")


def test_away_venue_without_a_sub_venue_stays_out_of_the_columns():
    """TeamSnap rejects a Venue with no Sub-Venue, so it goes to Notes and the
    run warns instead."""
    built = build(venue_map=VENUES, opponent_map=OPPONENTS)
    assert any('No venue for "Gilman"' in w for w in built["warnings"])
    row = [r for r in built["levels"]["JV"]["games"] if r[8] == "10/02/2026"][0]
    assert (row[12], row[13]) == ("", "")
    assert "Gilman School" in row[14]


def test_away_sub_venue_default_fills_the_gap():
    row = [
        r for r in mapped_rows("JV", "games", away_sub_venue="Main Gym")
        if r[8] == "09/09/2026"
    ][0]
    assert row[13] == "Gym A"  # an explicit mapping still wins
    gilman = [
        r for r in mapped_rows("JV", "games", away_sub_venue="Main Gym")
        if r[8] == "10/02/2026"
    ][0]
    assert (gilman[12], gilman[13]) == ("Gilman School", "Main Gym")


def test_playoff_row_has_no_venue():
    row = [r for r in mapped_rows("Varsity", "games") if r[8] == "11/04/2026"][0]
    assert (row[12], row[13]) == ("", "")
