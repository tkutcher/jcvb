"""Markdown bits shared by the static site and the emailed newsletter.

Obsidian previews a bare ``https://…`` URL as a link; Python-Markdown leaves it
as plain text. Newsletters are written in Obsidian, so URLs typed without
``[text](url)`` or ``<url>`` looked fine while drafting and then shipped
unlinked. ``BareUrlExtension`` closes that gap.
"""

import xml.etree.ElementTree as etree

from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor

# A bare URL runs to the first whitespace or angle bracket but may not END on
# sentence punctuation or a closing bracket, so "… at https://x/y." keeps the
# period out of the href. The lookbehind skips word chars, "@" and "/" so an
# email address or a scheme inside another URL's path is left alone.
BARE_URL_RE = r"""(?<![\w@/])(https?://[^\s<>]*[^\s<>.,;:!?)\]}"'])"""

# Registered below `html` (90) so URLs inside inline raw HTML are stashed first,
# and above `em_strong` (60) so underscores in a URL are not read as emphasis.
# Markdown links, autolinks, and code spans all run higher still, so a URL that
# is already marked up never reaches this pattern.
BARE_URL_PRIORITY = 85


class _BareUrlProcessor(InlineProcessor):
    def handleMatch(self, m, data):
        el = etree.Element("a")
        el.set("href", m.group(1))
        el.text = m.group(1)
        return el, m.start(0), m.end(0)


class BareUrlExtension(Extension):
    """Wrap bare http(s) URLs in an anchor, the way Obsidian previews them."""

    def extendMarkdown(self, md):
        md.inlinePatterns.register(
            _BareUrlProcessor(BARE_URL_RE, md), "bare_url", BARE_URL_PRIORITY
        )
