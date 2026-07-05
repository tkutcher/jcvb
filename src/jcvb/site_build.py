"""Static-site generator for the JCVB public website.

Renders pre-built HTML from Jinja2 templates + TOML data + Markdown newsletters
into ``site/public/`` (the deploy root). Run with::

    python -m jcvb.site_build

Design goals: zero external/runtime dependencies for the output (fonts and assets
are self-hosted), SEO-friendly pre-rendered pages, and a clean path toward later
auto-population from the vault.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageDraw, ImageFont, ImageOps

from jcvb._consts import REPO_ROOT

# --- Paths -------------------------------------------------------------------
SITE_DIR = REPO_ROOT / "site"
CONTENT_DIR = SITE_DIR / "content"
TEMPLATE_DIR = SITE_DIR / "templates"
STATIC_DIR = SITE_DIR / "static"
BRAND_DIR = SITE_DIR / "_assets" / "jcvb-brand"
PICS_DIR = SITE_DIR / "_assets" / "pics"
OUTPUT_DIR = REPO_ROOT / "build"
# Root the pages/assets are written under. When the site is served from a subpath
# (e.g. /jcvb), files live in build/<subpath>/ so local preview mirrors production.
OUT_ROOT = OUTPUT_DIR

# Brand font files copied into the output under /assets/fonts/ with web-safe names.
FONT_MAP = {
    "fonts/CreteRound/CreteRound-Regular.otf": "crete-round.otf",
    "fonts/FranklinGothic/ITCFranklinGothicStd-Book.otf": "franklin-book.otf",
    "fonts/FranklinGothic/ITCFranklinGothicStd-Med.otf": "franklin-med.otf",
    "fonts/FranklinGothic/ITCFranklinGothicStd-Demi.otf": "franklin-demi.otf",
    "fonts/QuaintGothic/Quaint Gothic SG OT Regular.ttf": "quaint-gothic.ttf",
}

# Team photos: source filename -> (web filename, max width px). Resized + recompressed
# at build time so we never ship 20 MP originals.
PHOTO_MAP = {
    "1dca1bf5-c40e-4a32-bca5-3e2660457898.jpg": ("huddle.jpg", 1600),
    "IMG_0252.JPG": ("celebration.jpg", 2200),
    "6b69716a-502a-4abb-93e8-a78e58ada1ca.jpg": ("action-set.jpg", 2200),
    "IMG_0190.JPG": ("celebrate-point.jpg", 1600),
    "8302aaea-e8d1-4eec-999d-e7a73fe0a5ce.jpg": ("net-attack.jpg", 1600),
    "IMG_3146.jpeg": ("team-line.jpg", 2200),
}
# Coach headshots -> web filename (square-ish thumbnails; framed via CSS object-position).
# tony.JPG is shot from behind, so it is intentionally excluded (monogram fallback in UI).
COACH_PHOTO_MAP = {
    "tim.JPG": ("tim.jpg", 800),
    "trent.JPG": ("trent.jpg", 800),
    "steven.JPG": ("steven.jpg", 800),
}

NEWSLETTER_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FIRST_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
LEADING_SYMBOLS_RE = re.compile(r"^[^\w(]+")
MD_STRIP_RE = re.compile(r"[*_`#>\[\]]|\!\[|\]\([^)]*\)")


# --- Data models -------------------------------------------------------------
@dataclass
class Newsletter:
    slug: str
    date: date
    headline: str          # human title (emoji stripped)
    eyebrow: str           # first bold line, emoji kept
    summary: str           # short plain-text excerpt
    html: str              # rendered body

    @property
    def date_long(self) -> str:
        return self.date.strftime("%B %-d, %Y")

    @property
    def date_short(self) -> str:
        return self.date.strftime("%b %-d")

    @property
    def weekday(self) -> str:
        return self.date.strftime("%A")

    @property
    def year(self) -> int:
        return self.date.year


@dataclass
class Game:
    date: date
    opponent: str
    designation: str
    home_away: str
    varsity: str
    jv: str
    venue: str
    note: str = ""

    @property
    def weekday(self) -> str:
        return self.date.strftime("%a")

    @property
    def date_display(self) -> str:
        return self.date.strftime("%b %-d")

    @property
    def month(self) -> str:
        return self.date.strftime("%B")

    @property
    def is_home(self) -> bool:
        return self.home_away == "home"

    @property
    def is_conference(self) -> bool:
        return self.designation == "conference"

    @property
    def ha_label(self) -> str:
        return {"home": "Home", "away": "Away", "tbd": "TBD"}.get(self.home_away, "")

    @property
    def designation_label(self) -> str:
        return {
            "conference": "Conference",
            "non-conference": "Non-Conference",
            "scrimmage": "Scrimmage",
            "playoffs": "Playoffs",
        }.get(self.designation, self.designation.title())

    @property
    def filter_tokens(self) -> str:
        """Space-separated tokens used by the client-side filter buttons."""
        toks = [self.designation, self.home_away]
        return " ".join(t for t in toks if t)


# --- Loaders -----------------------------------------------------------------
def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _plain_text(markdown_text: str) -> str:
    txt = MD_STRIP_RE.sub("", markdown_text)
    return re.sub(r"\s+", " ", txt).strip()


def load_newsletters() -> list[Newsletter]:
    items: list[Newsletter] = []
    md_render = md.Markdown(extensions=["extra", "sane_lists"])
    for path in sorted((CONTENT_DIR / "newsletters").glob("*.md")):
        m = NEWSLETTER_RE.match(path.name)
        if not m:
            continue
        d = date(int(m[1]), int(m[2]), int(m[3]))
        raw = path.read_text(encoding="utf-8")

        meta: dict[str, str] = {}
        fm = FRONT_MATTER_RE.match(raw)
        if fm:
            for line in fm[1].splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip("\"'")
            raw = raw[fm.end():]

        body = raw.strip()
        bold = FIRST_BOLD_RE.search(body)
        eyebrow = meta.get("headline") or (bold[1].strip() if bold else "Program Update")
        headline = LEADING_SYMBOLS_RE.sub("", eyebrow).strip() or "Program Update"

        # Summary: first list item's prose (after the bold headline), or file start.
        summary = meta.get("summary", "")
        if not summary:
            first_para = body.split("\n\n", 1)[0]
            first_para = FIRST_BOLD_RE.sub("", first_para, count=1)
            summary = _plain_text(first_para)
            summary = re.sub(r"^\s*\d+[.)]\s*", "", summary)  # drop list ordinal
            summary = summary.lstrip("-–—:•›* ").strip()
        if len(summary) > 180:
            summary = summary[:177].rsplit(" ", 1)[0] + "…"

        md_render.reset()
        html = md_render.convert(body)

        items.append(
            Newsletter(
                slug=d.isoformat(),
                date=d,
                headline=headline,
                eyebrow=eyebrow,
                summary=summary,
                html=html,
            )
        )
    items.sort(key=lambda n: n.date, reverse=True)
    return items


def load_schedule() -> tuple[dict, list[Game]]:
    data = _load_toml(CONTENT_DIR / "schedule" / "2026.toml")
    games = [
        Game(
            date=datetime.strptime(g["date"], "%Y-%m-%d").date(),
            opponent=g["opponent"],
            designation=g["designation"],
            home_away=g["home_away"],
            varsity=g.get("varsity", ""),
            jv=g.get("jv", ""),
            venue=g.get("venue", ""),
            note=g.get("note", ""),
        )
        for g in data["games"]
    ]
    games.sort(key=lambda g: g.date)
    return data.get("meta", {}), games


# --- Rendering ---------------------------------------------------------------
def build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def _write(rel_path: str, html: str) -> None:
    out = OUT_ROOT / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")


def _resize_jpeg(src: Path, dest: Path, max_w: int) -> None:
    """Downscale + recompress a photo for the web (honours EXIF orientation)."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width > max_w:
            h = round(im.height * max_w / im.width)
            im = im.resize((max_w, h), Image.Resampling.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=82, optimize=True, progressive=True)


