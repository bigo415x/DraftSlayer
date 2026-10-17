"""Matchup-score cards for week.html, rebuilt every run by weekly.py.

Same model as the hand-written week-3 pilot (see the WR/RB Matchup Scoring docs):
0-100 score = 40% matchup (opponent's fantasy points allowed to the position, in
THIS league's scoring) + 35% scheme fit + 25% personnel (injuries on the
opposing defense), then capped when the player's own role is too small to
matter. The START/BENCH call on each card comes from the lineup optimizer in
weekly.py, so the panel and the lineup table can never disagree.

Sources (all public, no auth): Sleeper weekly stats, ESPN scoreboard/injuries/
depth charts/player stats, Sharp Football's coverage-scheme table, NFL Next Gen
Stats, Open-Meteo forecasts.

Weather is shown and flagged but does not move the score (Oliver kept the
40/35/25 weighting). Cornerback matchups feed the 25% personnel piece for WRs.
Real coverage grades (targets/passer rating allowed per CB) aren't public, so CB
quality is a box-score proxy: interceptions and passes defended per game.
"""
import re, html, collections

ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
API = "https://api.sleeper.app/v1"
SHARP = "https://www.sharpfootballanalysis.com/stats-nfl/nfl-coverage-schemes/"
NGS = "https://nextgenstats.nfl.com/api/statboard/{}?season={}&seasonType=REG"
SECONDARY = {"CB", "S", "FS", "SS", "DB", "NB"}
FRONT = {"DT", "DE", "NT", "LB", "ILB", "OLB", "MLB", "EDGE", "DL"}
DOWN = ("Out", "Injured Reserve", "Doubtful")


STATES = {"AZ": "Arizona", "CA": "California", "CO": "Colorado", "FL": "Florida", "GA": "Georgia", "IL": "Illinois",
          "IN": "Indiana", "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland", "MI": "Michigan", "MN": "Minnesota",
          "MO": "Missouri", "NC": "North Carolina", "NJ": "New Jersey", "NV": "Nevada", "NY": "New York", "OH": "Ohio",
          "PA": "Pennsylvania", "TN": "Tennessee", "TX": "Texas", "WA": "Washington", "WI": "Wisconsin"}
COVERED = {"SoFi Stadium"}   # translucent roof; ESPN doesn't flag it indoor
OPEN_METEO = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
              "&hourly=temperature_2m,precipitation_probability,wind_speed_10m,wind_gusts_10m"
              "&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone=UTC&start_date={d}&end_date={d}")


def game_weather(get, venue, kick):
    """Forecast over the first three hours from kickoff; None if unavailable (e.g. too far out)."""
    if not venue or not kick: return None
    if venue.get("indoor") or venue.get("fullName") in COVERED: return {"indoor": True}
    addr = venue.get("address") or {}; city = addr.get("city")
    if not city: return None
    try:
        res = get("https://geocoding-api.open-meteo.com/v1/search?name=" + city.replace(" ", "%20") + "&count=10&language=en&format=json").get("results") or []
        st, country = STATES.get(addr.get("state")), addr.get("country")
        pick = (next((r for r in res if st and r.get("admin1") == st), None)
                or next((r for r in res if country and country != "USA" and r.get("country") == country), None)
                or (res[0] if res else None))
        if not pick: return None
        h = get(OPEN_METEO.format(lat=pick["latitude"], lon=pick["longitude"], d=kick[:10])).get("hourly") or {}
        start = int(kick[11:13])
        idx = [i for i, ts in enumerate(h.get("time", [])) if start <= int(ts[11:13]) <= min(23, start + 2)]
        vals = lambda k: [h[k][i] for i in idx if (h.get(k) or [None] * (i + 1))[i] is not None]
        temps = vals("temperature_2m")
        if not temps: return None
        return {"indoor": False, "temp": sum(temps) / len(temps), "rain": max(vals("precipitation_probability") or [0]),
                "wind": max(vals("wind_speed_10m") or [0]), "gust": max(vals("wind_gusts_10m") + vals("wind_speed_10m") or [0])}
    except Exception:
        return None


