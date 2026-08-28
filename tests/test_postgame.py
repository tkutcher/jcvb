import urllib.parse

import pytest

from jcvb import postgame as pg

FIVE_SET_LOSS = {
    "game": {
        "date": "2026-08-26",
        "opponent": "Harford Tech",
        "designation": "scrimmage",
        "home_away": "home",
        "sets": [[23, 25], [25, 22], [25, 19], [16, 25], [5, 15]],
    },
    "stats": {
        "aces": [5, 11, 5, 0, 0],
        "service_errors": [4, 5, 2, 2, 4],
        "kills": [6, 5, 9, 6, 2],
        "blocks": [1, 1, 1, 0, 0],
        "attack_errors": [1, 0, 3, 3, 1],
        "communication_errors": [0, 0, 0, 0, 0],
        "net_violations": [0, 0, 1, 0, 0],
        "doubles_lifts": [0, 0, 0, 0, 0],
    },
    "recap": {"body": "A good first look."},
}

SWEEP_WIN = {
    "game": {
        "date": "2026-09-18",
        "opponent": "Boys Latin",
        "designation": "conference",
        "home_away": "home",
        "sets": [[25, 20], [25, 18], [25, 22]],
    },
    "stats": {
        "aces": [4, 3, 5],
        "service_errors": [1, 2, 1],
        "kills": [8, 7, 9],
        "blocks": [2, 3, 2],
        "attack_errors": [2, 1, 0],
        "communication_errors": [0, 0, 0],
        "net_violations": [0, 0, 0],
        "doubles_lifts": [0, 0, 0],
    },
}


def game(data=None, slug="2026-08-26-harford-tech"):
    return pg.parse_game(data or FIVE_SET_LOSS, slug)


# --- derived result ------------------------------------------------------------


def test_set_results_and_match_score():
    g = game()
    assert g.set_results == ["L", "W", "W", "L", "L"]
    assert (g.sets_won, g.sets_lost) == (2, 3)
    assert g.won is False
    assert g.score_line == "Harford Tech 3-2"   # form wants the winner first
    assert g.jc_set_score == "2-3"              # our own site is JC-first
    assert g.set_scores == "23-25, 25-22, 25-19, 16-25, 5-15"


def test_win_reads_from_jc_side():
    g = game(SWEEP_WIN, "2026-09-18-boys-latin")
    assert g.won is True
    assert g.score_line == "JC 3-0"


def test_totals():
    assert game().totals()["aces"] == 21
    assert game().totals()["service_errors"] == 17


def test_stats_must_match_the_number_of_sets():
    bad = {**FIVE_SET_LOSS, "stats": {**FIVE_SET_LOSS["stats"], "aces": [1, 2]}}
    with pytest.raises(SystemExit, match="2 entries but the match went 5"):
        pg.parse_game(bad, "bad")


# --- records -------------------------------------------------------------------


def test_scrimmages_never_touch_the_record():
    season = [game(), game(SWEEP_WIN, "2026-09-18-boys-latin")]
    assert pg.records(season) == {"overall": "1-0", "conference": "1-0"}


def test_record_is_as_of_the_game_being_reported():
    season = [game(), game(SWEEP_WIN, "2026-09-18-boys-latin")]
    assert pg.records(season, through=game().date)["overall"] == "0-0"


# --- report card ---------------------------------------------------------------


def rows_by_key(g):
    return {row["key"]: row["marks"] for row in pg.evaluate(g)}


def test_arithmetic_rows_are_auto_marked():
    marks = rows_by_key(game())
    assert marks["net"] == [True, True, False, True, True]          # S3 had one
    assert marks["service_errors"] == [False, False, True, True, False]  # max 2
    assert marks["attack_errors"] == [True] * 5                     # max 3
    assert marks["blocks"] == [False] * 5                           # needs 2+
    assert marks["kills"] == [True, True, True, True, False]        # 5+ big-boy
    assert marks["aces_over_se"] == [True, True, True, False, False]


def test_judgment_rows_stay_unmarked_until_filled():
    assert rows_by_key(game())["rotation"] == [None] * 5


def test_race_to_15_only_resolves_when_the_set_says_so():
    """Scoring under 15 settles it; anything else needs a human."""
    assert rows_by_key(game())["race_to_15"] == [None, None, None, None, False]


def test_manual_marks_fill_the_gaps():
    data = {**FIVE_SET_LOSS, "report_card": {"rotation": "✅✅❌✅✅"}}
    assert rows_by_key(game(data))["rotation"] == [True, True, False, True, True]


