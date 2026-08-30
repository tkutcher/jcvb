"""Official match stats, exported from Hudl Assist.

Hudl Assist returns the authoritative box score a day or two after a match:
every player's kills, attempts, aces, serve attempts and errors, serve-receive,
assists, digs and blocks. It is the source for anything that has to be exactly
right — the serving-status board, newsletter highlights, season averages.

**These files are internal.** They carry every player's error counts, so they
sit at the Coaches level (see jcvb/audience.py) and are read here to produce
highlights and aggregates — never copied to the site.

File naming, so a season of them stays sortable and machine-findable:

    <YYYY-MM-DD>--vs-<Opponent>-Hudl-<Scope>.csv
    2026-08-26--vs-Harford-Tech-Hudl-Match-Totals.csv

matching the scorebook and tally scans already in the game folder. `<Scope>` is
what the export covers — `Match-Totals`, `Set-1`, `Serve-Receive` — because Hudl
can export several cuts of the same match and its own filenames ("JCS vs HTHS —
All Athletes — Whole Match — Averages.csv") collide across a season and sort by
nothing useful.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

FILENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})--(?:vs|at)-(?P<opponent>.+?)-Hudl-(?P<scope>.+)\.csv$"
)

# Hudl pads the export with unnamed `0` spacer columns and writes "-" where a
# rate is undefined. A negative hitting percentage arrives as "- 0.333".
EMPTY = {"", "-", None}


def _num(value: str) -> float | None:
    if value is None:
        return None
    text = value.strip().replace("%", "")
    if text in EMPTY:
        return None
    text = text.replace("- ", "-")
    try:
        return float(text)
    except ValueError:
        return None


def _int(value: str) -> int:
    number = _num(value)
    return 0 if number is None else int(number)


@dataclass
class PlayerLine:
    number: str
    name: str
    sets_played: int
    kills: int
    attack_errors: int
    attack_attempts: int
    aces: int
    serve_errors: int
    serve_attempts: int
    serve_rating: float | None
    receptions: int
    reception_rating: float | None
    assists: int
    digs: int
    blocks: int
    identified: bool = True

    @property
    def serve_pct(self) -> float | None:
        """Serves in play over serves attempted — what the board calls S%."""
        if not self.serve_attempts:
            return None
        return (self.serve_attempts - self.serve_errors) / self.serve_attempts

    @property
    def hitting_pct(self) -> float | None:
        if not self.attack_attempts:
            return None
        return (self.kills - self.attack_errors) / self.attack_attempts

    @property
    def last_name(self) -> str:
        return self.name.split()[-1] if self.name else ""


@dataclass
class MatchStats:
    date: date
    opponent: str
    scope: str
    players: list[PlayerLine]
    path: Path | None = None

    def by_last_name(self) -> dict[str, PlayerLine]:
        return {p.last_name: p for p in self.players if p.identified}

    def totals(self) -> dict[str, int]:
        return {
            "kills": sum(p.kills for p in self.players),
            "aces": sum(p.aces for p in self.players),
            "serve_errors": sum(p.serve_errors for p in self.players),
            "serve_attempts": sum(p.serve_attempts for p in self.players),
            "attack_attempts": sum(p.attack_attempts for p in self.players),
            "attack_errors": sum(p.attack_errors for p in self.players),
            "assists": sum(p.assists for p in self.players),
            "digs": sum(p.digs for p in self.players),
            "blocks": sum(p.blocks for p in self.players),
        }

    def unidentified(self) -> list[PlayerLine]:
        """Rows Hudl could not match to an athlete — a jersey number with no
        name. They still count in the totals, so they are surfaced rather than
        dropped."""
        return [p for p in self.players if not p.identified]


def parse_match_csv(path: Path) -> MatchStats:
    match = FILENAME_RE.match(path.name)
    if not match:
        raise SystemExit(
            f"{path.name} is not a recognised stats export.\n"
            "Rename it <YYYY-MM-DD>--vs-<Opponent>-Hudl-<Scope>.csv"
        )
    rows = list(csv.reader(path.read_text(encoding="utf-8-sig").splitlines()))
    header_at = next(
        (i for i, row in enumerate(rows) if row and row[0].strip() == "#"), None
    )
    if header_at is None:
        raise SystemExit(f"{path.name}: no header row starting with '#'")

    header = [c.strip() for c in rows[header_at]]
    index = {name: i for i, name in enumerate(header) if name and name != "0"}

    def cell(row: list[str], key: str) -> str:
        position = index.get(key)
        return row[position] if position is not None and position < len(row) else ""

    players = []
    for row in rows[header_at + 1:]:
        if not row or not row[0].strip():
            continue
        raw_name = cell(row, "Athlete").strip()
        identified = not raw_name.lower().startswith("warning")
        name = re.sub(r"^warning", "", raw_name, flags=re.IGNORECASE).strip()
        players.append(
            PlayerLine(
                number=row[0].strip(),
                name=name,
                sets_played=_int(cell(row, "SP")),
                kills=_int(cell(row, "Kill")),
                attack_errors=_int(cell(row, "A Err")),
                attack_attempts=_int(cell(row, "Att")),
                aces=_int(cell(row, "Ace")),
                serve_errors=_int(cell(row, "S Err")),
                serve_attempts=_int(cell(row, "S Att")),
                serve_rating=_num(cell(row, "S Rtg")),
                receptions=_int(cell(row, "SR Att")),
                reception_rating=_num(cell(row, "SR Rtg")),
                assists=_int(cell(row, "Assist")),
                digs=_int(cell(row, "Digs")),
                blocks=_int(cell(row, "B Total")),
                identified=identified,
            )
        )

    return MatchStats(
        date=datetime.strptime(match.group("date"), "%Y-%m-%d").date(),
        opponent=match.group("opponent").replace("-", " "),
        scope=match.group("scope"),
        players=players,
        path=path,
    )


def find_match_files(root: Path) -> list[Path]:
    """Every Hudl export in the vault's game folders, oldest first."""
    if not root.exists():
        return []
    found = [
        path
        for folder in sorted(root.iterdir())
        if folder.is_dir()
        for path in sorted(folder.glob("*-Hudl-*.csv"))
        if FILENAME_RE.match(path.name)
    ]
    return sorted(found, key=lambda p: p.name)


