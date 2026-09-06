#!/usr/bin/env python3
"""Refresh injury designations in data.js from live feeds.

Rewrites only the injury fields (inj / injn on every player, and bki on the
starter a backup sits behind). Values, ADP, tiers, depth-chart data and the
manager scouting are left untouched, so this is safe to run repeatedly.

Sources: ESPN's public injuries feed, with Sleeper's injury_status as a fallback
for players ESPN does not list.

    python refresh_injuries.py            # update data.js and artifact.html
    python refresh_injuries.py --dry-run  # report what would change
"""
import json, re, sys, subprocess, urllib.request, datetime, pathlib

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
SLEEPER = "https://api.sleeper.app/v1/players/nfl"
HERE = pathlib.Path(__file__).parent
DRY = "--dry-run" in sys.argv

CODE = {"Questionable": "Q", "Doubtful": "D", "Out": "OUT",
        "Injured Reserve": "IR", "Suspension": "SUSP"}
SLCODE = {"Questionable": "Q", "Doubtful": "D", "Out": "OUT", "IR": "IR",
          "PUP": "IR", "Sus": "SUSP", "NA": "IR", "COV": "Q"}


def get(url):
    """ESPN rejects Python's urllib (TLS fingerprint), so prefer curl, which
    ships with Windows 10+ and every mac/linux box. urllib is the fallback."""
    try:
        out = subprocess.run(["curl", "-sS", "-m", "90", url],
                             capture_output=True, check=True).stdout
        if out:
            return json.loads(out)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        pass
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def norm(s):
    s = (s or "").lower().replace(".", "").replace("'", "").replace("-", " ")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    espn_raw = get(ESPN)
    sleeper = get(SLEEPER)

    # latest non-Active ESPN record per player
    espn = {}
    for team in espn_raw.get("injuries", []):
        for rec in team.get("injuries", []):
            if rec.get("status") == "Active":
                continue
            athlete = rec.get("athlete") or {}
            key = norm(athlete.get("displayName"))
            if not key:
                continue
            if key not in espn or (rec.get("date") or "") > (espn[key].get("date") or ""):
                espn[key] = rec

    sl_status = {}
    for v in sleeper.values():
        if v.get("position") in ("QB", "RB", "WR", "TE") and v.get("injury_status"):
            sl_status[norm(v.get("full_name"))] = v["injury_status"]

    src = (HERE / "data.js").read_text(encoding="utf-8")
    m = re.search(r"const POOL = (\[.*?\]);\n", src, re.S)
    if not m:
        sys.exit("could not find POOL in data.js")
    pool = json.loads(m.group(1))

    changes = []
    for p in pool:
        key = norm(p["n"])
        was = p.get("inj")
        rec = espn.get(key)
        if rec:
            p["inj"] = CODE.get(rec.get("status"), "Q")
            note = re.sub(r"\s+", " ", rec.get("shortComment") or "").strip()
            if note:
                p["injn"] = note[:110]
            else:
                p.pop("injn", None)
        elif key in sl_status and SLCODE.get(sl_status[key]):
            p["inj"] = SLCODE[sl_status[key]]
            p.pop("injn", None)
        else:
            p.pop("inj", None)
            p.pop("injn", None)
        if was != p.get("inj"):
            changes.append(f"{p['p']:3} {p['n']:24} {was or '-':4} -> {p.get('inj') or '-'}")

    # keep the "starter he backs up" tag in step with the same feed
    for p in pool:
        if p.get("bk"):
            k = norm(p["bk"])
            if k in espn:
                p["bki"] = CODE.get(espn[k].get("status"), "Q")
            elif k in sl_status and SLCODE.get(sl_status[k]):
                p["bki"] = SLCODE[sl_status[k]]
            else:
                p.pop("bki", None)

    tagged = sum(1 for p in pool if p.get("inj"))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"{tagged} players tagged, {len(changes)} changed since last run ({stamp})")
    for c in changes[:40]:
        print("  " + c)
    if len(changes) > 40:
        print(f"  ... and {len(changes)-40} more")
    if DRY:
        return

    src = src[:m.start(1)] + json.dumps(pool, separators=(",", ":")) + src[m.end(1):]
    src = re.sub(r"// inj/injn.*?\n", f"// inj/injn  injury designation + note. ESPN feed, refreshed {stamp}. Sleeper fallback.\n", src, count=1)
    (HERE / "data.js").write_text(src, encoding="utf-8")

    # rebuild the single-file artifact build
    html = (HERE / "index.html").read_text(encoding="utf-8")
    head = html.split("<head>", 1)[1].split("</head>", 1)[0]
    body = html.split("<body>", 1)[1].split("</body>", 1)[0]
    keep = re.findall(r"<title>.*?</title>|<link rel=\"stylesheet\".*?>|<style>.*?</style>", head, re.S)
    body = body.replace('<script src="data.js"></script>', "<script>\n" + (HERE / "data.js").read_text(encoding="utf-8") + "</script>")
    (HERE / "artifact.html").write_text("\n".join(keep) + "\n" + body, encoding="utf-8")
    print("data.js and artifact.html updated")


if __name__ == "__main__":
    main()