def test_manual_marks_never_override_the_tallies():
    data = {**FIVE_SET_LOSS, "report_card": {"blocks": "✅✅✅✅✅"}}
    assert rows_by_key(game(data))["blocks"] == [False] * 5


def test_rating_is_checks_over_sets_once_everything_is_marked():
    filled = {key: "✅" * 3 for key in
              ("rotation", "meet_center", "no_complaints", "energy", "sr_rating",
               "run_5", "no_opp_run", "defensive_play", "race_to_15")}
    g = game({**SWEEP_WIN, "report_card": filled}, "2026-09-18-boys-latin")
    result = pg.score(pg.evaluate(g), g.sets_played)
    assert result["provisional"] is False
    assert result["rating"] == pytest.approx(result["checks"] / 3)
    assert result["band"] == "Near Perfect 💯"


def test_card_says_pending_rather_than_grading_a_half_filled_sheet():
    card = pg.render_report_card(game())
    assert "rating pending" in card
    assert "Poor" not in card.split("**Key**")[0]
    assert "23-25, 25-22, 25-19, 16-25, 5-15" in card


# --- google form ---------------------------------------------------------------


def form_params(g, season=None):
    query = urllib.parse.urlparse(pg.form_prefill_url(g, season or [g])).query
    return dict(urllib.parse.parse_qsl(query))


def test_form_prefill_carries_the_fixed_fields():
    params = form_params(game())
    assert params[pg.FORM_FIELDS["gender"]] == "Boys"
    assert params[pg.FORM_FIELDS["level"]] == "Varsity"
    assert params[pg.FORM_FIELDS["sport"]] == "Volleyball"
    assert params["usp"] == "pp_url"


def test_form_prefill_splits_the_date_field():
    params = form_params(game())
    field = pg.FORM_FIELDS["date"]
    assert (params[f"{field}_year"], params[f"{field}_month"], params[f"{field}_day"]) == (
        "2026", "8", "26",
    )


def test_form_recap_carries_set_scores_and_the_recap_link():
    params = form_params(game())
    recap = params[pg.FORM_FIELDS["recap"]]
    assert "23-25, 25-22, 25-19, 16-25, 5-15" in recap
    assert "sites.anvilor.com/jcvb/games/2026-08-26-harford-tech/" in recap
    assert params[pg.FORM_FIELDS["score"]] == (
        "Harford Tech 3-2 (23-25, 25-22, 25-19, 16-25, 5-15)"
    )


def test_form_next_game_comes_from_the_schedule(tmp_path):
    """The next match has not been played, so it only exists on the schedule."""
    (tmp_path / "2026.toml").write_text(
        '[[games]]\ndate = "2026-09-04"\nopponent = "Bel Air"\n'
        'home_away = "home"\nvarsity = "5:00 PM"\n',
        encoding="utf-8",
    )
    assert pg._next_game([], game(), tmp_path) == "9/4 vs Bel Air 5:00 PM"


def test_form_next_game_falls_back_to_played_games(tmp_path):
    season = [game(), game(SWEEP_WIN, "2026-09-18-boys-latin")]
    assert pg._next_game(season, game(), tmp_path) == "9/18 vs Boys Latin"


# --- scorebook -----------------------------------------------------------------

WITH_BOOK = {
    **FIVE_SET_LOSS,
    "scorebook": {
        "first_serve": ["opp", "jc", "opp", "jc", "opp"],
        "jc": [
            [3, 4, 6, 10, 11, 13, 14, 16, 18, 21, 22, 23],
            [4, 5, 6, 7, 12, 13, 16, 17, 20, 21, 23, 25],
            [2, 4, 8, 9, 13, 14, 15, 16, 19, 20, 22, 24, 25],
            [3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16],
            [1, 2, 3, 4, 5],
        ],
        "opp": [
            [2, 5, 9, 12, 14, 15, 16, 18, 19, 22, 24, 25],
            [2, 3, 4, 5, 6, 7, 9, 13, 14, 15, 19, 22],
            [1, 2, 4, 5, 7, 8, 9, 13, 15, 16, 17, 19],
            [1, 2, 4, 9, 10, 11, 13, 14, 18, 20, 24, 25],
            [5, 6, 8, 14, 15],
        ],
    },
}


def test_runs_are_the_diffs_of_term_end_scores():
    assert pg.runs([3, 4, 6, 10]) == [3, 1, 2, 4]
    assert pg.longest_run([3, 4, 6, 10]) == 4


def test_race_to_15_replays_alternating_service_terms():
    # jc serves first and reaches 16 while opp is still on 9
    assert pg.race_to([4, 12, 16], [2, 9, 13], "jc") == "jc"
    assert pg.race_to([4, 12, 14], [2, 9, 15], "opp") == "opp"