def load_season(root: Path) -> list[MatchStats]:
    matches = [parse_match_csv(p) for p in find_match_files(root)]
    return sorted(matches, key=lambda m: m.date)


# --- serving aggregates --------------------------------------------------------


def serve_percentages(
    matches: list[MatchStats], trending_window: int = 5
) -> dict[str, dict]:
    """Season and trending S% per player.

    Season is every serve of the year over every attempt — one bad night in
    thirty serves should not read the same as one bad serve in three. Trending
    is the same calculation over the player's last `trending_window` matches,
    so it moves without a single match swamping it.
    """
    per_player: dict[str, list[PlayerLine]] = {}
    for match in sorted(matches, key=lambda m: m.date):
        for player in match.players:
            if not player.identified or not player.serve_attempts:
                continue
            per_player.setdefault(player.last_name, []).append(player)

    out = {}
    for last_name, lines in per_player.items():
        season_att = sum(p.serve_attempts for p in lines)
        season_err = sum(p.serve_errors for p in lines)
        recent = lines[-trending_window:]
        recent_att = sum(p.serve_attempts for p in recent)
        recent_err = sum(p.serve_errors for p in recent)
        out[last_name] = {
            "season_pct": (season_att - season_err) / season_att if season_att else None,
            "season_attempts": season_att,
            "season_aces": sum(p.aces for p in lines),
            "trending_pct": (
                (recent_att - recent_err) / recent_att if recent_att else None
            ),
            "trending_matches": len(recent),
            "matches": len(lines),
        }
    return out


def format_pct(value: float | None) -> str:
    return "" if value is None else f"{value * 100:.0f}%"


# --- the serving-status board --------------------------------------------------

VAULT_ROOT = Path.home() / "TK" / "tk-vault" / "orgs" / "JCVB"
SERVING_STATUS_PATH = VAULT_ROOT / "coach" / "notes" / "2026 JCVB Serving Status.md"
GAMES_ROOT = VAULT_ROOT / "coach" / "daily-plans"

# `| **Boyle** | 87% | 87% | 🟢 | …` — capture the name and the first two data
# cells, leave every later cell (the serve-type lights) exactly as written.
BOARD_ROW_RE = re.compile(
    r"^(?P<lead>\|\s*\*\*(?P<name>[^*]+)\*\*\s*\|)"
    r"(?P<season>[^|]*)\|(?P<trending>[^|]*)\|(?P<rest>.*)$"
)


def update_serving_status(
    text: str, stats: dict[str, dict], trending_window: int = 5
) -> tuple[str, list[str], list[str]]:
    """Fill the Season and Trending S% columns, touching nothing else.

    The lights are TK's coaching judgement, not something a stat sheet decides,
    so only the first two data cells are ever rewritten. Returns the new text,
    the players filled, and the board rows we had no serves for.
    """
    filled, skipped = [], []
    out = []
    for line in text.splitlines():
        match = BOARD_ROW_RE.match(line)
        if not match:
            out.append(line)
            continue
        name = match.group("name").strip()
        key = name.split(". ")[-1].strip()          # "L. Brown" -> "Brown"
        record = stats.get(key) or stats.get(name)
        if not record or record["season_pct"] is None:
            skipped.append(name)
            out.append(line)
            continue
        season = format_pct(record["season_pct"])
        trending = format_pct(record["trending_pct"])
        filled.append(f"{name} {season}/{trending}")
        width_season = len(match.group("season"))
        width_trending = len(match.group("trending"))
        out.append(
            f"{match.group('lead')}{season.center(width_season)}"
            f"|{trending.center(width_trending)}|{match.group('rest')}"
        )
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), filled, skipped


# --- internal highlights -------------------------------------------------------


