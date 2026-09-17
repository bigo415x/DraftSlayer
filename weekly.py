#!/usr/bin/env python3
"""Build week.js for the in-season page.

    python weekly.py            # current NFL week (from Sleeper state)
    python weekly.py --week 3   # a specific week

Pulls: Sleeper roster/matchup/projections/last-week stats, ESPN injuries and
schedule, and The QB List's "What We Saw" (last week) and "Sit/Start" (this
week) articles filtered to your roster. Writes week.js; then commit and push.
"""
import json, re, sys, subprocess, html, datetime, pathlib, collections

HERE = pathlib.Path(__file__).parent
LEAGUE = "1388733713705099264"
ME = "1389151570356097024"
SEASON = 2026
API = "https://api.sleeper.app/v1"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
QBL = "https://football.pitcherlist.com"
BON = {"WR": .5, "TE": 1.0, "RB": 0, "QB": 0}
SLOTS = [("QB", ["QB"]), ("RB", ["RB"]), ("RB", ["RB"]), ("WR", ["WR"]), ("WR", ["WR"]),
         ("TE", ["TE"]), ("FLEX", ["RB", "WR", "TE"]), ("SF", ["QB", "RB", "WR", "TE"])]


def get(url, text=False):
    """ESPN 403s a browser UA; The QB List 403s curl's default. Try both."""
    for ua in (["-A", "Mozilla/5.0"], []):
        try:
            out = subprocess.run(["curl", "-sSL", "-m", "90", *ua, url], capture_output=True, check=True).stdout
            return out.decode("utf-8", "replace") if text else json.loads(out)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
    raise RuntimeError(f"fetch failed: {url}")


def score(s, pos):
    if not s: return 0.0
    g = lambda k: float(s.get(k) or 0)
    return round(g("pass_yd") * .04 + g("pass_td") * 4 - g("pass_int") + g("rush_yd") * .1 + g("rush_td") * 6
                 + g("rec_yd") * .1 + g("rec_td") * 6 - g("fum_lost") * 2 + g("rec") * (0.5 + BON.get(pos, 0)), 1)


def norm(s):
    s = (s or "").lower().replace(".", "").replace("'", "").replace("’", "").replace("-", " ")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


STAT = re.compile(r"^([A-Z][A-Za-z'\.\-’ ]+?)\s*\(([A-Z]{2,3})\)\s*(?:vs\.?|@)\s*([A-Z]{2,3})\s*:\s*(.*)$")


def qbl_blocks(page_html):
    """Player write-ups keyed by name: bold 'Name (TM) vs. OPP: stats' line then paragraphs."""
    out, cur = {}, None
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", page_html, re.S):
        raw = m.group(1)
        t = html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()
        if not t or t == "\xa0": continue
        mm = STAT.match(t)
        if mm and "<strong>" in raw:
            cur = mm.group(1).strip(); out[cur] = {"line": t, "paras": []}
        elif cur and not t.startswith("pic.twitter"):
            out[cur]["paras"].append(t)
    return out


def qbl_series(slug):
    """Fetch a roundup and every position sub-page it links to."""
    try: root = get(f"{QBL}/{slug}/", text=True)
    except Exception: return {}, None
    ids = re.findall(r"\?series_post=(\d+)", root)
    blocks = dict(qbl_blocks(root))
    for pid in dict.fromkeys(ids):
        try: blocks.update(qbl_blocks(get(f"{QBL}/{slug}/?series_post={pid}", text=True)))
        except Exception: pass
    return blocks, f"{QBL}/{slug}/"


