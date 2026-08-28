import pytest

from jcvb import audience as aud


def test_every_group_tk_named_exists():
    assert set(aud.INTERNAL_GROUPS) == {
        "hc", "coaches", "varsity", "jv", "players", "team", "program", "admins",
    }


def test_containment_is_derived_from_membership():
    assert aud.can_view("hc", "coaches")        # the HC is a coach
    assert aud.can_view("varsity", "players")
    assert aud.can_view("jv", "players")
    assert aud.can_view("players", "team")
    assert aud.can_view("coaches", "team")


def test_narrower_groups_do_not_see_wider_material_the_other_way():
    assert not aud.can_view("coaches", "hc")
    assert not aud.can_view("players", "coaches")
    assert not aud.can_view("varsity", "jv")
    assert not aud.can_view("program", "team")   # parents are not on the team


def test_program_is_players_and_parents_not_coaches():
    assert not aud.can_view("coaches", "program")
    assert aud.can_view("varsity", "program")


def test_admins_are_the_hc_plus_school_admins():
    assert aud.can_view("hc", "admins")
    assert not aud.can_view("coaches", "admins")


def test_public_material_is_readable_by_anyone():
    assert aud.is_public("public")
    for group in aud.INTERNAL_GROUPS:
        assert aud.can_view(group, "public")
        assert not aud.is_public(group)


def test_public_is_wider_than_any_internal_group():
    for group in aud.INTERNAL_GROUPS:
        assert aud.wider_than("public", group)


def test_unknown_group_is_refused_by_name():
    with pytest.raises(aud.UnknownAudience, match="'boosters' is not a JCVB group"):
        aud.get("boosters")


def test_frontmatter_line_explains_itself():
    line = aud.frontmatter_line("team")
    assert line.startswith("audience: team")
    assert "Players, coaches, manager" in line
