#!/usr/bin/env python3
"""TOPREG site generator.

Fetches poker news RSS feeds and generates a fully static site in ./site.
Zero dependencies (Python 3 stdlib only).

Usage:
    python3 build.py                  # fetch live feeds and build
    python3 build.py --offline a.xml  # build from local XML files (testing)
"""
import json
import re
import sys
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "site"
UA = {"User-Agent": "Mozilla/5.0 (compatible; TOPREGBot/1.0; +https://www.topreg.it)"}

TOURNEY_RE = re.compile(
    r"\b(WSOP|EPT|WPT|Triton|GUKPT|Main Event|wins?|winner|champion|takes down|"
    r"final table|bracelet|title|victory|series)\b", re.I)

HENDON_RANKINGS = [
    ("All Time Money List", "https://pokerdb.thehendonmob.com/ranking/all-time-money-list/",
     "The definitive career earnings ranking - Kenney, Chidwick, Koon and the rest of the all-time greats."),
    ("2026 Money List", "https://pokerdb.thehendonmob.com/ranking/11059",
     "Who's winning the most live money this year, updated as results come in."),
    ("GPI World Ranking", "https://pokerdb.thehendonmob.com/ranking/gpi/",
     "The Global Poker Index: the most consistent tournament performers on the planet."),
    ("Most Cashes - All Time", "https://pokerdb.thehendonmob.com/ranking/450/",
     "The volume kings: most recorded live cashes in poker history."),
    ("Live Festival Calendar", "https://pokerdb.thehendonmob.com/festival.php?a=l",
     "Every upcoming festival worldwide, from the WSOP to local series."),
]

THM = "https://pokerdb.thehendonmob.com"
FALLBACK_FESTIVALS = [
    ("23 Jul - 2 Aug 2026", "England", "GUKPT Goliath by Grosvenor Poker", f"{THM}/festival.php?a=r&n=66587"),
    ("24 Jul - 4 Aug 2026", "Estonia", "WSOP International Circuit - WSOPC Estonia", f"{THM}/festival.php?a=r&n=68203"),
    ("31 Jul - 10 Aug 2026", "Slovakia", "WSOP International Circuit - WSOPC Samorin", f"{THM}/festival.php?a=r&n=68811"),
    ("3 - 9 Aug 2026", "Scotland", "The PartyPoker Tour - Glasgow", f"{THM}/festival.php?a=r&n=68353"),
    ("7 - 16 Aug 2026", "Cyprus", "Onyx High Roller Series", f"{THM}/festival.php?a=r&n=67215"),
    ("7 - 16 Aug 2026", "South Korea", "Asian Poker Tour - APT Incheon 2026", f"{THM}/festival.php?a=r&n=65973"),
    ("18 - 23 Aug 2026", "Liechtenstein", "The Hendon Mob Championship - THMC Liechtenstein", f"{THM}/festival.php?a=r&n=67975"),
    ("19 - 31 Aug 2026", "Taiwan", "2026 Players Series Championship IV Taipei", f"{THM}/festival.php?a=r&n=70343"),
    ("31 Aug - 14 Sep 2026", "Australia", "Irish Open International - Sydney", f"{THM}/festival.php?a=r&n=69057"),
    ("14 - 20 Sep 2026", "Malta", "The Festival in Malta", f"{THM}/festival.php?a=r&n=66717"),
    ("25 Sep - 7 Oct 2026", "South Korea", "Asian Poker Tour - APT Jeju 2026", f"{THM}/festival.php?a=r&n=65975"),
]

DATE_RE = re.compile(r"\b(\d{1,2}(?:\s+\w{3,9})?\s*[-–]\s*\d{1,2}\s+\w{3,9}\s+20\d\d)\b")
FEST_LINK_RE = re.compile(r'href="(https?://pokerdb\.thehendonmob\.com/festival\.php\?a=r&(?:amp;)?n=\d+)"[^>]*>([^<]{6,120})</a>')


