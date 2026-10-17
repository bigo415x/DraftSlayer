#!/usr/bin/env python3
"""Build affiliates.json: each NFL team's home-market CBS / FOX / NBC / ABC station.

    python affiliates.py

Source: Wikipedia's network affiliate lists (city of license, call letters,
channel). Stations rarely change, so this runs by hand, not in the daily job.
weekly.py reads affiliates.json to label "Games to watch".
"""
import json, re, pathlib, subprocess, time

HERE = pathlib.Path(__file__).parent
PAGES = {"CBS": "List_of_CBS_television_affiliates", "FOX": "List_of_Fox_Broadcasting_Company_affiliates",
         "NBC": "List_of_NBC_television_affiliates", "ABC": "List_of_American_Broadcasting_Company_television_affiliates"}
# Home market for each team, as Wikipedia names the city of license (first match wins)
MARKET = {
    "ARI": ["Phoenix"], "ATL": ["Atlanta"], "BAL": ["Baltimore"], "BUF": ["Buffalo"], "CAR": ["Charlotte"],
    "CHI": ["Chicago"], "CIN": ["Cincinnati"], "CLE": ["Cleveland"], "DAL": ["Dallas", "Fort Worth"], "DEN": ["Denver"],
    "DET": ["Detroit"], "GB": ["Green Bay"], "HOU": ["Houston"], "IND": ["Indianapolis"], "JAX": ["Jacksonville"],
    "KC": ["Kansas City"], "LV": ["Las Vegas", "Henderson"], "LAC": ["Los Angeles"], "LAR": ["Los Angeles"],
    "MIA": ["Miami", "Fort Lauderdale"], "MIN": ["Minneapolis", "Saint Paul", "St. Paul"], "NE": ["Boston"],
    "NO": ["New Orleans"], "NYG": ["New York"], "NYJ": ["New York"], "PHI": ["Philadelphia"], "PIT": ["Pittsburgh"],
    "SF": ["San Francisco", "Oakland", "San Jose"], "SEA": ["Seattle", "Tacoma"], "TB": ["Tampa", "St. Petersburg", "Saint Petersburg"],
    "TEN": ["Nashville"], "WAS": ["Washington"],
}


def wikitext(page):
    url = f"https://en.wikipedia.org/w/api.php?action=parse&page={page}&prop=wikitext&format=json&formatversion=2"
    for attempt in range(4):   # Wikipedia occasionally returns an empty body under load
        out = subprocess.run(["curl", "-s", "-A", "DraftSlayer/1.0 (github.com/bigo415x/DraftSlayer)", url], capture_output=True).stdout
        try: return json.loads(out)["parse"]["wikitext"]
        except (ValueError, KeyError): time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"Wikipedia fetch failed: {page}")


def link_text(cell):
    m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", cell)
    return ((m.group(2) or m.group(1)) if m else re.sub(r"<[^>]+>|'''|''", "", cell)).strip(), (m.group(1).strip() if m else "")


def parse(text):
    """[(city, city_link_target, station, channel)] from the table rows."""
    rows, city, target = [], None, ""
    for row in text.split("\n|-"):
        lines = [l for l in row.strip().split("\n") if l.strip()]
        st_line = next((l for l in lines if l.startswith("!") and "[[" in l), None)
        if not st_line: continue
        first = lines[0]
        if first.startswith("|") and not first.startswith("|-") and "[[" in first and first is not st_line:
            cell = first.lstrip("|").split("||")[0]
            cell = re.sub(r'^\s*rowspan="\d+"\s*\|', "", cell)
            city, target = link_text(cell)
        station = link_text(st_line.split("|", 1)[-1])[0]
        after = lines[lines.index(st_line) + 1] if lines.index(st_line) + 1 < len(lines) else ""
        ch = re.sub(r'rowspan="\d+"\s*\|', "", after.lstrip("|").split("||")[0]).strip()
        if city: rows.append((city, target, station, ch))
    return rows


def main():
    table = {t: {} for t in MARKET}
    for net, page in PAGES.items():
        rows = parse(wikitext(page))
        for team, cities in MARKET.items():
            for c in cities:
                hit = next((r for r in rows if r[0] == c or r[1].split(",")[0] == c or r[0].startswith(c)), None)
                if hit:
                    table[team][net] = {"call": hit[2], "ch": hit[3], "city": hit[0]}
                    break
    (HERE / "affiliates.json").write_text(json.dumps(table, indent=1, ensure_ascii=False), encoding="utf-8")
    missing = [(t, n) for t in table for n in PAGES if n not in table[t]]
    print(f"affiliates.json written; {32 * 4 - len(missing)}/128 found; missing: {missing}")


if __name__ == "__main__":
    main()
