import textwrap

import pytest

from jcvb import hudl

CSV = textwrap.dedent("""\
    JCS vs HTHS — All Athletes — Whole Match — Averages
    #,Athlete,MP,SP,0,Ace,S Err,S Att,S Rtg,S %,0,SR Perf,SR Good,SR Poor,SR Err,SR Att,SR Rtg,0,Kill,A Err,Att,H %,0,B Solo,B Assist,B Total,0,Assist,A Att,0,Digs,0,Sent,Received,0,Violations,BHE
    3,Jackson DeReamer,1,5,0,3,3,16,1.88,81.3%,0,2,1,0,1,4,2,0,15,5,34,0.294,0,0,0,0,0,0,0,0,0,0,1,-,0,-,1
    9,Peyton Williams,1,5,0,3,1,11,2.55,90.9%,0,12,5,5,5,27,1.89,0,10,6,22,0.182,0,0,1,1,0,1,2,0,6,0,2,-,0,-,0
    0,Tyler Olivi,1,5,0,2,2,16,1.94,87.5%,0,12,5,7,7,31,1.71,0,0,1,3,- 0.333,0,0,0,0,0,4,5,0,9,0,5,-,0,-,0
    13,warningUnknown Athlete,1,4,0,0,0,1,2,100.0%,0,4,2,2,0,8,2.25,0,0,1,1,- 1.000,0,0,0,0,0,0,3,0,5,0,1,-,0,-,1
    """)


@pytest.fixture
def match(tmp_path):
    path = tmp_path / "2026-08-26--vs-Harford-Tech-Hudl-Match-Totals.csv"
    path.write_text(CSV, encoding="utf-8")
    return hudl.parse_match_csv(path)


def test_filename_carries_the_date_opponent_and_scope(match):
    import datetime
    assert match.date == datetime.date(2026, 8, 26)
    assert match.opponent == "Harford Tech"
    assert match.scope == "Match-Totals"


def test_an_unnamed_export_is_refused_with_the_convention(tmp_path):
    path = tmp_path / "JCS vs HTHS — All Athletes — Whole Match — Averages.csv"
    path.write_text(CSV, encoding="utf-8")
    with pytest.raises(SystemExit, match="Hudl-<Scope>.csv"):
        hudl.parse_match_csv(path)


def test_player_lines_survive_hudls_spacer_columns(match):
    dereamer = match.by_last_name()["DeReamer"]
    assert (dereamer.kills, dereamer.attack_attempts, dereamer.attack_errors) == (15, 34, 5)
    assert (dereamer.aces, dereamer.serve_errors, dereamer.serve_attempts) == (3, 3, 16)


def test_negative_hitting_percentage_parses(match):
    """Hudl writes -0.333 as '- 0.333'."""
    assert match.by_last_name()["Olivi"].hitting_pct == pytest.approx(-1 / 3)


def test_serve_pct_is_serves_in_play_over_attempts(match):
    assert match.by_last_name()["Williams"].serve_pct == pytest.approx(10 / 11)
    assert hudl.format_pct(match.by_last_name()["Williams"].serve_pct) == "91%"


def test_unidentified_rows_are_surfaced_not_dropped(match):
    """A jersey number Hudl could not name still counts in the totals."""
    unknown = match.unidentified()
    assert [p.number for p in unknown] == ["13"]
    assert "Unknown" not in match.by_last_name()
    assert match.totals()["serve_attempts"] == 16 + 11 + 16 + 1


def test_season_pct_weights_by_attempts_not_by_match(match):
    """Two serves at 50% should not offset twenty at 90%."""
    light = hudl.PlayerLine("9", "Peyton Williams", 1, 0, 0, 0, 0, 1, 2, None,
                            0, None, 0, 0, 0)
    later = hudl.MatchStats(match.date.replace(day=27), "Bel Air", "Match-Totals",
                            [light])
    stats = hudl.serve_percentages([match, later])
    williams = stats["Williams"]
    assert williams["season_attempts"] == 13
    assert williams["season_pct"] == pytest.approx(11 / 13)
    assert williams["matches"] == 2


def test_trending_window_only_counts_the_last_n_matches(match):
    line = lambda err, att: hudl.PlayerLine(  # noqa: E731
        "9", "Peyton Williams", 1, 0, 0, 0, 0, err, att, None, 0, None, 0, 0, 0)
    season = [
        hudl.MatchStats(match.date.replace(day=d), "x", "Match-Totals", [line(5, 10)])
        for d in range(1, 7)
    ] + [hudl.MatchStats(match.date.replace(day=20), "x", "Match-Totals", [line(0, 10)])]
    stats = hudl.serve_percentages(season, trending_window=2)["Williams"]
    assert stats["trending_matches"] == 2
    assert stats["trending_pct"] == pytest.approx(15 / 20)   # last two only
    assert stats["season_pct"] == pytest.approx(40 / 70)     # all seven: 30 errors of 70


# --- the serving board ---------------------------------------------------------

BOARD = textwrap.dedent("""\
    |                | Season <br>S% | Trending <br>S% | Standing Float | Jump Float |
    | -------------- | :-----------: | :-------------: | :------------: | :--------: |
    | **Boyle**      |               |                 |       🟢       |     🟡     |
    | **Kim**        |               |                 |       🟢       |     🟡     |
    | **L. Brown**   |               |                 |       🟢       |     🔴     |
    """)


def test_board_fills_only_the_two_percentage_columns():
    stats = {"Boyle": {"season_pct": 0.75, "trending_pct": 0.8}}
    updated, filled, skipped = hudl.update_serving_status(BOARD, stats)
    boyle = [ln for ln in updated.splitlines() if "Boyle" in ln][0]
    assert "75%" in boyle and "80%" in boyle
    assert filled == ["Boyle 75%/80%"]
    assert "Kim" in skipped


def test_board_never_touches_the_lights():
    """The lights are TK's coaching judgement, not a stat."""
    stats = {"Boyle": {"season_pct": 0.75, "trending_pct": 0.8}}
    updated, _, _ = hudl.update_serving_status(BOARD, stats)
    for line in updated.splitlines():
        if "Boyle" in line:
            assert line.count("🟢") == 1 and line.count("🟡") == 1
    assert updated.count("🟢") == BOARD.count("🟢")
    assert updated.count("🔴") == BOARD.count("🔴")


def test_board_leaves_a_player_with_no_serves_blank():
    updated, _, skipped = hudl.update_serving_status(BOARD, {})
    assert updated == BOARD
    assert "Kim" in skipped and "L. Brown" in skipped


def test_board_matches_initialled_names_by_last_name():
    stats = {"Brown": {"season_pct": 0.9, "trending_pct": 0.9}}
    updated, filled, _ = hudl.update_serving_status(BOARD, stats)
    assert filled == ["L. Brown 90%/90%"]


def test_highlights_are_positives_only(match):
    lines = hudl.highlights(match)
    assert "Jackson DeReamer — 15 kills" in lines
    assert "Peyton Williams — 10 kills" in lines
    assert not any("err" in line.lower() for line in lines)