def fetch_festivals():
    """Parse upcoming festivals from The Hendon Mob homepage; fall back to a
    curated list if the page layout changes."""
    raw = fetch("https://www.thehendonmob.com/")
    fests = []
    if raw:
        html_text = raw.decode("utf-8", "ignore")
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S):
            dm = DATE_RE.search(row)
            lm = FEST_LINK_RE.search(row)
            if not (dm and lm):
                continue
            country_m = re.search(r"<td[^>]*>\s*(?:<[^>]+>\s*)*([A-Z][A-Za-z .]{3,25})\s*<", row)
            country = country_m.group(1).strip() if country_m else ""
            name = html.unescape(lm.group(2)).strip()
            if name and not any(name == f[2] for f in fests):
                fests.append((dm.group(1), country, name, lm.group(1).replace("&amp;", "&")))
    if len(fests) < 4:
        print("  [warn] festival parse fallback in use", file=sys.stderr)
        fests = FALLBACK_FESTIVALS
    return fests[:12]


MONEY_RE = re.compile(r"\$\s?([\d,]{4,})")


def find_spotlight(items):
    """Pick the biggest money score mentioned in recent headlines."""
    best, best_amt = None, 0
    for it in items:
        for m in MONEY_RE.finditer(it["title"]):
            amt = int(m.group(1).replace(",", ""))
            if amt > best_amt:
                best, best_amt = it, amt
    return best, best_amt