def copy_assets() -> None:
    assets = OUT_ROOT / "assets"
    # css / js / img
    for sub in ("css", "js", "img"):
        src = STATIC_DIR / sub
        if src.exists():
            shutil.copytree(src, assets / sub, dirs_exist_ok=True)
    # self-hosted brand fonts (renamed web-safe)
    fonts_out = assets / "fonts"
    fonts_out.mkdir(parents=True, exist_ok=True)
    for src_rel, dest_name in FONT_MAP.items():
        src = BRAND_DIR / src_rel
        if src.exists():
            shutil.copy2(src, fonts_out / dest_name)
    # full brand kit for the brand page + downloads
    shutil.copytree(BRAND_DIR, assets / "brand", dirs_exist_ok=True)
    # optimized team photos + coach headshots
    for src_name, (dest_name, max_w) in PHOTO_MAP.items():
        src = PICS_DIR / src_name
        if src.exists():
            _resize_jpeg(src, assets / "pics" / dest_name, max_w)
    for src_name, (dest_name, max_w) in COACH_PHOTO_MAP.items():
        src = PICS_DIR / "coaches" / src_name
        if src.exists():
            _resize_jpeg(src, assets / "pics" / "coaches" / dest_name, max_w)


def render_og_image(dest: Path) -> None:
    """Compose the 1200x630 social-share (Open Graph) image on brand."""
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), (10, 2, 3))
    d = ImageDraw.Draw(im)
    # gold accent bar
    d.rectangle([0, 0, W, 10], fill=(196, 183, 129))
    # centered horizontal logo (icon + wordmark, white/gold on dark)
    logo_path = BRAND_DIR / "jcvb-logo-hz-on-dark.png"
    block_bottom = H // 2
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        lw = 760
        lh = round(logo.height * lw / logo.width)
        logo = logo.resize((lw, lh), Image.Resampling.LANCZOS)
        ly = (H - lh) // 2 - 34
        im.paste(logo, ((W - lw) // 2, ly), logo)
        block_bottom = ly + lh
    # tagline
    try:
        font = ImageFont.truetype(
            str(BRAND_DIR / "fonts" / "FranklinGothic" / "ITCFranklinGothicStd-Demi.otf"), 30)
    except Exception:
        font = ImageFont.load_default()
    tag = "2026 SEASON   ·   THE JOHN CARROLL SCHOOL   ·   MIAA"
    tw = d.textlength(tag, font=font)
    d.text(((W - tw) / 2, block_bottom + 34), tag, font=font, fill=(196, 183, 129))
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "PNG", optimize=True)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_schedule_svg(regular: list[Game], playoffs: list[Game], meta: dict) -> str:
    """A clean, print-ready 2026 schedule graphic on a WHITE background."""
    W, L, R = 850, 50, 800
    BLACK, GOLD, INK, MUT, LINE = "#0a0203", "#b9975b", "#141414", "#6b6b6b", "#e4e4e4"
    ff = "'Helvetica Neue', Arial, sans-serif"
    # column x-anchors
    cx = {"date": 50, "opp": 208, "site": 470, "jv": 592, "v": 694}
    rowh = 46

    p: list[str] = []
    p.append(
        f'<rect x="0" y="0" width="{W}" height="__H__" fill="#ffffff"/>'
        f'<rect x="0" y="0" width="{W}" height="10" fill="{GOLD}"/>'
    )
    # Header
    p.append(
        f'<text x="{L}" y="66" font-family="{ff}" font-size="34" font-weight="800" '
        f'letter-spacing="0.5" fill="{BLACK}">JOHN CARROLL VOLLEYBALL</text>'
        f'<text x="{L}" y="98" font-family="{ff}" font-size="20" font-weight="700" '
        f'letter-spacing="3" fill="{GOLD}">2026 SEASON SCHEDULE</text>'
        f'<text x="{L}" y="124" font-family="{ff}" font-size="12.5" fill="{MUT}">'
        f'The John Carroll School &#183; MIAA &#183; Home matches in the Upper Gym</text>'
    )
    y = 168
    # column headers
    hdr = [("DATE", cx["date"]), ("OPPONENT", cx["opp"]), ("SITE", cx["site"]),
           ("JV", cx["jv"]), ("VARSITY", cx["v"])]
    for label, x in hdr:
        p.append(f'<text x="{x}" y="{y}" font-family="{ff}" font-size="11.5" '
                 f'font-weight="700" letter-spacing="1.5" fill="{MUT}">{label}</text>')
    p.append(f'<rect x="{L}" y="{y+10}" width="{R-L}" height="2" fill="{BLACK}"/>')
    y += 22

    def row(g: Game, i: int) -> None:
        nonlocal y
        if i % 2 == 1:
            p.append(f'<rect x="{L}" y="{y}" width="{R-L}" height="{rowh}" fill="#faf8f3"/>')
        tag = "" if g.designation == "conference" else g.designation_label
        if g.note:
            tag = (tag + " · " + g.note).strip(" ·")
        ty = y + 25 if tag else y + 29
        p.append(f'<text x="{cx["date"]}" y="{ty}" font-family="{ff}" font-size="14.5" '
                 f'font-weight="700" fill="{INK}">{_esc(g.weekday)}, {_esc(g.date_display)}</text>')
        p.append(f'<text x="{cx["opp"]}" y="{ty}" font-family="{ff}" font-size="15.5" '
                 f'font-weight="600" fill="{INK}">{_esc(g.opponent)}</text>')
        if tag:
            p.append(f'<text x="{cx["opp"]}" y="{y+39}" font-family="{ff}" font-size="9.5" '
                     f'letter-spacing="0.8" fill="{MUT}">{_esc(tag.upper())}</text>')
        cy = y + rowh / 2  # vertical center for chips/times
        # site chip
        if g.home_away == "home":
            p.append(f'<rect x="{cx["site"]}" y="{cy-11}" width="60" height="22" rx="11" fill="{GOLD}"/>'
                     f'<text x="{cx["site"]+30}" y="{cy+4}" text-anchor="middle" font-family="{ff}" '
                     f'font-size="10.5" font-weight="800" letter-spacing="1" fill="{BLACK}">HOME</text>')
        elif g.home_away == "away":
            p.append(f'<rect x="{cx["site"]}" y="{cy-11}" width="60" height="22" rx="11" fill="none" stroke="{LINE}"/>'
                     f'<text x="{cx["site"]+30}" y="{cy+4}" text-anchor="middle" font-family="{ff}" '
                     f'font-size="10.5" font-weight="700" letter-spacing="1" fill="{MUT}">AWAY</text>')
        else:
            p.append(f'<text x="{cx["site"]}" y="{cy+5}" font-family="{ff}" font-size="12" fill="{MUT}">TBD</text>')
        p.append(f'<text x="{cx["jv"]}" y="{cy+5}" font-family="{ff}" font-size="14" fill="{INK}">'
                 f'{_esc(g.jv) if g.jv else "&#8212;"}</text>')
        p.append(f'<text x="{cx["v"]}" y="{cy+5}" font-family="{ff}" font-size="14" '
                 f'font-weight="700" fill="{INK}">{_esc(g.varsity) if g.varsity else "&#8212;"}</text>')
        p.append(f'<rect x="{L}" y="{y+rowh}" width="{R-L}" height="1" fill="{LINE}"/>')
        y += rowh

    for i, g in enumerate(regular):
        row(g, i)
    # Playoffs subhead
    y += 8
    p.append(f'<text x="{L}" y="{y+16}" font-family="{ff}" font-size="12" font-weight="800" '
             f'letter-spacing="2" fill="{GOLD}">MIAA PLAYOFFS</text>')
    y += 26
    for i, g in enumerate(playoffs):
        row(g, i)

    y += 26
    p.append(f'<text x="{L}" y="{y}" font-family="{ff}" font-size="11" fill="{MUT}">'
             f'{_esc(meta.get("status", ""))}</text>')
    p.append(f'<text x="{R}" y="{y}" text-anchor="end" font-family="{ff}" font-size="11" '
             f'font-weight="700" fill="{BLACK}">GO PATRIOTS</text>')
    H = y + 30
    body = "".join(p).replace("__H__", str(H))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}" font-family="{ff}">{body}</svg>')


