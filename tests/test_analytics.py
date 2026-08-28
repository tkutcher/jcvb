"""The analytics tag is off unless two separate things are true.

An id in config is not enough — the build has to be the production one. That
keeps local rebuilds and staging traffic out of the numbers, which is the
failure mode that makes analytics untrustworthy for a small site.
"""

import pytest

from jcvb import site_build


def render(analytics):
    env = site_build.build_env()
    return env.get_template("base.html.j2").render(
        page="home",
        analytics=analytics,
        site={"name": "JCVB", "short_name": "JCVB", "description": "",
              "canonical_url": "https://sites.anvilor.com/jcvb", "season": 2026,
              "school": "The John Carroll School", "location": "Bel Air, Maryland",
              "league": "MIAA"},
        links={"roster": "#", "store": "#", "instagram": "#", "league": "#",
               "give": "#", "watch": "#"},
        cfg={}, ver="test", base="/jcvb",
    )


ON = {"ga_id": "G-ABC1234567", "enabled": True, "active": True}


def test_tag_renders_when_configured_and_enabled():
    html = render(ON)
    assert "googletagmanager.com/gtag/js?id=G-ABC1234567" in html
    assert "gtag('config', 'G-ABC1234567'" in html


@pytest.mark.parametrize(
    "analytics",
    [
        {"ga_id": "G-ABC1234567", "enabled": False, "active": False},  # staging
        {"ga_id": "", "enabled": True, "active": False},               # unconfigured
        {"ga_id": "", "enabled": False, "active": False},
    ],
)
def test_no_tag_without_both_halves(analytics):
    assert "googletagmanager" not in render(analytics)


def test_a_page_rendered_without_analytics_context_still_builds():
    """Templates are rendered directly in tests; a missing key must not explode."""
    env = site_build.build_env()
    html = env.get_template("base.html.j2").render(
        page="home",
        site={"name": "JCVB", "short_name": "JCVB", "description": "",
              "canonical_url": "", "season": 2026, "school": "", "location": "",
              "league": ""},
        links={"roster": "#", "store": "#", "instagram": "#", "league": "#",
               "give": "#", "watch": "#"},
        cfg={}, ver="test", base="/jcvb",
    )
    assert "googletagmanager" not in html


def test_ad_profiling_is_switched_off():
    """Minors are named on this site — nothing here should feed an ad profile."""
    html = render(ON)
    assert "allow_google_signals: false" in html
    assert "allow_ad_personalization_signals: false" in html