def test_race_returns_none_when_neither_side_gets_there():
    assert pg.race_to([3], [2], "jc") is None


def test_scorebook_rows_are_auto_marked():
    marks = rows_by_key(game(WITH_BOOK))
    assert marks["run_5"] == [False, True, False, False, False]      # S2 ran 5
    assert marks["no_opp_run"] == [True, True, True, False, False]   # S4 5, S5 6
    assert marks["race_to_15"] == [False, True, True, False, False]


def test_scorebook_must_agree_with_the_set_scores():
    """A misread digit shows up as a set that does not end where the book says."""
    broken = {**WITH_BOOK}
    broken["scorebook"] = {**WITH_BOOK["scorebook"], "jc": [[3, 4, 6, 10, 22]] + WITH_BOOK["scorebook"]["jc"][1:]}
    with pytest.raises(SystemExit, match="set 1 ends at 22 but the set score says 23"):
        pg.parse_game(broken, "broken")


def test_a_game_without_a_scorebook_still_loads():
    marks = rows_by_key(game())
    assert marks["run_5"] == [None] * 5
    assert marks["race_to_15"] == [None, None, None, None, False]


def test_slug_matches_the_site():
    import datetime
    assert pg.slugify(datetime.date(2026, 9, 15), "St. Paul's") == "2026-09-15-st-paul-s"


# --- what the public sees ------------------------------------------------------


INTERNAL_STATS = (
    "service_errors",
    "attack_errors",
    "communication_errors",
    "net_violations",
    "doubles_lifts",
)


def test_public_stats_are_only_the_objective_three():
    assert pg.PUBLIC_STAT_KEYS == ("aces", "kills", "blocks")
    assert set(pg.PUBLIC_STAT_KEYS).isdisjoint(INTERNAL_STATS)


def test_public_stats_drop_every_internal_tally():
    """The site is public; error tallies are the team's business."""
    public = game().public_stats()
    assert list(public) == ["aces", "kills", "blocks"]
    for key in INTERNAL_STATS:
        assert key not in public
        assert key not in game().public_totals()


def test_public_totals_still_add_up():
    assert game().public_totals() == {"aces": 21, "kills": 28, "blocks": 3}


def test_internal_surfaces_keep_everything():
    """The report card and the vault note are internal — they see it all."""
    assert game().totals()["service_errors"] == 17
    assert "Service Errors" in pg.render_stats_note(game())
    assert "Max 2 SE/Set" in pg.render_report_card(game())


def test_generated_notes_declare_their_audience():
    """The card is read with the team; the stats note is a coaches' document."""
    assert "audience: team" in pg.render_report_card(game())
    assert "audience: coaches" in pg.render_stats_note(game())


def test_form_score_always_spells_out_the_sets():
    """The school's Score box must carry the set breakdown, not just the match."""
    assert game().form_score == "Harford Tech 3-2 (23-25, 25-22, 25-19, 16-25, 5-15)"
    sweep = game(SWEEP_WIN, "2026-09-18-boys-latin")
    assert sweep.form_score == "JC 3-0 (25-20, 25-18, 25-22)"


# --- serve receive -------------------------------------------------------------

WITH_SR = {
    **FIVE_SET_LOSS,
    "serve_receive": {
        "T. Olivi": ["301211001", "033", "0330", "0231332300", "310303"],
        "Sam": ["1", "002", "3", "", ""],
        "Logan": ["13", "", "3133", "32", "3"],
        "Andrew": ["", "01", "", "", ""],
        "DeReamer": ["0", "", "2", "2", ""],
        "Peyton": ["1201012", "33", "1321303", "2330332", "200"],
        "Nate": ["", "200", "", "", ""],
        "aces_against": [2, 3, 2, 4, 1],
    },
}


def test_team_rating_is_the_mean_of_every_reception():
    sr = game(WITH_SR).serve_receive
    assert sr.receptions(0) == 20
    assert sr.rating(0) == pytest.approx(21 / 20)     # 1.05
    assert sr.rating(2) == pytest.approx(2.0)
    assert sr.match_rating() == pytest.approx(127 / 80)


def test_sr_row_marks_against_the_2_point_target():
    assert rows_by_key(game(WITH_SR))["sr_rating"] == [False, False, True, True, False]


def test_a_set_nobody_received_in_is_unmarked_not_zero():
    data = {**WITH_SR, "serve_receive": {"Solo": ["3", "", "3", "3", "3"]}}
    marks = rows_by_key(game(data))["sr_rating"]
    assert marks[1] is None
    assert marks[0] is True