def weather_text(wx, pos):
    """(sentence, hurts_passing)"""
    if not wx: return None, False
    if wx.get("indoor"): return "Indoors, so weather isn't a factor.", False
    base = f"{wx['temp']:.0f}°F, {wx['rain']:.0f}% chance of rain, wind {wx['wind']:.0f} mph (gusts {wx['gust']:.0f})"
    windy = wx["wind"] >= 15 or wx["gust"] >= 25; wet = wx["rain"] >= 60; cold = wx["temp"] <= 32
    if pos == "RB":
        return base + (": rough passing weather tends to push teams toward the run." if windy or wet else ": weather shouldn't matter."), False
    if windy: return base + ": wind strong enough to hurt passing, especially deep throws.", True
    if wet: return base + ": rain likely, a mild downgrade for passing.", True
    if cold: return base + ": freezing, a mild downgrade for passing.", True
    return base + ": weather shouldn't matter.", False


def corner_report(get, team_id, games):
    """Starting left/right outside corners and slot corner, skipping injured starters, with a playmaking rate."""
    out = {}
    if not team_id: return out
    try:
        dc = get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/depthcharts")
        grp = next((g for g in dc.get("depthchart", []) if "lcb" in (g.get("positions") or {})), None)
        if not grp: return out
        for slot in ("lcb", "rcb", "nb"):
            fill = False
            for a in ((grp["positions"].get(slot) or {}).get("athletes") or []):
                hurt = [i.get("status") for i in a.get("injuries") or []]
                if any(s in DOWN for s in hurt):
                    fill = True; continue
                pd = ints = 0.0
                try:
                    st = get(f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{a['id']}/overview").get("statistics") or {}
                    reg = next((s["stats"] for s in st.get("splits", []) if s.get("displayName") == "Regular Season"), None)
                    if reg:
                        val = dict(zip(st.get("names") or [], reg))
                        pd, ints = float(val.get("passesDefended") or 0), float(val.get("interceptions") or 0)
                except Exception:
                    pass
                out[slot] = {"name": a.get("displayName"), "pd": int(pd), "int": int(ints),
                             "rate": (pd + 2 * ints) / games if games else 0.0, "fill": fill, "q": "Questionable" in hurt}
                break
    except Exception:
        pass
    return out


def corner_score(c):
    """Higher = easier for the receiver."""
    s = 25 if c["rate"] >= 1.2 else 50 if c["rate"] >= 0.6 else 70
    if c["fill"]: s += 20
    if c["q"]: s += 5
    return min(95, s)


def corner_phrase(c):
    tag = "a playmaking corner" if c["rate"] >= 1.2 else "a solid corner" if c["rate"] >= 0.6 else "a quiet stat line"
    extra = " (filling in for an injured starter)" if c["fill"] else " (questionable)" if c["q"] else ""
    return f"{c['name']}{extra}: {c['int']} INT, {c['pd']} pass{'' if c['pd'] == 1 else 'es'} defended, {tag}"


def team_ab(a):
    return "WAS" if a == "WSH" else a


def pct_rank(value, values, high_is_good=True):
    """0-100: share of the league this value beats."""
    vals = sorted(values)
    if not vals: return 50
    below = sum(1 for v in vals if v < value) + 0.5 * sum(1 for v in vals if v == value)
    p = 100 * below / len(vals)
    return round(p if high_is_good else 100 - p)


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def build(get, score, players, season, week, roster, lineup, sitstart, inj_raw, sched):
    last = week - 1
    if last < 1: return None
    P = lambda pid: players.get(str(pid)) or {}

    # ---- season box scores + who played whom ----
    stats = {w: get(f"{API}/stats/nfl/regular/{season}/{w}") for w in range(1, last + 1)}
    names, games = {}, collections.defaultdict(dict)   # games[week][team] = opponent
    for w in range(1, last + 1):
        sb = get(f"{ESPN}/scoreboard?dates={season}&seasontype=2&week={w}")
        for e in sb.get("events", []):
            c = (e.get("competitions") or [{}])[0]
            if (e.get("status") or {}).get("type", {}).get("name") != "STATUS_FINAL": continue
            t = [team_ab((x.get("team") or {}).get("abbreviation")) for x in c.get("competitors", [])]
            for x in c.get("competitors", []):
                tm = x.get("team") or {}; names[tm.get("displayName")] = team_ab(tm.get("abbreviation"))
            if len(t) == 2: games[w][t[0]], games[w][t[1]] = t[1], t[0]

    # ---- what each defense allows (this league's scoring) ----
    allow = collections.defaultdict(lambda: collections.defaultdict(float)); played = collections.Counter()
    for w, opp_of in games.items():
        off = collections.defaultdict(lambda: collections.defaultdict(float))
        for pid, s in stats[w].items():
            v = P(pid); tm, pos = v.get("team"), v.get("position")
            if not tm or pos not in ("WR", "TE", "RB"): continue
            o = off[tm]; o[pos] += score(s, pos); o[pos + "_tgt"] += s.get("rec_tgt") or 0
            if pos == "RB":
                o["car"] += s.get("rush_att") or 0; o["ryd"] += s.get("rush_yd") or 0; o["rtd"] += s.get("rush_td") or 0
        for d, o in opp_of.items():
            for k, val in off[o].items(): allow[d][k] += val
            played[d] += 1
    per = {d: {k: v / played[d] for k, v in a.items()} for d, a in allow.items() if played[d]}
    def rank_of(d, key):
        order = sorted(per, key=lambda t: -per[t].get(key, 0))
        return order.index(d) + 1 if d in order else None

    # ---- coverage scheme (Sharp) ----
    cov = {}
    try:
        page = get(SHARP, text=True)
        for r in re.findall(r"<tr.*?</tr>", page, re.S):
            c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)]
            if len(c) >= 5 and c[0] in names:
                try: cov[names[c[0]]] = {"man": float(c[1]), "zone": float(c[2]), "closed": float(c[3]), "open": float(c[4])}
                except ValueError: pass
    except Exception:
        pass

    # ---- tracking data (context only; never the tiebreaker) ----
    ngs = {}
    for kind in ("receiving", "rushing"):
        try:
            for s in get(NGS.format(kind, season), referer=f"https://nextgenstats.nfl.com/stats/{kind}").get("stats", []):
                ngs.setdefault(s["player"]["displayName"], {}).update(s)
        except Exception:
            pass

    # ---- injuries on each defense ----
    hurt = collections.defaultdict(list)
    for grp in inj_raw.get("injuries", []):
        tm = names.get(grp.get("displayName"))
        for rec in grp.get("injuries", []):
            a = rec.get("athlete") or {}; pos = (a.get("position") or {}).get("abbreviation")
            if tm and rec.get("status") in DOWN and pos in SECONDARY | FRONT:
                hurt[tm].append((pos, a.get("displayName"), rec.get("status")))

    # ---- this week's games: opponent, line, venue ----
    wk = {}
    for e in sched.get("events", []):
        c = (e.get("competitions") or [{}])[0]; comp = c.get("competitors") or []
        if len(comp) != 2: continue
        odds = (c.get("odds") or [{}])[0]; total = odds.get("overUnder"); det = odds.get("details") or ""
        fav, line = None, 0.0
        m = re.match(r"([A-Z]{2,3})\s+(-?[\d.]+)", det)
        if m: fav, line = team_ab(m.group(1)), abs(float(m.group(2)))
        indoor = (c.get("venue") or {}).get("indoor"); venue = c.get("venue") or {}
        for i, x in enumerate(comp):
            me = team_ab((x.get("team") or {}).get("abbreviation")); o = team_ab((comp[1 - i].get("team") or {}).get("abbreviation"))
            implied = None
            if total:
                implied = (total + line) / 2 if me == fav else (total - line) / 2
            wk[me] = {"opp": o, "home": x.get("homeAway") == "home", "total": total, "implied": implied, "indoor": indoor,
                      "venue": venue, "kick": e.get("date", ""), "opp_id": (comp[1 - i].get("team") or {}).get("id")}
    wx_cache, cb_cache = {}, {}
    def wx_for(tm):
        g = wk.get(tm) or {}; key = ((g.get("venue") or {}).get("id"), g.get("kick"))
        if key not in wx_cache: wx_cache[key] = game_weather(get, g.get("venue"), g.get("kick"))
        return wx_cache[key]
    def cbs_for(tm):
        g = wk.get(tm) or {}; opp = g.get("opp")
        if opp not in cb_cache: cb_cache[opp] = corner_report(get, g.get("opp_id"), played.get(opp) or 0)
        return cb_cache[opp]

    # ---- each player's own role, last 3 games ----
    def role(pid, pos, team):
        tg = tt = car = tc = rz = sn = tsn = 0; n = 0
        for w in range(max(1, last - 2), last + 1):
            s = stats[w].get(str(pid)) or {}
            if not (s.get("off_snp") or s.get("rec_tgt") or s.get("rush_att")): continue
            n += 1; tg += s.get("rec_tgt") or 0; car += s.get("rush_att") or 0; rz += int(s.get("rush_rz_att") or 0)
            sn += s.get("off_snp") or 0; tsn += s.get("tm_off_snp") or 0
            for q, s2 in stats[w].items():
                if P(q).get("team") == team:
                    tt += s2.get("rec_tgt") or 0
                    if P(q).get("position") == "RB": tc += s2.get("rush_att") or 0
        return {"games": n, "tpg": tg / n if n else 0, "tshare": tg / tt if tt else 0,
                "cpg": car / n if n else 0, "cshare": car / tc if tc else 0, "rz": rz,
                "snap": round(100 * sn / tsn) if tsn else None}

    slot_of = {}
    counts = collections.Counter()
    for l in lineup:
        if l["pick"]:
            counts[l["slot"]] += 1
            lab = l["slot"] + (str(counts[l["slot"]]) if l["slot"] in ("RB", "WR") else "")
            slot_of[l["pick"]["id"]] = "SUPERFLEX" if lab == "SF" else lab

    def card(r):
        pid, pos, tm = r["id"], r["p"], r["t"]
        base = {"n": r["n"], "p": pos, "t": tm, "opp": r["opp"], "proj": r["proj"]}
        st = (r.get("inj") or {}).get("st")
        if r["opp"] == "BYE": return {**base, "score": None, "verdict": "BYE", "bottom": "On bye this week."}
        if st in ("Out", "Injured Reserve", "IR", "Suspension", "NA"):
            return {**base, "score": None, "verdict": "OUT", "bottom": f"{st}. {(r['inj'] or {}).get('note', '')}".strip()}
        g = wk.get(tm, {}); opp = g.get("opp")
        ro = role(pid, pos, tm); d = per.get(opp, {}); key = "RB" if pos == "RB" else pos
        dvp = pct_rank(d.get(key, 0), [x.get(key, 0) for x in per.values()])
        rk = rank_of(opp, key) if opp else None
        word = "one of the most generous matchups" if rk and rk <= 8 else "one of the stingiest matchups" if rk and rk >= 25 else "about an average matchup"
        lines = [("Matchup", f"{opp} allows {d.get(key, 0):.1f} {pos} points a game in this league's scoring "
                  f"({ordinal(rk)} most of 32): {word}." if rk else "No defensive sample yet.")]
        n = ngs.get(r["n"], {})
        if pos in ("WR", "TE"):
            adot = n.get("avgIntendedAirYards")
            deep = adot is not None and adot >= 12
            cv = cov.get(opp)
            if cv:
                if deep:
                    fit = round(0.6 * pct_rank(cv["man"], [c["man"] for c in cov.values()]) + 0.4 * pct_rank(cv["closed"], [c["closed"] for c in cov.values()]))
                    lines.append(("Scheme", f"{opp} plays man coverage {cv['man']:.0f}% of snaps with a single-high safety {cv['closed']:.0f}%: "
                                  + ("the one-on-one looks a downfield receiver wants." if fit >= 55 else "not many free one-on-one shots deep." if fit <= 45 else "neutral for a downfield receiver.")))
                else:
                    fit = pct_rank(cv["zone"], [c["zone"] for c in cov.values()])
                    lines.append(("Scheme", f"{opp} plays zone {cv['zone']:.0f}% of snaps: "
                                  + ("more zone than most defenses, so soft spots underneath for a short-route target like him." if fit >= 55 else "less zone than most defenses, so tighter coverage on short routes." if fit <= 45 else "about league-average zone usage; neutral for his short-route role.")))
            else:
                fit = 50; lines.append(("Scheme", "Coverage data unavailable this week."))
            dbs = [x for x in hurt.get(opp, []) if x[0] in SECONDARY]
            pers = min(100, 40 + 20 * len(dbs))
            lines.append(("Secondary", ("Missing " + ", ".join(f"{nm} ({p}, {s})" for p, nm, s in dbs[:4]) + ".") if dbs else "No defensive backs on the injury report."))
            if pos == "WR":
                cbs = cbs_for(tm)
                slot_wr = adot is not None and adot < 9
                faced = [cbs[k] for k in (("nb",) if slot_wr else ("lcb", "rcb")) if k in cbs]
                if faced:
                    cbs_sc = sum(corner_score(c) for c in faced) / len(faced)
                    pers = round(0.5 * pers + 0.5 * cbs_sc)
                    where = "Mostly a short-area/slot target, so his likely matchup is the slot defender, " if slot_wr else "Lines up mostly outside, against "
                    lines.append(("Corners", where + "; ".join(corner_phrase(c) for c in faced) + "."))
            share, gate = ro["tshare"], ro["tshare"] < 0.12
            role_txt = f"{100 * share:.0f}% of team targets over his last {ro['games']} games ({ro['tpg']:.1f} a game)" + (f", {ro['snap']}% of snaps" if ro["snap"] else "")
        else:
            ypc = d.get("ryd", 0) / d["car"] if d.get("car") else 0
            fit = round(0.5 * pct_rank(ypc, [x.get("ryd", 0) / x["car"] for x in per.values() if x.get("car")]) + 0.5 * pct_rank(d.get("rtd", 0), [x.get("rtd", 0) for x in per.values()]))
            lines.append(("Run defense", f"{opp} gives up {ypc:.2f} yards a carry and {d.get('rtd', 0):.1f} rushing TDs a game to backs: "
                          + ("soft." if fit >= 60 else "tough." if fit <= 40 else "middle of the pack.")))
            front = [x for x in hurt.get(opp, []) if x[0] in FRONT]
            pers = min(100, 40 + 15 * len(front))
            lines.append(("Front seven", ("Missing " + ", ".join(f"{nm} ({p}, {s})" for p, nm, s in front[:4]) + ".") if front else "No front-seven starters on the injury report."))
            share, gate = ro["cshare"], ro["cshare"] < 0.35
            role_txt = f"{100 * share:.0f}% of team RB carries over his last {ro['games']} games ({ro['cpg']:.1f} a game, {ro['rz']} red-zone carries)"
        wx_line, wx_bad = weather_text(wx_for(tm), pos)
        if wx_line: lines.append(("Weather", wx_line))
        sc = round(0.40 * dvp + 0.35 * fit + 0.25 * pers)
        if gate: sc = min(sc, 45)
        lines.insert(0, ("Role", role_txt + ("; too small a role to trust the matchup." if gate else ".")))
        if g.get("implied"):
            lines.append(("Game", f"{tm} expected to score about {g['implied']:.0f} (total {g['total']}); "
                          + ("indoors." if g.get("indoor") else "outdoors.")))
        slot = slot_of.get(pid)
        verdict = f"START: {slot}" if slot else "BENCH"
        if slot:
            bottom = f"Starts at {slot}, projected {r['proj']:.1f}." + (" Tough spot, but still your best option for the slot." if sc < 35 else " Good spot on top of the role." if sc >= 60 else "")
        else:
            bottom = f"Bench, projected {r['proj']:.1f}." + (" Strong matchup if a starter gets hurt." if sc >= 60 else "")
        if wx_bad: bottom += " Weather flag: see above."
        adv = None
        if pos in ("WR", "TE") and n.get("targets"):
            adv = (f"{n['avgIntendedAirYards']:.1f}-yard average target depth, {n['catchPercentage']:.0f}% catch rate, "
                   f"{n['avgSeparation']:.1f} yards of separation ({n['targets']} targets). Context only; targets drive the call.")
        elif pos == "RB" and n.get("rushYardsOverExpectedPerAtt") is not None:
            adv = f"{n['rushYardsOverExpectedPerAtt']:+.2f} rushing yards over expected per carry on {n.get('rushAttempts')} carries."
        q = (sitstart or {}).get(r["n"])
        qbl = None
        if q:
            agree = (q["verdict"] == "START") == bool(slot)
            qbl = f"{q['verdict']}{' (' + q['tier'] + ')' if q.get('tier') else ''}: " + ("agrees." if agree else "disagrees with this call.")
        return {**base, "score": sc, "verdict": verdict, "lines": lines, "bottom": bottom, "adv": adv, "qbl": qbl}

    def order(c):
        v = c["verdict"]
        return (0 if v.startswith("START") else 1 if v == "BENCH" else 2, -(c["proj"] or 0))
    wr = sorted([card(r) for r in roster if r["p"] in ("WR", "TE")], key=order)
    rb = sorted([card(r) for r in roster if r["p"] == "RB"], key=order)
    return {"week": week, "wr": wr, "rb": rb, "coverage": bool(cov), "ngs": bool(ngs)}