def main():
    week = None
    if "--week" in sys.argv: week = int(sys.argv[sys.argv.index("--week") + 1])
    if week is None: week = int(get(f"{API}/state/nfl").get("week") or 1)
    last = week - 1
    print(f"building week {week}")

    players = get(f"{API}/players/nfl")
    rosters = get(f"{API}/league/{LEAGUE}/rosters")
    users = {u["user_id"]: u.get("display_name") for u in get(f"{API}/league/{LEAGUE}/users")}
    proj = get(f"{API}/projections/nfl/regular/{SEASON}/{week}")
    stats_last = get(f"{API}/stats/nfl/regular/{SEASON}/{last}") if last >= 1 else {}
    stats_prev = get(f"{API}/stats/nfl/regular/{SEASON}/{last-1}") if last >= 2 else {}
    matchups = get(f"{API}/league/{LEAGUE}/matchups/{week}")
    inj_raw = get(f"{ESPN}/injuries")
    sched = get(f"{ESPN}/scoreboard?dates={SEASON}&seasontype=2&week={week}")

    P = lambda pid: players.get(str(pid)) or {}
    me = next(r for r in rosters if r.get("owner_id") == ME)
    mine = [str(p) for p in (me.get("players") or [])]
    rostered = {str(p) for r in rosters for p in (r.get("players") or [])}

    # ---- injuries (ESPN, Sleeper fallback) ----
    inj = {}
    for team in inj_raw.get("injuries", []):
        for rec in team.get("injuries", []):
            if rec.get("status") == "Active": continue
            k = norm((rec.get("athlete") or {}).get("displayName"))
            if k: inj[k] = {"st": rec.get("status"), "note": re.sub(r"\s+", " ", rec.get("shortComment") or "")[:160]}
    def injury(pid):
        v = P(pid); k = norm(v.get("full_name"))
        if k in inj: return inj[k]
        if v.get("injury_status"): return {"st": v["injury_status"], "note": ""}
        return None

    # ---- schedule ----
    opp, kick = {}, {}
    for e in sched.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        comps = c.get("competitors") or []
        abbr = {x.get("homeAway"): (x.get("team") or {}).get("abbreviation") for x in comps}
        h, a = abbr.get("home"), abbr.get("away")
        if not (h and a): continue
        for t, o, pre in ((h, a, "vs "), (a, h, "@ ")):
            opp[t] = pre + o; kick[t] = e.get("date", "")
    opp["WAS"] = opp.get("WSH", opp.get("WAS")); kick["WAS"] = kick.get("WSH", kick.get("WAS"))

    def row(pid):
        v = P(pid); pos = v.get("position"); tm = v.get("team")
        s = stats_last.get(str(pid)) or {}
        sn, tsn = s.get("off_snp"), s.get("tm_off_snp")
        return {"id": str(pid), "n": v.get("full_name"), "p": pos, "t": tm, "age": v.get("age"),
                "proj": score(proj.get(str(pid)), pos), "last": score(s, pos),
                "snap": round(100 * sn / tsn) if sn and tsn else None,
                "tgt": int(s.get("rec_tgt") or 0), "car": int(s.get("rush_att") or 0),
                "opp": opp.get(tm, "BYE"), "kick": kick.get(tm, ""), "inj": injury(pid),
                "depth": v.get("depth_chart_order")}

    roster = [row(p) for p in mine]

    # ---- optimal lineup with coin flips ----
    OUT = ("Out", "Injured Reserve", "IR", "Doubtful", "NA", "Suspension")
    avail = [r for r in roster if not (r["inj"] and r["inj"]["st"] in OUT) and r["opp"] != "BYE"]
    used, lineup = set(), []
    for slot, acc in SLOTS:
        c = sorted([r for r in avail if r["p"] in acc and r["id"] not in used], key=lambda z: -z["proj"])
        pick = c[0] if c else None
        alt = c[1] if len(c) > 1 else None
        if pick: used.add(pick["id"])
        lineup.append({"slot": slot, "pick": pick, "alt": alt,
                       "flip": bool(pick and alt and pick["proj"] - alt["proj"] < 3)})
    bench = [r for r in roster if r["id"] not in used]

    # ---- opponent this week + games to watch ----
    mm = next((m for m in matchups if m.get("roster_id") == me["roster_id"]), None)
    opp_r = next((m for m in matchups if mm and m.get("matchup_id") == mm.get("matchup_id") and m.get("roster_id") != me["roster_id"]), None)
    opp_name = None; opp_starters = []
    if opp_r:
        rr = next(r for r in rosters if r["roster_id"] == opp_r["roster_id"])
        opp_name = users.get(rr.get("owner_id"))
        opp_starters = [row(p) for p in (opp_r.get("starters") or rr.get("starters") or []) if p and p != "0"]
    my_starters = [l["pick"] for l in lineup if l["pick"]]
    games = {}
    for e in sched.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        teams = [(x.get("team") or {}).get("abbreviation") for x in (c.get("competitors") or [])]
        teams = ["WAS" if t == "WSH" else t for t in teams]
        key = " @ ".join(reversed(teams)) if len(teams) == 2 else "?"
        g = {"game": key, "kick": e.get("date", ""), "mine": [], "theirs": []}
        for r in my_starters:
            if r["t"] in teams: g["mine"].append(f"{r['p']} {r['n']}")
        for r in opp_starters:
            if r["t"] in teams: g["theirs"].append(f"{r['p']} {r['n']}")
        if g["mine"] or g["theirs"]: games[key] = g
    games = sorted(games.values(), key=lambda g: (-(len(g["mine"]) + len(g["theirs"])), g["kick"]))

    # ---- waiver radar ----
    fa = []
    for pid, v in players.items():
        if v.get("position") not in ("QB", "RB", "WR", "TE") or not v.get("team") or pid in rostered: continue
        s = stats_last.get(pid) or {}; s2 = stats_prev.get(pid) or {}
        sn, tsn = s.get("off_snp"), s.get("tm_off_snp")
        if not sn: continue
        snap = round(100 * sn / tsn) if tsn else 0
        p_sn, p_tsn = s2.get("off_snp"), s2.get("tm_off_snp")
        psnap = round(100 * p_sn / p_tsn) if p_sn and p_tsn else None
        fa.append({"n": v["full_name"], "p": v["position"], "t": v["team"], "age": v.get("age"),
                   "snap": snap, "psnap": psnap, "tgt": int(s.get("rec_tgt") or 0), "car": int(s.get("rush_att") or 0),
                   "last": score(s, v["position"]), "proj": score(proj.get(pid), v["position"]),
                   "rise": (snap - psnap) if psnap is not None else None, "inj": injury(pid)})
    fa.sort(key=lambda z: -(z["snap"] + z["tgt"] * 2))
    radar = {pos: [x for x in fa if x["p"] == pos][:10] for pos in ("QB", "RB", "WR", "TE")}
    # starters newly out -> their backup
    down = []
    for k, i in inj.items():
        if i["st"] not in ("Out", "Injured Reserve"): continue
        for pid, v in players.items():
            if norm(v.get("full_name")) == k and v.get("position") in ("RB", "WR", "TE", "QB") and v.get("depth_chart_order") == 1:
                bk = [b for b in players.values() if b.get("team") == v.get("team") and b.get("position") == v["position"] and b.get("depth_chart_order") == 2]
                if bk:
                    b = bk[0]; bid = next((q for q, w in players.items() if w is b), None)
                    down.append({"starter": v["full_name"], "team": v["team"], "pos": v["position"], "st": i["st"],
                                 "backup": b["full_name"], "backup_rostered": bid in rostered})
                break

    # ---- The QB List ----
    wws, wws_url = qbl_series(f"what-we-saw-roundup-week-{last}") if last >= 1 else ({}, None)
    ss, ss_url = qbl_series(f"sit-start-{SEASON}-week-{week}-reviewing-all-fantasy-relevant-players-in-every-game")
    mine_n = {norm(r["n"]): r["n"] for r in roster}
    def mine_only(blocks): return {mine_n[norm(k)]: b for k, b in blocks.items() if norm(k) in mine_n}

    out = {"week": week, "built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "opponent": opp_name, "lineup": lineup, "bench": bench, "games": games,
           "radar": radar, "down": down[:12],
           "wws": {"url": wws_url, "players": mine_only(wws)},
           "sitstart": {"url": ss_url, "players": mine_only(ss)}}
    (HERE / "week.js").write_text("const WEEK = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"week.js written: lineup {sum(1 for l in lineup if l['pick'])}/8, {sum(1 for l in lineup if l['flip'])} coin flips, "
          f"{len(games)} games, WWS {len(out['wws']['players'])} players, Sit/Start {len(out['sitstart']['players'])} players")


if __name__ == "__main__":
    main()