def test_ratings_outside_the_scale_are_refused():
    data = {**WITH_SR, "serve_receive": {"Solo": ["34", "", "", "", ""]}}
    with pytest.raises(SystemExit, match="'4' — reception ratings are 0-3"):
        pg.parse_game(data, "bad")


def test_a_passer_must_cover_every_set():
    data = {**WITH_SR, "serve_receive": {"Solo": ["3", "3"]}}
    with pytest.raises(SystemExit, match="covers 2 sets but the match went 5"):
        pg.parse_game(data, "bad")


def test_aces_against_are_not_the_aces_we_served():
    g = game(WITH_SR)
    assert g.serve_receive.aces_against == [2, 3, 2, 4, 1]
    assert g.totals()["aces"] == 21          # ours, from the tally sheet
    assert "aces_against" not in g.public_stats()


def test_serve_receive_never_reaches_a_public_surface():
    """SR is a coaching measure — it stays in the report card and vault note."""
    g = game(WITH_SR)
    assert list(g.public_stats()) == ["aces", "kills", "blocks"]
    assert "Serve receive" in pg.render_stats_note(g)


# --- reading a filled-in card back ---------------------------------------------

FILLED_CARD = """
| No rotation errors or sub issues | ❌ ✅ ✅ ✅ ✅ | Confused S1 |
| Meet in the center | ✅ ✅ ✅ ✅ ✅ |  |
| No complaints | ✅ ❌ ✅ ✅ ✅ | S2 - JY |
| Good energy, effort, focus | ✅ ✅ ❌ ❌ ❌ |  |
| 2+ blocks | ✅ ✅ ✅ ✅ ✅ | someone got optimistic |
"""


def test_absorb_reads_the_judgment_rows():
    absorbed = pg.absorb_card(game(), FILLED_CARD)
    assert absorbed["marks"]["rotation"] == "❌✅✅✅✅"
    assert absorbed["marks"]["no_complaints"] == "✅❌✅✅✅"
    assert absorbed["notes"]["no_complaints"] == "S2 - JY"


def test_absorb_refuses_to_take_an_auto_row_from_the_card():
    """Blocks come from the tally sheet — editing the card cannot change them."""
    absorbed = pg.absorb_card(game(), FILLED_CARD)
    assert "blocks" not in absorbed["marks"]
    assert any("2+ blocks" in c for c in absorbed["conflicts"])


def test_absorb_reports_rows_that_were_deleted_from_the_card():
    absorbed = pg.absorb_card(game(), FILLED_CARD)
    assert "defensive_play" in absorbed["missing_rows"]
    assert "rotation" not in absorbed["missing_rows"]


def test_writing_back_keeps_marks_and_notes_in_their_own_sections(tmp_path):
    """`sr_rating` is a key in both sections — a blind replace would cross them."""
    path = tmp_path / "2026-08-26-harford-tech.toml"
    path.write_text(
        '[report_card]\nrotation = "....."\nsr_rating = "....."\n\n'
        '[notes]\nsr_rating = "old note"\n',
        encoding="utf-8",
    )
    pg.apply_to_game_file(
        "2026-08-26-harford-tech",
        {"marks": {"rotation": "❌✅✅✅✅"}, "notes": {"sr_rating": "new note"}},
        games_dir=tmp_path,
        vault_root=tmp_path / "no-vault",
    )
    written = path.read_text(encoding="utf-8")
    card, notes = written.split("[notes]")
    assert 'rotation = "❌✅✅✅✅"' in card
    assert 'sr_rating = "....."' in card      # untouched by the note
    assert 'sr_rating = "new note"' in notes


def test_writing_back_preserves_trailing_comments(tmp_path):
    path = tmp_path / "g.toml"
    path.write_text('[report_card]\nenergy = "....."   # why\n', encoding="utf-8")
    pg.apply_to_game_file("g", {"marks": {"energy": "✅✅❌❌❌"}, "notes": {}},
                          games_dir=tmp_path, vault_root=tmp_path / "no-vault")
    assert path.read_text(encoding="utf-8") == '[report_card]\nenergy = "✅✅❌❌❌"   # why\n'


# --- vault sync ----------------------------------------------------------------


def test_sync_copies_game_files_out_of_the_vault(tmp_path):
    vault = tmp_path / "daily-plans" / "2026-08-26.JCVB"
    vault.mkdir(parents=True)
    (vault / "2026-08-26-harford-tech.toml").write_text("x = 1\n", encoding="utf-8")
    games = tmp_path / "games"
    assert pg.sync_from_vault(games, tmp_path / "daily-plans") == [
        "2026-08-26-harford-tech"
    ]
    assert (games / "2026-08-26-harford-tech.toml").read_text() == "x = 1\n"
    # second run is a no-op
    assert pg.sync_from_vault(games, tmp_path / "daily-plans") == []