def highlights(match: MatchStats, min_kills: int = 10) -> list[str]:
    """Newsletter-ready lines, drawn from the official box score.

    Positives only: this feeds public writing, and the same file carries every
    player's error counts, which do not.
    """
    lines = []
    for player in sorted(match.players, key=lambda p: -p.kills):
        if player.kills >= min_kills:
            lines.append(f"{player.name} — {player.kills} kills")
    for player in sorted(match.players, key=lambda p: -p.aces):
        if player.aces >= 3:
            lines.append(f"{player.name} — {player.aces} aces")
    for player in match.players:
        if player.assists >= 15:
            lines.append(f"{player.name} — {player.assists} assists")
        if player.digs >= 8:
            lines.append(f"{player.name} — {player.digs} digs")
    return lines


def render_stat_note(match: MatchStats) -> str:
    """The internal record of an official export: full box score, coaches only."""
    totals = match.totals()
    header = [
        "---",
        f"created: {match.date.isoformat()}",
        "aliases: []",
        "audience: coaches   # Coaches — All coaches",
        "cssclasses:",
        "  - jcvb-stats-note",
        "tags:",
        "  - jcvb-official-stats",
        "---",
        "",
        f"# {match.date.strftime('%-m/%-d/%y')} — Official stats vs {match.opponent}",
        "",
        "> [!warning] Internal — Coaches",
        "> Hudl Assist box score. Carries per-player error counts; only aces,",
        "> kills and blocks are ever published. Source:",
        f"> `{match.path.name if match.path else 'unknown'}`",
        "",
        "| # | Player | SP | K | Att | H% | Ace | SE | S Att | S% | SR | SR Rtg | Ast | Dig | Blk |",
        "| --- | --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |",
    ]
    rows = []
    for p in sorted(match.players, key=lambda x: (-x.kills, -x.aces, x.name)):
        hitting = f"{p.hitting_pct:.3f}" if p.hitting_pct is not None else "—"
        sr_rtg = f"{p.reception_rating:.2f}" if p.reception_rating is not None else "—"
        rows.append(
            f"| {p.number} | {p.name}{'' if p.identified else ' ⚠️'} | {p.sets_played} "
            f"| {p.kills} | {p.attack_attempts} | {hitting} | {p.aces} "
            f"| {p.serve_errors} | {p.serve_attempts} | {format_pct(p.serve_pct) or '—'} "
            f"| {p.receptions} | {sr_rtg} | {p.assists} | {p.digs} | {p.blocks} |"
        )
    team = [
        "",
        "## Team",
        "",
        f"- **{totals['kills']} kills** on {totals['attack_attempts']} attempts "
        f"({totals['attack_errors']} errors)",
        f"- **{totals['aces']} aces**, {totals['serve_errors']} service errors on "
        f"{totals['serve_attempts']} serves "
        f"({(totals['serve_attempts'] - totals['serve_errors']) / totals['serve_attempts'] * 100:.0f}% in play)",
        f"- {totals['assists']} assists · {totals['digs']} digs · {totals['blocks']} blocks",
    ]
    notes = []
    if match.unidentified():
        notes = [
            "",
            "## Needs attention",
            "",
        ] + [
            f"- Hudl did not identify **#{p.number}** — {p.serve_attempts} serves, "
            f"{p.digs} digs, {p.kills} kills recorded against an unnamed athlete. "
            "Fix the roster in Hudl so future exports name them."
            for p in match.unidentified()
        ]
    highlight_lines = ["", "## Highlights", ""] + [
        f"- {line}" for line in highlights(match)
    ]
    return "\n".join(header + rows + team + notes + highlight_lines) + "\n"


# --- cli -----------------------------------------------------------------------


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="jcvb.hudl", description="Official Hudl Assist stats (internal)."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="every stats export found in the vault")
    p = sub.add_parser("board", help="update the serving-status board")
    p.add_argument("--path", type=Path, default=SERVING_STATUS_PATH)
    p.add_argument("--window", type=int, default=5, help="matches in 'trending'")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("note", help="render the internal stats note for one match")
    p.add_argument("csv", type=Path)
    p.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    if args.command == "list":
        for match in load_season(GAMES_ROOT):
            totals = match.totals()
            print(
                f"{match.date}  vs {match.opponent:<16} {match.scope:<14} "
                f"{len(match.players):>2} players, {totals['kills']} kills, "
                f"{totals['aces']} aces"
            )
        return 0

    if args.command == "board":
        matches = load_season(GAMES_ROOT)
        stats = serve_percentages(matches, args.window)
        text = args.path.read_text(encoding="utf-8")
        updated, filled, skipped = update_serving_status(text, stats, args.window)
        if not args.dry_run:
            args.path.write_text(updated, encoding="utf-8")
        print(
            f"{'would fill' if args.dry_run else 'filled'} {len(filled)} row(s) "
            f"from {len(matches)} match(es), trending = last {args.window}"
        )
        for line in filled:
            print(f"  {line}")
        if skipped:
            print(f"  no serves on record: {', '.join(skipped)}")
        return 0

    if args.command == "note":
        match = parse_match_csv(args.csv)
        text = render_stat_note(match)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(text)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
