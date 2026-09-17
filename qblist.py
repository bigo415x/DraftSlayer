"""Parsers for The QB List (football.pitcherlist.com).

Two article families, two shapes:

* What We Saw — a roundup that is a *series* (position sub-pages via ?series_post=ID),
  plus standalone posts for late games ("What We Saw – Broncos vs Chiefs"). Every
  write-up is anchored by a bold stat line: "Name (TM) vs. OPP: stats".
* Sit/Start — a series with one sub-page per game. Verdict lines ("Name: START, RB1",
  several per paragraph) are followed by one analysis paragraph for that group.

Each function takes the caller's `get(url, text=True)` fetcher so this module stays free
of transport concerns.
"""
import re, html, datetime

QBL = "https://football.pitcherlist.com"
STAT = re.compile(r"^([A-Z][A-Za-z'\.\-’ ]+?)\s*\(([A-Z]{2,3})\)\s*(?:vs\.?|@)\s*([A-Z]{2,3})\s*:\s*(.*)$")
VERDICT = re.compile(r"^([A-Z][A-Za-z'\.\-’ ]+?):\s*(START|SIT|FLEX|BENCH)\b(?:,\s*([A-Za-z]{2}\d+))?", re.I)


def _paras(page):
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", page, re.S):
        raw = m.group(1)
        t = html.unescape(re.sub(r"<br\s*/?>", "\n", raw))
        t = re.sub(r"<[^>]+>", "", t).strip()
        if t and t != "\xa0":
            yield raw, t


def wws_blocks(page):
    """{name: {line, paras}} from a What We Saw page."""
    out, cur = {}, None
    for raw, t in _paras(page):
        mm = STAT.match(t)
        if mm and "<strong>" in raw:
            cur = mm.group(1).strip()
            out[cur] = {"line": t, "paras": []}
        elif cur and not t.startswith("pic.twitter"):
            out[cur]["paras"].append(t)
    return out


def late_games(get, since_days=6):
    """Standalone late-game What We Saw posts from the last few days."""
    blocks = {}
    try:
        posts = get(f"{QBL}/wp-json/wp/v2/posts?search=what%20we%20saw&per_page=20&_fields=id,title,link,date")
    except Exception:
        return blocks
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=since_days)).isoformat()
    for post in posts:
        title = html.unescape((post.get("title") or {}).get("rendered", "")).lower()
        if not title.startswith("what we saw") or "roundup" in title or post.get("date", "") < cutoff:
            continue
        try:
            blocks.update(wws_blocks(get(post["link"], text=True)))
        except Exception:
            pass
    return blocks


def sitstart(get, slug):
    """{name: {verdict, tier, note}} across every game sub-page of a Sit/Start article."""
    try:
        root = get(f"{QBL}/{slug}/", text=True)
    except Exception:
        return {}, None
    out = {}
    for pid in dict.fromkeys(re.findall(r"\?series_post=(\d+)", root)):
        try:
            page = get(f"{QBL}/{slug}/?series_post={pid}", text=True)
        except Exception:
            continue
        pending = []
        for _, t in _paras(page):
            lines = [l.strip() for l in t.split("\n") if l.strip()]
            verdicts = [VERDICT.match(l) for l in lines]
            if lines and all(verdicts):
                pending = []
                for v in verdicts:
                    name = v.group(1).strip()
                    out[name] = {"verdict": v.group(2).upper(), "tier": (v.group(3) or "").upper(), "note": ""}
                    pending.append(name)
            elif pending and len(t) > 40:
                for name in pending:
                    out[name]["note"] = t[:600]
                pending = []
    return out, f"{QBL}/{slug}/"
