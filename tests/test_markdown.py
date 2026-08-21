import markdown
import pytest

from jcvb._markdown import BareUrlExtension


def render(text):
    return markdown.markdown(text, extensions=["extra", "sane_lists", BareUrlExtension()])


def test_bare_url_is_linked():
    assert (
        '<a href="https://sites.anvilor.com/jcvb/schedule/">'
        "https://sites.anvilor.com/jcvb/schedule/</a>" in render("Schedule at https://sites.anvilor.com/jcvb/schedule/")
    )


def test_trailing_period_stays_outside_the_link():
    html = render("Details at https://miaasports.net/2025_MIAA_Volleyball.")
    assert '<a href="https://miaasports.net/2025_MIAA_Volleyball">' in html
    assert html.endswith("</a>.</p>")


def test_underscores_in_url_are_not_emphasis():
    html = render("https://gomustangsports.com/a_b_c/d")
    assert "<em>" not in html
    assert 'href="https://gomustangsports.com/a_b_c/d"' in html


@pytest.mark.parametrize(
    "text",
    [
        "[Schedule](https://sites.anvilor.com/jcvb/schedule/)",
        '[Sheet](https://docs.google.com/x "https://nam12.safelinks.protection.outlook.com/?url=x")',
        "<https://sites.anvilor.com/jcvb/>",
        "`https://sites.anvilor.com/jcvb/`",
        '<a href="https://sites.anvilor.com/jcvb/">Site</a>',
    ],
)
def test_marked_up_urls_are_left_alone(text):
    """Nothing already in link, autolink, code, or raw-HTML form is touched —
    no nested anchors, no href mangled into link text."""
    html = render(text)
    assert "<a href" not in html.replace("<a href", "", 1)


def test_query_string_url_survives_intact():
    """The whole query string is kept; `&` is HTML-escaped in the attribute."""
    html = render("Sign up: https://forms.gle/bQqo71Dp3W7PeswU6?a=1&b=2")
    assert 'href="https://forms.gle/bQqo71Dp3W7PeswU6?a=1&amp;b=2"' in html
