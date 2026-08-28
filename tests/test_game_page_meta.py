"""The share card for a game page.

Renders the real template so the assertions cover what actually ships, not a
reimplementation of it.
"""

import datetime

import pytest

from jcvb import postgame as pg
from jcvb import site_build

PLAYED = {
    "game": {
        "date": "2026-08-26",
        "opponent": "Harford Tech",
        "designation": "scrimmage",
        "home_away": "home",
        "sets": [[23, 25], [25, 22], [25, 19], [16, 25], [5, 15]],
    },
    "stats": {
        "aces": [5, 11, 5, 1, 0],
        "kills": [6, 5, 9, 6, 2],
        "blocks": [1, 1, 1, 0, 0],
        "service_errors": [4, 5, 2, 2, 4],
    },
}


def scheduled(played=None, **overrides):
    fields = dict(
        date=datetime.date(2026, 8, 26),
        opponent="Harford Tech",
        designation="scrimmage",
        home_away="home",
        varsity="5:00 PM",
        jv="3:30 PM",
        venue="Upper Gym",
    )
    fields.update(overrides)
    game = site_build.Game(**fields)
    game.played = played
    return game


def render(game):
    env = site_build.build_env()
    return env.get_template("game.html.j2").render(
        page="schedule",
        g=game,
        stat_keys=pg.PUBLIC_STAT_KEYS,
        previous=None,
        following=None,
        site={
            "name": "John Carroll Boys Volleyball",
            "short_name": "JCVB",
            "canonical_url": "https://sites.anvilor.com/jcvb",
            "season": 2026,
            "school": "The John Carroll School",
            "location": "Bel Air, Maryland",
            "league": "MIAA",
        },
        links={"roster": "#", "store": "#", "instagram": "#", "league": "#",
               "give": "#", "watch": "#"},
        cfg={},
        ver="test",
        base="/jcvb",
    )


def meta(html, prop):
    import re
    match = re.search(rf'property="og:{prop}" content="([^"]*)"', html)
    return match.group(1)


@pytest.fixture
def played_html():
    return render(scheduled(pg.parse_game(PLAYED, "2026-08-26-harford-tech")))


def test_completed_game_puts_the_result_in_the_og_title(played_html):
    assert meta(played_html, "title") == "L 2-3 vs Harford Tech · JCVB"


def test_completed_game_puts_every_set_in_the_og_description(played_html):
    description = meta(played_html, "description")
    assert "Harford Tech 3-2 (23-25, 25-22, 25-19, 16-25, 5-15)" in description
    assert "22 aces, 28 kills, 3 blocks" in description


def test_og_description_leaks_no_internal_stat(played_html):
    description = meta(played_html, "description")
    for term in ("service error", "attack error", "net violation", "doubles"):
        assert term not in description.lower()


def test_og_url_is_the_game_not_the_homepage(played_html):
    assert meta(played_html, "url") == (
        "https://sites.anvilor.com/jcvb/games/2026-08-26-harford-tech/"
    )


def test_unplayed_game_advertises_the_fixture_instead():
    html = render(scheduled())
    assert meta(html, "title") == "Aug 26 vs Harford Tech · JCVB"
    assert meta(html, "description") == (
        "Wed Aug 26 — JV 3:30 PM, Varsity 5:00 PM at Upper Gym."
    )


def test_away_win_reads_from_our_side():
    data = {
        **PLAYED,
        "game": {**PLAYED["game"], "home_away": "away",
                 "sets": [[25, 20], [25, 18], [25, 22]]},
        "stats": {"aces": [4, 3, 5], "kills": [8, 7, 9], "blocks": [2, 3, 2]},
    }
    game = scheduled(pg.parse_game(data, "2026-08-26-harford-tech"), home_away="away")
    assert meta(render(game), "title") == "W 3-0 @ Harford Tech · JCVB"


# --- match stats on small screens ----------------------------------------------


def test_stat_table_does_not_borrow_the_schedule_table_class(played_html):
    """`.sched-table` is display:none below 760px so the schedule can swap in
    cards — reusing it silently hid the match stats on every phone."""
    assert "stat-table" in played_html
    assert "sched-table" not in played_html


def test_stat_table_is_wrapped_so_it_can_scroll_rather_than_overflow(played_html):
    assert 'class="table-scroll"' in played_html


def test_stat_rows_render_with_totals(played_html):
    import re
    rows = re.findall(r"<tr>\s*<th scope=\"row\">([^<]+)</th>(.*?)</tr>",
                      played_html, re.S)
    labels = [name for name, _ in rows]
    assert labels == ["Aces", "Kills", "Blocks"]
    aces = [int(v) for v in re.findall(r">(\d+)<", rows[0][1])]
    assert aces == [5, 11, 5, 1, 0, 22]      # per set, then the total
