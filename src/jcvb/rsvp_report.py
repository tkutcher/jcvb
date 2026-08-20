"""RSVP roll-up for an Anvilor form — who's coming and how many.

Fetches the live responses via :mod:`jcvb.forms` and summarizes them:
one row per RSVP plus the totals worth knowing before an event (head
count, how many players are covered, who never responded).

Usage:
    uv run python -m jcvb.rsvp_report
    uv run python -m jcvb.rsvp_report --slug welcome-reception-rsvp-2026
    uv run python -m jcvb.rsvp_report --json

Response fields come from the published form: /respondent_name,
/player_name (optional — non-player guests leave it blank), /party_size
(total in party, including the player).

Auth is the same as jcvb.forms — ANVILOR_API_KEY + ANVILOR_ORG_OID in .env.
"""

import argparse
import json

from jcvb import forms

DEFAULT_SLUG = "welcome-reception-rsvp-2026"


# --- summarizing ---------------------------------------------------------------
# Pure functions over already-fetched response data, so the roll-up is testable
# without hitting the API.


def _clean(value) -> str:
    return str(value or "").strip()


def _player_key(name: str) -> str:
    """Normalize a player name so 'Will McDonald ' and 'will mcdonald' match."""
    return " ".join(name.split()).casefold()


def summarize(response_data: list[dict]) -> dict:
    """Roll up raw response_data dicts into rows + totals.

    An identical (respondent, player, party size) triple is a double-submit —
    someone hitting the button twice — never two real households, so those
    rows are collapsed before anything is counted. Two *different* respondents
    naming the same player is a judgement call, so those are kept and flagged.
    """
    rows = []
    for entry in response_data:
        rows.append(
            {
                "respondent_name": _clean(entry.get("respondent_name")),
                "player_name": _clean(entry.get("player_name")),
                "party_size": int(entry.get("party_size") or 0),
            }
        )
    rows.sort(key=lambda r: (r["player_name"].casefold(), r["respondent_name"].casefold()))

    # Drop exact double-submits, keeping the first of each identical triple.
    deduped: list[dict] = []
    exact_duplicates: list[dict] = []
    seen_rows: set[tuple] = set()
    for row in rows:
        key = (
            _player_key(row["respondent_name"]),
            _player_key(row["player_name"]),
            row["party_size"],
        )
        if key in seen_rows:
            exact_duplicates.append(row)
        else:
            seen_rows.add(key)
            deduped.append(row)
    rows = deduped

    # A player is "covered" once any RSVP names them. Two parents filing
    # separately would double-count a head count but not a player count.
    players: dict[str, str] = {}
    duplicates: list[str] = []
    for row in rows:
        if not row["player_name"]:
            continue
        key = _player_key(row["player_name"])
        if key in players:
            duplicates.append(row["player_name"])
        else:
            players[key] = row["player_name"]

    return {
        "rows": rows,
        "response_count": len(rows),
        "total_attending": sum(r["party_size"] for r in rows),
        "player_count": len(players),
        "players": sorted(players.values(), key=str.casefold),
        "duplicate_player_rsvps": duplicates,
        "exact_duplicates_removed": exact_duplicates,
        "responses_without_player": [
            r["respondent_name"] for r in rows if not r["player_name"]
        ],
    }


def format_report(summary: dict, slug: str) -> str:
    lines = [f"RSVP report — {slug}", ""]
    name_width = max(
        [len("Respondent")] + [len(r["respondent_name"]) for r in summary["rows"]] or [0]
    )
    player_width = max(
        [len("Player")] + [len(r["player_name"]) for r in summary["rows"]] or [0]
    )
    lines.append(f"{'Respondent':<{name_width}}  {'Player':<{player_width}}  Party")
    lines.append(f"{'-' * name_width}  {'-' * player_width}  -----")
    for row in summary["rows"]:
        player = row["player_name"] or "—"
        lines.append(
            f"{row['respondent_name']:<{name_width}}  {player:<{player_width}}  "
            f"{row['party_size']:>5}"
        )

    lines += [
        "",
        f"Responses:       {summary['response_count']}",
        f"Players covered: {summary['player_count']}",
        f"Total attending: {summary['total_attending']}",
    ]
    if summary["exact_duplicates_removed"]:
        collapsed = ", ".join(
            f"{r['respondent_name']} / {r['player_name'] or '\u2014'} ({r['party_size']})"
            for r in summary["exact_duplicates_removed"]
        )
        lines.append(
            f"\nCollapsed {len(summary['exact_duplicates_removed'])} exact "
            f"double-submit(s), not counted above: {collapsed}"
        )
    if summary["duplicate_player_rsvps"]:
        dupes = ", ".join(summary["duplicate_player_rsvps"])
        lines.append(
            f"\nNote: more than one RSVP names these players ({dupes}) — the head "
            "count may double-count that family."
        )
    if summary["responses_without_player"]:
        others = ", ".join(summary["responses_without_player"])
        lines.append(f"Not tied to a player: {others}")
    return "\n".join(lines)


# --- command ------------------------------------------------------------------


def fetch_summary(slug: str) -> dict:
    entry = forms.load_registry().get(slug)
    if not entry:
        raise SystemExit(f"{slug} is not published yet")
    docs = forms.fetch_responses(forms._auth_headers(), entry["form_oid"])
    return summarize(
        [(doc.get("response") or {}).get("response_data") or {} for doc in docs]
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="jcvb.rsvp_report", description=__doc__)
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="form slug to report on")
    parser.add_argument("--json", action="store_true", help="emit the summary as JSON")
    args = parser.parse_args(argv)

    summary = fetch_summary(args.slug)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_report(summary, args.slug))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
