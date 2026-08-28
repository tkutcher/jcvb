"""Who a piece of JCVB material is for.

Every artifact this repo generates has an audience, and they are not the same:
the site is public, a recap is for anyone, the Keys to the Game card is for the
team, the tally transcription is for the coaches, and a roster export with dates
of birth is for the head coach. Labelling that on the artifact — rather than
holding it in someone's head — is what makes "don't publish that" checkable.

Groups are defined by their members, so containment is derived rather than
asserted: material labelled `coaches` is readable by `hc`, because every member
of `hc` is a member of `coaches`. Nothing here enforces access control on a
file system; it is a vocabulary plus the arithmetic to reason about it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Atomic principals. Groups below are unions of these — never of each other's
# labels directly, so containment stays computable.
HEAD_COACH = "head-coach"
ASSISTANT_COACHES = "assistant-coaches"
VARSITY_PLAYERS = "varsity-players"
JV_PLAYERS = "jv-players"
MANAGER = "manager"
PARENTS = "parents"
JC_ADMINS = "jc-admins"
EVERYONE = "everyone"


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    members: frozenset[str]
    description: str


def _group(key: str, label: str, members: set[str], description: str) -> Group:
    return Group(key, label, frozenset(members), description)


GROUPS: dict[str, Group] = {
    g.key: g
    for g in (
        _group("hc", "HC", {HEAD_COACH}, "Head coach only"),
        _group(
            "coaches",
            "Coaches",
            {HEAD_COACH, ASSISTANT_COACHES},
            "All coaches",
        ),
        _group(
            "varsity",
            "Varsity Team",
            {VARSITY_PLAYERS},
            "All current players on varsity",
        ),
        _group("jv", "JV Team", {JV_PLAYERS}, "All current players on JV"),
        _group(
            "players",
            "Players",
            {VARSITY_PLAYERS, JV_PLAYERS},
            "All current players",
        ),
        _group(
            "team",
            "Team",
            {VARSITY_PLAYERS, JV_PLAYERS, HEAD_COACH, ASSISTANT_COACHES, MANAGER},
            "Players, coaches, manager",
        ),
        _group(
            "program",
            "Program",
            {VARSITY_PLAYERS, JV_PLAYERS, PARENTS},
            "Current players and parents",
        ),
        _group(
            "admins",
            "Admins",
            {HEAD_COACH, JC_ADMINS},
            "HC + JC admins",
        ),
        # Not one of the internal groups — the label for material that is
        # already public (the site, the school's score form, social posts).
        _group("public", "Public", {EVERYONE}, "Anyone — published material"),
    )
}

INTERNAL_GROUPS = tuple(key for key in GROUPS if key != "public")

DEFAULT_AUDIENCE = "coaches"


class UnknownAudience(ValueError):
    pass


def get(key: str) -> Group:
    try:
        return GROUPS[key]
    except KeyError:
        raise UnknownAudience(
            f"{key!r} is not a JCVB group — pick one of: {', '.join(GROUPS)}"
        ) from None


def is_public(key: str) -> bool:
    return EVERYONE in get(key).members


def can_view(viewer: str, material: str) -> bool:
    """May everyone in `viewer` read material labelled `material`?"""
    if is_public(material):
        return True
    return get(viewer).members <= get(material).members


def wider_than(a: str, b: str) -> bool:
    """Is `a` a strictly wider audience than `b`?"""
    return get(b).members < get(a).members or (is_public(a) and not is_public(b))


def frontmatter_line(key: str) -> str:
    """The `audience:` line generated vault notes carry."""
    return f"audience: {get(key).key}   # {get(key).label} — {get(key).description}"