def test_sync_is_quiet_when_the_vault_is_not_mounted(tmp_path):
    assert pg.sync_from_vault(tmp_path / "games", tmp_path / "nope") == []


def test_an_explicit_games_dir_is_never_redirected_to_the_real_vault(tmp_path):
    """Guards the bug this test suite hit: a default vault lookup made
    `games_dir` advisory, so a test wrote into TK's actual game file."""
    (tmp_path / "g.toml").write_text('[report_card]\nrotation = "....."\n', encoding="utf-8")
    written = pg.apply_to_game_file(
        "g", {"marks": {"rotation": "✅✅✅✅✅"}, "notes": {}},
        games_dir=tmp_path, vault_root=tmp_path / "no-vault",
    )
    assert written == tmp_path / "g.toml"


def test_generated_notes_carry_their_obsidian_css_class():
    """`cssclasses` is what scopes obsidian/jcvb.css to these notes."""
    assert "  - jcvb-report-card" in pg.render_report_card(game())
    assert "  - jcvb-stats-note" in pg.render_stats_note(game())


# --- match totals on the card --------------------------------------------------


def test_card_ends_with_team_totals_and_per_set_rates():
    card = pg.render_report_card(game(WITH_SR))
    totals = card.split("### Match totals")[1]
    assert "| Aces | 21 | 4.2 |" in totals          # 21 over 5 sets
    assert "| Kills (big boy) | 28 | 5.6 |" in totals
    assert "| Blocks (big boy) | 3 | 0.6 |" in totals
    assert "| **Serve receive** | **1.59** | 80 receptions |" in totals
    assert "| Aces against | 12 | 2.4 |" in totals


def test_totals_come_after_the_marks_not_before():
    card = pg.render_report_card(game(WITH_SR))
    assert card.index("### Match totals") > card.index("**Key**")


def test_season_block_waits_until_there_is_a_season():
    """One match in, a per-match average is just the match — skip it."""
    assert "Season to date" not in pg.render_report_card(game(WITH_SR), season=[game()])


def test_season_block_averages_per_match_and_per_set():
    later = {
        **SWEEP_WIN,
        "serve_receive": {"Solo": ["3", "3", "3"], "aces_against": [1, 1, 1]},
    }
    season = [game(WITH_SR), game(later, "2026-09-18-boys-latin")]
    card = pg.render_report_card(season[1], season=season)
    block = card.split("### Season to date")[1]
    assert "2 matches, 8 sets" in card
    # 21 + 12 aces over 2 matches / 8 sets
    assert "| Aces | 16.5 | 4.1 |" in block
    assert "**Serve receive**" in block


# --- internal write-up vs public recap -----------------------------------------

INTERNAL = "We were way too flat and needed more energy."
PUBLIC = "A good first look that went the distance."


def test_card_uses_the_internal_writeup_not_the_public_recap():
    data = {**FIVE_SET_LOSS, "card": {"writeup": INTERNAL},
            "recap": {"body": PUBLIC}}
    card = pg.render_report_card(game(data))
    assert f"*{INTERNAL}*" in card
    assert PUBLIC not in card


def test_card_never_falls_back_to_the_public_recap():
    """Different audiences: the recap is written to be supportive for families,
    the card is where the blunt version lives. A missing write-up is a gap to
    fill, not a reason to publish one voice in the other's place."""
    data = {**FIVE_SET_LOSS, "recap": {"body": PUBLIC}}
    card = pg.render_report_card(game(data))
    assert PUBLIC not in card
    assert "(write-up to come)" in card


def test_absorbing_a_card_keeps_the_writeup():
    card = pg.render_report_card(
        game({**FIVE_SET_LOSS, "card": {"writeup": INTERNAL}})
    )
    assert pg.absorb_card(game(), card)["card"] == {"writeup": INTERNAL}


def test_absorbing_an_unwritten_card_does_not_store_the_placeholder():
    card = pg.render_report_card(game())
    assert pg.absorb_card(game(), card)["card"] == {}


def test_writeup_survives_a_full_round_trip(tmp_path):
    path = tmp_path / "g.toml"
    path.write_text('[card]\nwriteup = "old"\n', encoding="utf-8")
    pg.apply_to_game_file(
        "g",
        {"marks": {}, "notes": {}, "card": {"writeup": INTERNAL}},
        games_dir=tmp_path,
        vault_root=tmp_path / "no-vault",
    )
    assert f'writeup = "{INTERNAL}"' in path.read_text(encoding="utf-8")