DESTINATIONS = [
    {
        "slug": "las-vegas", "name": "Las Vegas, USA", "tags": "WSOP · Wynn Classic · DeepStack",
        "blurb": "Home of the WSOP every summer. Bellagio, Aria and Wynn run the biggest cash games and daily tournaments on the planet.",
        "intro": "There is no place like it. From late May to mid-July the World Series of Poker takes over the Horseshoe and Paris, and the entire city becomes one giant poker festival: every major room runs its own summer series at the same time, cash games run around the clock, and the player pool is the softest it will be all year.",
        "venues": [
            ("Horseshoe & Paris Las Vegas", "Home of the WSOP: 100+ bracelet events across the summer."),
            ("Wynn Poker Room", "The premier non-WSOP room. Wynn Summer and Fall Classics with multi-million guarantees."),
            ("Bellagio", "Bobby's Room legacy, Five Diamond in December, deep cash lineup year-round."),
            ("Aria", "High-stakes cash, daily $240-$600 tournaments, PokerGO studio next door."),
            ("Venetian", "DeepStack Extravaganza series virtually all year."),
            ("Resorts World & Orleans", "Big summer series with softer fields and lower buy-ins."),
        ],
        "when": "Peak season is the WSOP window (late May - mid July). December's Five Diamond at Bellagio is the winter highlight. Cash games are good every single day of the year.",
        "tips": "Book accommodation months ahead for the WSOP - prices triple. The 1/3 and 2/5 NL games are beatable everywhere; tournament fields at Orleans and Resorts World are notably softer than the Strip average.",
        "links": [
            ("WSOP 2026 results on The Hendon Mob", "https://pokerdb.thehendonmob.com/festival.php?a=r&n=66671"),
            ("Wynn Poker calendar", "https://www.wynnlasvegas.com/casino/poker"),
        ],
    },
    {
        "slug": "barcelona", "name": "Barcelona, Spain", "tags": "EPT Barcelona",
        "blurb": "EPT Barcelona at Casino Barcelona is Europe's largest annual festival, with huge side events and beach-side cash games.",
        "intro": "Every August the poker world moves to the Catalan coast. EPT Barcelona is consistently the biggest EPT stop of the year - thousands of entries in the Main Event, a Super High Roller with the game's elite, and cash games that run 24/7 for three straight weeks, all a few metres from the beach.",
        "venues": [
            ("Casino Barcelona", "Port Olimpic. Host of EPT Barcelona and year-round tournaments; passport required at the door."),
        ],
        "when": "August for the EPT festival (roughly three weeks including pre-events). The casino runs good regular tournaments and cash games the rest of the year, with a strong PLO scene.",
        "tips": "Bring your passport - it is legally required for casino entry in Spain. Book early for August: the Hotel Arts and beachfront options sell out fast. Side events from 550 euro offer great value against soft international fields.",
        "links": [
            ("EPT Barcelona on PokerStars Live", "https://www.pokerstarslive.com/ept/"),
            ("Festival results on The Hendon Mob", "https://pokerdb.thehendonmob.com/festival.php?a=l"),
        ],
    },
    {
        "slug": "london", "name": "London, UK", "tags": "GUKPT · Triton · The Vic",
        "blurb": "The Hippodrome and Aspers anchor a deep year-round scene, plus GUKPT stops and Triton London super high rollers.",
        "intro": "London has the deepest year-round poker ecosystem in Europe: three major rooms within the city, a historic tour (GUKPT), regular visits from Triton's super high roller circus, and a cash scene that never really stops.",
        "venues": [
            ("The Hippodrome (PokerStars Live)", "Leicester Square landmark with daily tournaments and cash."),
            ("Grosvenor Victoria - 'The Vic'", "The most storied card room in the UK, GUKPT flagship stop."),
            ("Aspers Stratford", "Biggest casino floor in the UK, strong mid-stakes tournaments."),
        ],
        "when": "Year-round. GUKPT visits multiple times a season (the Goliath in Coventry, its sister event, is the largest tournament in Europe by entries); Triton has made London a recurring super high roller stop.",
        "tips": "UK casinos require registration but membership is instant with ID. London cash games run deep - 1/2 plays more like 2/5 elsewhere. The PartyPoker Tour and Hendon Mob Championship also make regular UK stops.",
        "links": [
            ("GUKPT results on The Hendon Mob", "https://pokerdb.thehendonmob.com/circuit.php?a=e&n=GUKPT"),
            ("The Hippodrome poker schedule", "https://www.hippodromecasino.com/poker/"),
        ],
    },
    {
        "slug": "monte-carlo", "name": "Monte Carlo, Monaco", "tags": "EPT Monte Carlo",
        "blurb": "The EPT Grand Final's historic home. Glamour, high rollers and the Casino de Monte-Carlo.",
        "intro": "Poker's most glamorous address. The EPT's spring stop at the Monte-Carlo Bay Hotel brings the game's biggest names to the principality every April-May, with a Super High Roller schedule that regularly features seven-figure first prizes.",
        "venues": [
            ("Monte-Carlo Bay Hotel & Resort", "EPT festival home - tournament floor with a Mediterranean view."),
            ("Casino de Monte-Carlo", "The legendary Belle Epoque casino itself; jacket recommended."),
        ],
        "when": "Late April to early May for the EPT Monte Carlo festival. Outside festival dates the poker offering is limited - this is a festival destination, not a year-round grind stop.",
        "tips": "Stay in Beausoleil (France side) for a fraction of Monaco hotel prices - it is a 10-minute walk. Dress codes are enforced in the main casino. Qualifying online via PokerStars satellites is the classic budget route in.",
        "links": [
            ("EPT Monte Carlo on PokerStars Live", "https://www.pokerstarslive.com/ept/"),
            ("Festival results on The Hendon Mob", "https://pokerdb.thehendonmob.com/festival.php?a=l"),
        ],
    },
    {
        "slug": "bahamas", "name": "Paradise Island, Bahamas", "tags": "PSPC · PCA",
        "blurb": "PokerStars' flagship winter festival brings thousands of players to Atlantis every January.",
        "intro": "The PCA built the destination-poker template: fly somewhere warm in the dead of winter, play a world-class festival, and spend the breaks on a beach. The January festival at Atlantis remains one of the great annual gatherings of the poker calendar.",
        "venues": [
            ("Atlantis Paradise Island", "Festival host resort - tournament rooms, water park, casino floor."),
        ],
        "when": "January, for the PCA/PSPC window. Combine with US winter stops if you are touring.",
        "tips": "Book the festival package early - Atlantis rates spike hard. Satellites run online for months beforehand and are by far the cheapest way in. Bring US dollars: they are accepted everywhere at par.",
        "links": [
            ("PokerStars Live - Bahamas", "https://www.pokerstarslive.com/"),
            ("Festival results on The Hendon Mob", "https://pokerdb.thehendonmob.com/festival.php?a=l"),
        ],
    },
    {
        "slug": "cyprus", "name": "Northern Cyprus", "tags": "Triton · Merit Series · Onyx HRS",
        "blurb": "Merit casinos host Triton and Mediterranean poker festivals with some of the softest high-stakes fields anywhere.",
        "intro": "Northern Cyprus has quietly become one of the most important stops on the international calendar. The Merit group's resorts in Kyrenia host Triton Series stops, the Merit Poker Classic and Gala series, and the Onyx High Roller Series - with high-stakes cash games that regulars describe as among the best value in the world.",
        "venues": [
            ("Merit Royal Diamond, Kyrenia", "Flagship resort - Triton and Merit series host."),
            ("Merit Crystal Cove", "Sister property with festival overflow and strong cash games."),
        ],
        "when": "Multiple festival windows a year - Merit series in spring and autumn, Onyx HRS in August, Triton stops announced season by season.",
        "tips": "Fly via Istanbul to Ercan (ECN) - it is the practical route in. Festivals are all-inclusive resort affairs; cash games run big and soft during series weeks. Bring patience for registration queues at peak events.",
        "links": [
            ("Onyx HRS results on The Hendon Mob", "https://pokerdb.thehendonmob.com/festival.php?a=r&n=67215"),
            ("Merit Poker", "https://www.meritpoker.com/"),
        ],
    },
]


def fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=20) as r:
            return r.read()
    except Exception as e:
        print(f"  [warn] {url}: {e}", file=sys.stderr)
        return None


def text_of(el, tag):
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def parse_feed(raw: bytes, source: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"  [warn] parse error {source}: {e}", file=sys.stderr)
        return items
    for it in root.iter("item"):
        title = html.unescape(text_of(it, "title"))
        link = text_of(it, "link").split("?utm_")[0]
        desc = text_of(it, "description")
        img = None
        m = re.search(r'<img[^>]+src="([^"]+)"', desc)
        if m:
            img = m.group(1)
        excerpt = html.unescape(re.sub(r"<[^>]+>", " ", desc)).strip()
        excerpt = re.sub(r"\s+", " ", excerpt)[:180]
        try:
            dt = parsedate_to_datetime(text_of(it, "pubDate"))
        except Exception:
            dt = datetime.now(timezone.utc)
        if title and link:
            items.append({"title": title, "link": link, "img": img,
                          "excerpt": excerpt, "date": dt, "source": source})
    return items


def collect(config, offline_files):
    all_items = []
    if offline_files:
        for f in offline_files:
            all_items += parse_feed(Path(f).read_bytes(), Path(f).stem)
    else:
        for url in config["feeds"]:
            print(f"fetching {url}")
            raw = fetch(url)
            if raw:
                all_items += parse_feed(raw, re.sub(r"^www\.", "", url.split("/")[2]))
    seen, unique = set(), []
    for it in sorted(all_items, key=lambda x: x["date"], reverse=True):
        key = it["title"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(it)
    return unique


def esc(s):
    return html.escape(s, quote=True)


def news_card(it):
    img = (f'<img src="{esc(it["img"])}" alt="" loading="lazy">' if it["img"]
           else '<div class="noimg">&#9824;</div>')
    return f'''<a class="card" href="{esc(it["link"])}" target="_blank" rel="noopener nofollow">
      <div class="thumb">{img}</div>
      <div class="cbody">
        <span class="meta">{it["date"].strftime("%b %d, %Y")} &middot; {esc(it["source"])}</span>
        <h3>{esc(it["title"])}</h3>
        <p>{esc(it["excerpt"])}</p>
      </div></a>'''


def result_row(it):
    return f'''<a class="row" href="{esc(it["link"])}" target="_blank" rel="noopener nofollow">
      <span class="rdate">{it["date"].strftime("%b %d")}</span>
      <span class="rtitle">{esc(it["title"])}</span></a>'''


def banner(a):
    return f'''<a class="banner" href="{esc(a["url"])}" target="_blank" rel="noopener sponsored">
      <div class="bname">{esc(a["name"])}</div>
      <div class="btag">{esc(a["tagline"])}</div>
      <div class="bbadge">{esc(a["badge"])}</div>
      <div class="bcta">{esc(a["cta"])} &rarr;</div></a>'''


def festival_row(date, country, name, url):
    return f'''<a class="row" href="{esc(url)}" target="_blank" rel="noopener">
      <span class="rdate">{esc(date)}</span>
      <span class="rtitle"><strong>{esc(name)}</strong>{" &mdash; " + esc(country) if country else ""}</span></a>'''


def compare_row(a):
    return f'''<tr>
      <td class="cmp-name"><a href="{esc(a["url"])}" target="_blank" rel="noopener sponsored">{esc(a["name"])}</a><span class="cmp-net">{esc(a.get("network", ""))}</span></td>
      <td>{esc(a.get("rating", "-"))} &#9733;</td>
      <td>{esc(a["badge"])}</td>
      <td>{esc(a.get("rakeback", "-"))}</td>
      <td><a class="cmp-cta" href="{esc(a["url"])}" target="_blank" rel="noopener sponsored">{esc(a["cta"])}</a></td></tr>'''


def spotlight_html(item, amount):
    if not item:
        return ""
    return f'''<a class="spotlight" href="{esc(item["link"])}" target="_blank" rel="noopener nofollow">
      <span class="spot-label">&#127942; Score of the Day</span>
      <span class="spot-title">{esc(item["title"])}</span>
      <span class="spot-amt">${amount:,}</span></a>'''


def dest_card(d):
    return f'''<a class="dest" href="play/{d["slug"]}.html"><h3>{esc(d["name"])}</h3><p>{esc(d["blurb"])}</p>
      <span class="dtags">{esc(d["tags"])}</span><span class="dmore">Read the full guide &rarr;</span></a>'''


def ranking_row(name, url, desc):
    return f'''<a class="row" href="{esc(url)}" target="_blank" rel="noopener">
      <span class="rdate">&#9819;</span>
      <span class="rtitle"><strong>{esc(name)}</strong> &mdash; {esc(desc)}</span></a>'''


def dest_page(d, updated, year):
    venues = "\n".join(
        f'<div class="dest"><h3>{esc(n)}</h3><p>{esc(t)}</p></div>' for n, t in d["venues"])
    links = "\n".join(
        f'<a class="row" href="{esc(u)}" target="_blank" rel="noopener"><span class="rdate">&rarr;</span><span class="rtitle">{esc(n)}</span></a>'
        for n, u in d["links"])
    return DEST_TEMPLATE \
        .replace("{{NAME}}", esc(d["name"])) \
        .replace("{{TAGS}}", esc(d["tags"])) \
        .replace("{{INTRO}}", esc(d["intro"])) \
        .replace("{{VENUES}}", venues) \
        .replace("{{WHEN}}", esc(d["when"])) \
        .replace("{{TIPS}}", esc(d["tips"])) \
        .replace("{{LINKS}}", links) \
        .replace("{{UPDATED}}", updated) \
        .replace("{{YEAR}}", year)


def build(config, items, offline=False):
    tourney = [i for i in items if TOURNEY_RE.search(i["title"])][:8]
    tourney_keys = {t["title"] for t in tourney}
    news = [i for i in items if i["title"] not in tourney_keys][:config["max_news"]]
    if len(news) < 6:
        news = items[:config["max_news"]]
    updated = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    year = str(datetime.now().year)
    mail = config["sponsor_email"]
    festivals = FALLBACK_FESTIVALS if offline else fetch_festivals()
    spot_item, spot_amt = find_spotlight(items)

    page = TEMPLATE
    page = page.replace("{{SPOTLIGHT}}", spotlight_html(spot_item, spot_amt))
    page = page.replace("{{FESTIVALS}}", "\n".join(festival_row(*f) for f in festivals))
    page = page.replace("{{COMPARE}}", "\n".join(compare_row(a) for a in config["affiliates"]))
    page = page.replace("{{TAGLINE}}", esc(config["tagline"]))
    page = page.replace("{{UPDATED}}", updated)
    page = page.replace("{{YEAR}}", year)
    page = page.replace("{{BANNERS}}", "\n".join(banner(a) for a in config["affiliates"]))
    page = page.replace("{{NEWS}}", "\n".join(news_card(i) for i in news))
    page = page.replace("{{RESULTS}}", "\n".join(result_row(i) for i in tourney))
    page = page.replace("{{DESTS}}", "\n".join(dest_card(d) for d in DESTINATIONS))
    page = page.replace("{{RANKINGS}}", "\n".join(ranking_row(*r) for r in HENDON_RANKINGS))
    page = page.replace("{{MAIL}}", esc(mail))

    SITE.mkdir(exist_ok=True)
    (SITE / "play").mkdir(exist_ok=True)
    (SITE / "index.html").write_text(page, encoding="utf-8")
    for d in DESTINATIONS:
        (SITE / "play" / f"{d['slug']}.html").write_text(
            dest_page(d, updated, year), encoding="utf-8")
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (SITE / "CNAME").write_text(config["domain"] + "\n", encoding="utf-8")
    print(f"built site: {len(news)} news, {len(tourney)} results, {len(DESTINATIONS)} destination pages")


CSS = """
:root{--felt:#0d3b2e;--felt2:#0a2e24;--gold:#d4af37;--ink:#e8e6df;--mut:#9aa89f;--card:#12463a;--red:#c0392b}
*{margin:0;box-sizing:border-box}
body{font-family:Georgia,'Times New Roman',serif;background:var(--felt2);color:var(--ink)}
a{color:inherit;text-decoration:none}
.wrap{max-width:1100px;margin:0 auto;padding:0 20px}
header{background:linear-gradient(180deg,#071f18,var(--felt2));border-bottom:2px solid var(--gold);padding:26px 0 18px}
.logo{font-size:2.6rem;letter-spacing:.35em;font-weight:700;color:var(--gold)}
.logo span{color:var(--ink)}
.logo a{color:inherit}
.tag{color:var(--mut);font-style:italic;margin-top:4px}
nav{margin-top:14px;display:flex;gap:22px;flex-wrap:wrap;font-family:Helvetica,Arial,sans-serif;font-size:.8rem;letter-spacing:.15em;text-transform:uppercase}
nav a{color:var(--mut)} nav a:hover{color:var(--gold)}
.updated{font-family:Helvetica,Arial,sans-serif;font-size:.7rem;color:var(--mut);margin-top:10px}
h2{font-size:1.5rem;color:var(--gold);border-bottom:1px solid #1d5a49;padding-bottom:8px;margin:44px 0 20px;letter-spacing:.08em}
.banners{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px;margin-top:22px}
.banner{background:linear-gradient(135deg,var(--card),#0e3a2f);border:1px solid var(--gold);border-radius:10px;padding:18px;transition:.2s;position:relative}
.banner:hover{transform:translateY(-3px);box-shadow:0 8px 24px rgba(0,0,0,.45)}
.bname{font-size:1.25rem;font-weight:700;color:var(--gold)}
.btag{color:var(--mut);font-size:.85rem;margin:6px 0 10px}
.bbadge{display:inline-block;background:var(--red);color:#fff;font-family:Helvetica,Arial,sans-serif;font-size:.7rem;padding:4px 10px;border-radius:20px;letter-spacing:.05em}
.bcta{margin-top:12px;font-family:Helvetica,Arial,sans-serif;font-size:.8rem;color:var(--ink);letter-spacing:.1em;text-transform:uppercase}
.ad-note{font-family:Helvetica,Arial,sans-serif;font-size:.65rem;color:var(--mut);margin-top:8px;text-transform:uppercase;letter-spacing:.1em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px}
.card{background:var(--card);border-radius:10px;overflow:hidden;border:1px solid #1d5a49;transition:.2s;display:flex;flex-direction:column}
.card:hover{transform:translateY(-3px);border-color:var(--gold)}
.thumb{height:170px;background:#0a2e24;overflow:hidden}
.thumb img{width:100%;height:100%;object-fit:cover}
.noimg{display:flex;align-items:center;justify-content:center;height:100%;font-size:3rem;color:#1d5a49}
.cbody{padding:16px}
.meta{font-family:Helvetica,Arial,sans-serif;font-size:.68rem;color:var(--mut);text-transform:uppercase;letter-spacing:.1em}
.card h3{font-size:1.05rem;margin:8px 0;line-height:1.35}
.card p{color:var(--mut);font-size:.88rem;line-height:1.5}
.rows{background:var(--card);border:1px solid #1d5a49;border-radius:10px;overflow:hidden}
.row{display:flex;gap:16px;padding:13px 18px;border-bottom:1px solid #1d5a49;align-items:baseline}
.row:last-child{border-bottom:none}
.row:hover{background:#175243}
.rdate{font-family:Helvetica,Arial,sans-serif;font-size:.7rem;color:var(--gold);min-width:52px;letter-spacing:.05em}
.rtitle{font-size:.95rem}
.dests{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px}
.dest{background:var(--card);border:1px solid #1d5a49;border-radius:10px;padding:20px;transition:.2s;display:block}
a.dest:hover{transform:translateY(-3px);border-color:var(--gold)}
.dest h3{color:var(--gold);margin-bottom:8px}
.dest p{color:var(--mut);font-size:.9rem;line-height:1.55}
.dtags{display:inline-block;margin-top:12px;font-family:Helvetica,Arial,sans-serif;font-size:.68rem;color:var(--ink);background:#0a2e24;padding:4px 10px;border-radius:20px;letter-spacing:.08em}
.dmore{display:block;margin-top:12px;font-family:Helvetica,Arial,sans-serif;font-size:.72rem;color:var(--gold);letter-spacing:.1em;text-transform:uppercase}
.spotlight{display:flex;align-items:center;gap:18px;flex-wrap:wrap;background:linear-gradient(90deg,#2b1f08,#12463a);border:1px solid var(--gold);border-radius:10px;padding:16px 22px;margin-top:22px;transition:.2s}
.spotlight:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.45)}
.spot-label{font-family:Helvetica,Arial,sans-serif;font-size:.7rem;letter-spacing:.15em;text-transform:uppercase;color:var(--gold);white-space:nowrap}
.spot-title{flex:1;font-size:1.02rem;min-width:200px}
.spot-amt{font-family:Helvetica,Arial,sans-serif;font-weight:700;font-size:1.3rem;color:var(--gold)}
.cmp{width:100%;border-collapse:collapse;background:var(--card);border:1px solid #1d5a49;border-radius:10px;overflow:hidden;font-size:.9rem}
.cmp th{font-family:Helvetica,Arial,sans-serif;font-size:.68rem;letter-spacing:.12em;text-transform:uppercase;color:var(--mut);text-align:left;padding:12px 14px;border-bottom:1px solid #1d5a49}
.cmp td{padding:13px 14px;border-bottom:1px solid #1d5a49;color:var(--ink)}
.cmp tr:last-child td{border-bottom:none}
.cmp tr:hover td{background:#175243}
.cmp-name a{color:var(--gold);font-weight:700}
.cmp-net{display:block;font-family:Helvetica,Arial,sans-serif;font-size:.68rem;color:var(--mut)}
.cmp-cta{display:inline-block;background:var(--gold);color:#111;font-family:Helvetica,Arial,sans-serif;font-weight:700;font-size:.68rem;letter-spacing:.08em;text-transform:uppercase;padding:7px 14px;border-radius:5px}
.cmp-wrap{overflow-x:auto;margin-top:18px}
.partner{background:linear-gradient(135deg,#1a1204,#2b1f08);border:1px solid var(--gold);border-radius:10px;padding:34px;text-align:center;margin-top:44px}
.partner h2{border:none;margin:0 0 10px}
.partner p{color:var(--mut);max-width:600px;margin:0 auto 18px;line-height:1.6}
.pbtn{display:inline-block;background:var(--gold);color:#111;font-family:Helvetica,Arial,sans-serif;font-weight:700;font-size:.8rem;letter-spacing:.12em;text-transform:uppercase;padding:13px 30px;border-radius:6px}
.lede{font-size:1.1rem;line-height:1.7;color:var(--ink);max-width:800px;margin-top:24px}
.body-text{color:var(--mut);line-height:1.7;max-width:800px;margin-top:12px}
.back{font-family:Helvetica,Arial,sans-serif;font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;color:var(--gold)}
footer{margin-top:60px;border-top:1px solid #1d5a49;padding:30px 0 40px;font-family:Helvetica,Arial,sans-serif;font-size:.72rem;color:var(--mut);line-height:1.7}
footer strong{color:var(--ink)}
.age{display:inline-block;border:2px solid var(--red);color:var(--red);border-radius:50%;width:38px;height:38px;line-height:34px;text-align:center;font-weight:700;margin-right:10px;font-size:.85rem}
"""

FOOTER = """<footer><div class="wrap">
  <p><span class="age">18+</span><strong>Play responsibly.</strong> Gambling can be addictive. If you or someone you know has a gambling problem, seek help: <a href="https://www.begambleaware.org" rel="noopener">BeGambleAware.org</a>.</p>
  <p style="margin-top:12px"><strong>Affiliate disclosure:</strong> TOPREG contains affiliate links and advertising. We may receive compensation when you click links or sign up through this site. This does not affect our editorial content, which links to and credits original sources.</p>
  <p style="margin-top:12px">This website is intended exclusively for visitors located in jurisdictions where online poker and related advertising are legal. It is <strong>not directed at residents of Italy</strong> or any jurisdiction where gambling advertising is prohibited. Nothing on this site constitutes an invitation to gamble where unlawful. News headlines and excerpts are aggregated from and credited to their original publishers. Rankings data courtesy of <a href="https://www.thehendonmob.com" rel="noopener">The Hendon Mob</a>.</p>
  <p style="margin-top:12px">&copy; {{YEAR}} TOPREG.it &mdash; All rights reserved.</p>
</div></footer>"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TOPREG &mdash; Poker News, Tournaments &amp; Where to Play</title>
<meta name="description" content="TOPREG: daily poker news, tournament results, live poker destinations, Hendon Mob rankings and the best rooms to play online. Built for regs, by regs.">
<style>""" + CSS + """</style>
</head>
<body>
<header><div class="wrap">
  <div class="logo">TOP<span>REG</span></div>
  <div class="tag">{{TAGLINE}}</div>
  <nav><a href="#news">News</a><a href="#results">Tournament Results</a><a href="#calendar">Calendar</a><a href="#play">Where to Play</a><a href="#rankings">Rankings</a><a href="#rooms">Best Rooms</a><a href="#partner">Advertise</a></nav>
  <div class="updated">Auto-updated: {{UPDATED}}</div>
</div></header>

<div class="wrap">
  <section id="rooms">
    <div class="banners">{{BANNERS}}</div>
    <div class="cmp-wrap"><table class="cmp">
      <tr><th>Poker Room</th><th>Rating</th><th>Welcome Bonus</th><th>Rakeback</th><th></th></tr>
      {{COMPARE}}
    </table></div>
    <div class="ad-note">Advertisement &mdash; TOPREG may earn a commission from partner links. 18+ only. Play responsibly. Terms apply on all offers.</div>
    {{SPOTLIGHT}}
  </section>

  <section id="news"><h2>&#9824; Latest Poker News</h2>
    <div class="grid">{{NEWS}}</div>
  </section>

  <section id="results"><h2>&#127942; Tournament Results &amp; Winners</h2>
    <div class="rows">{{RESULTS}}</div>
  </section>

  <section id="calendar"><h2>&#128197; Upcoming Live Festivals</h2>
    <div class="rows">{{FESTIVALS}}</div>
    <div class="ad-note" style="text-transform:none">Schedule data refreshed automatically. Full details on The Hendon Mob.</div>
  </section>

  <section id="play"><h2>&#9992; Where to Play Live</h2>
    <div class="dests">{{DESTS}}</div>
  </section>

  <section id="rankings"><h2>&#9819; Player Rankings</h2>
    <div class="rows">{{RANKINGS}}</div>
    <div class="ad-note" style="text-transform:none">Rankings hosted by The Hendon Mob, the largest live poker database.</div>
  </section>

  <section class="partner" id="partner">
    <h2>Advertise on TOPREG</h2>
    <p>Reach a dedicated audience of poker regulars, grinders and travelling players. Banner placements, sponsored slots and featured room listings available.</p>
    <a class="pbtn" href="mailto:{{MAIL}}?subject=Advertising%20on%20TOPREG">Get in touch</a>
  </section>
</div>
""" + FOOTER + """
</body>
</html>
"""

DEST_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{NAME}} &mdash; Where to Play | TOPREG</title>
<meta name="description" content="TOPREG guide to playing live poker in {{NAME}}: venues, signature events, when to go and tips for travelling players.">
<style>""" + CSS + """</style>
</head>
<body>
<header><div class="wrap">
  <div class="logo"><a href="../index.html">TOP<span>REG</span></a></div>
  <div class="tag">Where to Play &mdash; {{NAME}}</div>
  <nav><a href="../index.html" class="back">&larr; Back to TOPREG</a></nav>
  <div class="updated">Auto-updated: {{UPDATED}}</div>
</div></header>

<div class="wrap">
  <section>
    <h2>&#9992; {{NAME}}</h2>
    <span class="dtags">{{TAGS}}</span>
    <p class="lede">{{INTRO}}</p>
  </section>

  <section><h2>Where the Action Is</h2>
    <div class="dests">{{VENUES}}</div>
  </section>

  <section><h2>When to Go</h2>
    <p class="body-text">{{WHEN}}</p>
  </section>

  <section><h2>Reg Tips</h2>
    <p class="body-text">{{TIPS}}</p>
  </section>

  <section><h2>Results &amp; Schedules</h2>
    <div class="rows">{{LINKS}}</div>
  </section>
</div>
""" + FOOTER + """
</body>
</html>
"""


if __name__ == "__main__":
    config = json.loads((ROOT / "config.json").read_text())
    offline = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "--offline" else None
    items = collect(config, offline)
    if not items:
        sys.exit("no items fetched - aborting (keeping previous site)")
    build(config, items, offline=bool(offline))
