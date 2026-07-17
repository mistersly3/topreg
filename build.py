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

DESTINATIONS = [
    ("Las Vegas, USA", "Home of the WSOP every summer. Bellagio, Aria and Wynn "
     "run the biggest cash games and daily tournaments on the planet.", "WSOP · Wynn Classic"),
    ("Barcelona, Spain", "EPT Barcelona at Casino Barcelona is Europe's largest "
     "annual festival, with huge side events and beach-side cash games.", "EPT Barcelona"),
    ("London, UK", "The Hippodrome and Aspers anchor a deep year-round scene, "
     "plus GUKPT stops and Triton London super high rollers.", "GUKPT · Triton"),
    ("Monte Carlo, Monaco", "The EPT Grand Final's historic home. Glamour, "
     "high rollers and the Casino de Monte-Carlo.", "EPT Monte Carlo"),
    ("Paradise Island, Bahamas", "PokerStars' flagship winter festival brings "
     "thousands of players to Atlantis every January.", "PSPC · PCA"),
    ("Northern Cyprus", "Merit casinos host Triton and Mediterranean poker "
     "festivals with some of the softest high-stakes fields anywhere.", "Triton · Merit Series"),
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


def dest_card(name, blurb, tags):
    return f'''<div class="dest"><h3>{esc(name)}</h3><p>{esc(blurb)}</p>
      <span class="dtags">{esc(tags)}</span></div>'''


def build(config, items):
    tourney = [i for i in items if TOURNEY_RE.search(i["title"])][:8]
    tourney_keys = {t["title"] for t in tourney}
    news = [i for i in items if i["title"] not in tourney_keys][:config["max_news"]]
    if len(news) < 6:  # if feed is result-heavy, show everything as news too
        news = items[:config["max_news"]]
    updated = datetime.now(timezone.utc).strftime("%B %d, %Y %H:%M UTC")
    mail = config["sponsor_email"]

    page = TEMPLATE
    page = page.replace("{{TAGLINE}}", esc(config["tagline"]))
    page = page.replace("{{UPDATED}}", updated)
    page = page.replace("{{YEAR}}", str(datetime.now().year))
    page = page.replace("{{BANNERS}}", "\n".join(banner(a) for a in config["affiliates"]))
    page = page.replace("{{NEWS}}", "\n".join(news_card(i) for i in news))
    page = page.replace("{{RESULTS}}", "\n".join(result_row(i) for i in tourney))
    page = page.replace("{{DESTS}}", "\n".join(dest_card(*d) for d in DESTINATIONS))
    page = page.replace("{{MAIL}}", esc(mail))

    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(page, encoding="utf-8")
    (SITE / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    (SITE / "CNAME").write_text(config["domain"] + "\n", encoding="utf-8")
    print(f"built site/index.html — {len(news)} news, {len(tourney)} results")


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TOPREG — Poker News, Tournaments &amp; Where to Play</title>
<meta name="description" content="TOPREG: daily poker news, tournament results, live poker destinations and the best rooms to play online. Built for regs, by regs.">
<style>
:root{--felt:#0d3b2e;--felt2:#0a2e24;--gold:#d4af37;--ink:#e8e6df;--mut:#9aa89f;--card:#12463a;--red:#c0392b}
*{margin:0;box-sizing:border-box}
body{font-family:Georgia,'Times New Roman',serif;background:var(--felt2);color:var(--ink)}
a{color:inherit;text-decoration:none}
.wrap{max-width:1100px;margin:0 auto;padding:0 20px}
header{background:linear-gradient(180deg,#071f18,var(--felt2));border-bottom:2px solid var(--gold);padding:26px 0 18px}
.logo{font-size:2.6rem;letter-spacing:.35em;font-weight:700;color:var(--gold)}
.logo span{color:var(--ink)}
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
.dest{background:var(--card);border:1px solid #1d5a49;border-radius:10px;padding:20px}
.dest h3{color:var(--gold);margin-bottom:8px}
.dest p{color:var(--mut);font-size:.9rem;line-height:1.55}
.dtags{display:inline-block;margin-top:12px;font-family:Helvetica,Arial,sans-serif;font-size:.68rem;color:var(--ink);background:#0a2e24;padding:4px 10px;border-radius:20px;letter-spacing:.08em}
.partner{background:linear-gradient(135deg,#1a1204,#2b1f08);border:1px solid var(--gold);border-radius:10px;padding:34px;text-align:center;margin-top:44px}
.partner h2{border:none;margin:0 0 10px}
.partner p{color:var(--mut);max-width:600px;margin:0 auto 18px;line-height:1.6}
.pbtn{display:inline-block;background:var(--gold);color:#111;font-family:Helvetica,Arial,sans-serif;font-weight:700;font-size:.8rem;letter-spacing:.12em;text-transform:uppercase;padding:13px 30px;border-radius:6px}
footer{margin-top:60px;border-top:1px solid #1d5a49;padding:30px 0 40px;font-family:Helvetica,Arial,sans-serif;font-size:.72rem;color:var(--mut);line-height:1.7}
footer strong{color:var(--ink)}
.age{display:inline-block;border:2px solid var(--red);color:var(--red);border-radius:50%;width:38px;height:38px;line-height:34px;text-align:center;font-weight:700;margin-right:10px;font-size:.85rem}
</style>
</head>
<body>
<header><div class="wrap">
  <div class="logo">TOP<span>REG</span></div>
  <div class="tag">{{TAGLINE}}</div>
  <nav><a href="#news">News</a><a href="#results">Tournament Results</a><a href="#play">Where to Play</a><a href="#rooms">Best Rooms</a><a href="#partner">Advertise</a></nav>
  <div class="updated">Auto-updated: {{UPDATED}}</div>
</div></header>

<div class="wrap">
  <section id="rooms">
    <div class="banners">{{BANNERS}}</div>
    <div class="ad-note">Advertisement — TOPREG may earn a commission from partner links. 18+ only. Play responsibly.</div>
  </section>

  <section id="news"><h2>&#9824; Latest Poker News</h2>
    <div class="grid">{{NEWS}}</div>
  </section>

  <section id="results"><h2>&#127942; Tournament Results &amp; Winners</h2>
    <div class="rows">{{RESULTS}}</div>
  </section>

  <section id="play"><h2>&#9992; Where to Play Live</h2>
    <div class="dests">{{DESTS}}</div>
  </section>

  <section class="partner" id="partner">
    <h2>Advertise on TOPREG</h2>
    <p>Reach a dedicated audience of poker regulars, grinders and travelling players. Banner placements, sponsored slots and featured room listings available.</p>
    <a class="pbtn" href="mailto:{{MAIL}}?subject=Advertising%20on%20TOPREG">Get in touch</a>
  </section>
</div>

<footer><div class="wrap">
  <p><span class="age">18+</span><strong>Play responsibly.</strong> Gambling can be addictive. If you or someone you know has a gambling problem, seek help: <a href="https://www.begambleaware.org" rel="noopener">BeGambleAware.org</a>.</p>
  <p style="margin-top:12px"><strong>Affiliate disclosure:</strong> TOPREG contains affiliate links and advertising. We may receive compensation when you click links or sign up through this site. This does not affect our editorial content, which links to and credits original sources.</p>
  <p style="margin-top:12px">This website is intended exclusively for visitors located in jurisdictions where online poker and related advertising are legal. It is <strong>not directed at residents of Italy</strong> or any jurisdiction where gambling advertising is prohibited. Nothing on this site constitutes an invitation to gamble where unlawful. News headlines and excerpts are aggregated from and credited to their original publishers.</p>
  <p style="margin-top:12px">&copy; {{YEAR}} TOPREG.it — All rights reserved.</p>
</div></footer>
</body>
</html>
"""


if __name__ == "__main__":
    config = json.loads((ROOT / "config.json").read_text())
    offline = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "--offline" else None
    items = collect(config, offline)
    if not items:
        sys.exit("no items fetched — aborting (keeping previous site)")
    build(config, items)