def build() -> None:
    global OUT_ROOT
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    site = _load_toml(CONTENT_DIR / "site.toml")
    base = site["site"].get("base_path", "").rstrip("/")  # e.g. "/jcvb"
    OUT_ROOT = OUTPUT_DIR / base.strip("/") if base else OUTPUT_DIR
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    newsletters = load_newsletters()
    sched_meta, games = load_schedule()

    env = build_env()
    # Content-hash for cache-busting CSS/JS (also helps real deploys).
    h = hashlib.md5()
    for f in ("css/brand.css", "css/site.css", "js/motion.js"):
        fp = STATIC_DIR / f
        if fp.exists():
            h.update(fp.read_bytes())
    ver = h.hexdigest()[:8]
    ctx = {"site": site["site"], "links": site["links"], "cfg": site, "ver": ver, "base": base}

    # Home
    _write(
        "index.html",
        env.get_template("home.html.j2").render(
            page="home",
            latest=newsletters[:3],
            next_games=[g for g in games if g.designation != "playoffs"][:3],
            **ctx,
        ),
    )

    # Brand
    _write(
        "brand/index.html",
        env.get_template("brand.html.j2").render(page="brand", **ctx),
    )

    # Schedule
    _write(
        "schedule/index.html",
        env.get_template("schedule.html.j2").render(
            page="schedule",
            games=[g for g in games if g.designation != "playoffs"],
            playoffs=[g for g in games if g.designation == "playoffs"],
            meta=sched_meta,
            **ctx,
        ),
    )

    # Newsletters index + detail pages
    _write(
        "newsletters/index.html",
        env.get_template("newsletters_index.html.j2").render(
            page="newsletters", newsletters=newsletters, **ctx
        ),
    )
    detail_tpl = env.get_template("newsletter.html.j2")
    for i, n in enumerate(newsletters):
        newer = newsletters[i - 1] if i > 0 else None
        older = newsletters[i + 1] if i + 1 < len(newsletters) else None
        _write(
            f"newsletters/{n.slug}/index.html",
            detail_tpl.render(page="newsletters", n=n, newer=newer, older=older, **ctx),
        )

    copy_assets()

    # Printable, white-background schedule graphic (download).
    reg = [g for g in games if g.designation != "playoffs"]
    pos = [g for g in games if g.designation == "playoffs"]
    svg = render_schedule_svg(reg, pos, sched_meta)
    (OUT_ROOT / "assets" / "img").mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "assets" / "img" / "2026-JCVB-schedule.svg").write_text(svg, encoding="utf-8")

    # Social-share (Open Graph) image
    render_og_image(OUT_ROOT / "assets" / "img" / "og.png")

    print(f"Built {2 + 2 + len(newsletters)} pages -> {OUTPUT_DIR}")
    print(f"  newsletters: {len(newsletters)} | games: {len(games)}")


if __name__ == "__main__":
    build()
