#!/usr/bin/env python3
"""League-adjusted trade value chart.

    python tradevalue.py            # writes trade_data.js (read by trade.html)

Method: PeakedInHighSkool's chart is a market number (expert ROS ranks + user
trade data + expected points) built for 4pt pass TD / 2QB / 1.0 PPR. Our league
differs only in reception scoring (RB 0.5, WR 1.0, TE 1.5) and in replacement
level (superflex, 12 teams, actual free-agent pool). So:

  1. Sum Sleeper weekly projections for the rest of the season (this week..17)
     under BOTH scoring systems.
  2. VBD = points over replacement, where replacement = the best FREE AGENT at
     each position in this league right now (same definition under both
     scorings, so the two VBDs differ only by the reception change).
  3. Fit the market curve: chart value ~ a * VBD_chart ** b (per position pool).
  4. Adjusted value = chart value * (VBD_league / VBD_chart), clamped, so each
     player keeps the market's opinion of HIM and only the scoring is re-priced.
     Unlisted players get the fitted curve applied to VBD_league (model-only).
"""
import json, math, pathlib, datetime, collections, re
from weekly import get, API, LEAGUE, ME, SEASON

HERE = pathlib.Path(__file__).parent
CHART_DATE = "09/15/26"
CHART = {  # PeakedInHighSkool week 2, 4pt / 2QB / 1.0 PPR
 "RB": {"Jahmyr Gibbs":83,"Bijan Robinson":74.5,"Christian McCaffrey":70.5,"James Cook":68.5,"Jonathan Taylor":67,
  "Kenneth Walker":60,"Saquon Barkley":59,"Chase Brown":59,"Devon Achane":56.5,"Ashton Jeanty":56,"Derrick Henry":53.5,
  "Omarion Hampton":48.5,"Javonte Williams":44.5,"Breece Hall":41.5,"D'Andre Swift":41,"Kyren Williams":40.5,
  "Jeremiyah Love":38,"David Montgomery":36,"Travis Etienne":34,"Bucky Irving":32,"Cam Skattebo":31,"Quinshon Judkins":25.5,
  "Rhamondre Stevenson":23.5,"Bhayshul Tuten":23.5,"Jaylen Warren":23,"Jadarian Price":23,"TreVeyon Henderson":21,
  "Chuba Hubbard":19,"Rico Dowdle":18,"Tony Pollard":17,"Jordan Mason":14,"Josh Jacobs":13.5,"RJ Harvey":12.5,
  "Jonathon Brooks":10.5,"Kyle Monangai":10.5,"Blake Corum":9,"J.K. Dobbins":7.5,"MarShawn Lloyd":5,"Jacory Croskey-Merritt":2.5},
 "WR": {"Ja'Marr Chase":79,"Jaxon Smith-Njigba":70,"CeeDee Lamb":64.5,"Justin Jefferson":64,"Puka Nacua":64,"Nico Collins":54.5,
  "Amon-Ra St. Brown":51,"Chris Olave":49.5,"Malik Nabers":49,"Zay Flowers":47,"George Pickens":43,"Garrett Wilson":39.5,
  "Drake London":38.5,"Ladd McConkey":38.5,"DeVonta Smith":38,"Tee Higgins":34,"Rashee Rice":33,"Tetairoa McMillan":32,
  "Emeka Egbuka":32,"Christian Watson":31,"D.J. Moore":29.5,"Jaylen Waddle":29,"Mike Evans":29,"A.J. Brown":28.5,
  "Luther Burden":28,"Jameson Williams":27.5,"Parker Washington":27,"Davante Adams":21,"Terry McLaurin":20.5,"Stefon Diggs":19,
  "DK Metcalf":18.5,"Carnell Tate":18.5,"Rome Odunze":16.5,"Marvin Harrison":13.5,"Jalen Coker":10,"Chris Godwin":9.5,
  "Alec Pierce":5.5,"Deebo Samuel":1.5,"Michael Wilson":1},
 "TE": {"Trey McBride":56,"Brock Bowers":41,"Colston Loveland":28.5,"Sam LaPorta":26.5,"Tyler Warren":26.5,"Tucker Kraft":24,
  "Dalton Kincaid":19,"Isaiah Likely":18,"George Kittle":17,"Harold Fannin":16.5,"Dallas Goedert":16,"Travis Kelce":15.5,
  "Mark Andrews":14.5,"Juwan Johnson":14.5,"Kyle Pitts":14.5,"Dalton Schultz":13,"Jake Ferguson":11,"Brenton Strange":10.5,
  "Hunter Henry":10,"T.J. Hockenson":6.5},
 "QB": {"Josh Allen":82.5,"Lamar Jackson":81,"Caleb Williams":72.5,"Joe Burrow":68.5,"Drake Maye":59.5,"Jalen Hurts":55,
  "Trevor Lawrence":50.5,"Jayden Daniels":50.5,"Brock Purdy":45,"Dak Prescott":45,"Justin Herbert":44.5,"Jaxson Dart":42,
  "Patrick Mahomes":38,"Jared Goff":35.5,"Jordan Love":33,"Bo Nix":33,"Tyler Shough":33,"Matthew Stafford":31,
  "Baker Mayfield":30.5,"Bryce Young":28,"Malik Willis":25,"C.J. Stroud":24,"Kyler Murray":22,"Sam Darnold":21,
  "Daniel Jones":20,"Drew Lock":19.5,"Jacoby Brissett":19,"Cam Ward":17,"Aaron Rodgers":16.5,"Carson Wentz":15.5,
  "Geno Smith":13,"Kirk Cousins":12.5},
}
LEAGUE_REC = {"QB": .5, "RB": .5, "WR": 1.0, "TE": 1.5}
CHART_REC  = {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0}
POS = ["RB", "WR", "TE", "QB"]


def pts(s, rec):
    g = lambda k: float(s.get(k) or 0)
    return (g("pass_yd") * .04 + g("pass_td") * 4 - g("pass_int") + g("rush_yd") * .1 + g("rush_td") * 6
            + g("rec_yd") * .1 + g("rec_td") * 6 - g("fum_lost") * 2 + g("rec") * rec
            + 2 * (g("pass_2pt") + g("rush_2pt") + g("rec_2pt")))


def norm(s):
    s = (s or "").lower().replace(".", "").replace("'", "").replace("’", "").replace("-", " ")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def fit_power(xs, ys):
    """least squares on log-log: y = a * x^b"""
    pts_ = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    n = len(pts_); mx = sum(p[0] for p in pts_) / n; my = sum(p[1] for p in pts_) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts_); sxy = sum((p[0] - mx) * (p[1] - my) for p in pts_)
    b = sxy / sxx; a = math.exp(my - b * mx)
    ss_res = sum((y - a * x ** b) ** 2 for x, y in zip(xs, ys) if x > 0)
    ss_tot = sum((y - sum(ys) / len(ys)) ** 2 for y in ys)
    return a, b, 1 - ss_res / ss_tot


def main():
    week = int(get(f"{API}/state/nfl").get("week") or 1)
    players = get(f"{API}/players/nfl")
    rosters = get(f"{API}/league/{LEAGUE}/rosters")
    users = {u["user_id"]: u.get("display_name") for u in get(f"{API}/league/{LEAGUE}/users")}
    owner = {}
    for r in rosters:
        for p in r.get("players") or []: owner[str(p)] = users.get(r["owner_id"], "?")

    weeks = list(range(week, 18))
    tot_l, tot_c, gp = collections.Counter(), collections.Counter(), collections.Counter()
    for w in weeks:
        proj = get(f"{API}/projections/nfl/regular/{SEASON}/{w}")
        for pid, s in proj.items():
            pos = (players.get(pid) or {}).get("position")
            if pos not in POS or not s: continue
            tot_l[pid] += pts(s, LEAGUE_REC[pos]); tot_c[pid] += pts(s, CHART_REC[pos])
            if (s.get("gp") or 0) > 0: gp[pid] += 1

    rows = []
    for pid, pl in tot_l.items():
        v = players[pid]
        if not v.get("team") or pl < 15: continue
        rows.append({"id": pid, "n": v.get("full_name"), "p": v["position"], "t": v["team"], "age": v.get("age"),
                     "ptsL": round(pl, 1), "ptsC": round(tot_c[pid], 1), "ppgL": round(pl / max(gp[pid], 1), 1),
                     "own": owner.get(pid), "inj": v.get("injury_status") or ("NA" if v.get("status") == "Inactive" else None)})

    # replacement levels
    # Same definition on both sides (best free agent in THIS league) so the two
    # VBDs differ only by the scoring change, not by how "replacement" is drawn.
    repl_c, repl_l = {}, {}
    for p in POS:
        fa = [r for r in rows if r["p"] == p and not r["own"] and not r["inj"]]
        c = max(fa, key=lambda r: r["ptsC"]); l = max(fa, key=lambda r: r["ptsL"])
        repl_c[p] = c["ptsC"]; repl_c[p + "_name"] = c["n"]
        repl_l[p] = l["ptsL"]; repl_l[p + "_name"] = l["n"]
    for r in rows:
        r["vbdC"] = round(r["ptsC"] - repl_c[r["p"]], 1)
        r["vbdL"] = round(r["ptsL"] - repl_l[r["p"]], 1)

    # match chart names
    byname = {}
    for r in rows: byname.setdefault(norm(r["n"]), []).append(r)
    unmatched = []
    for p, d in CHART.items():
        for name, val in d.items():
            cands = [r for r in byname.get(norm(name), []) if r["p"] == p]
            if not cands: unmatched.append(name); continue
            cands[0]["chart"] = val
    if unmatched: print("unmatched chart names:", unmatched)

    # market curve per position (chart value vs chart-scoring VBD)
    fits = {}
    for p in POS:
        pts_ = [(r["vbdC"], r["chart"]) for r in rows if r["p"] == p and r.get("chart") and r["vbdC"] > 0]
        a, b, r2 = fit_power([x for x, _ in pts_], [y for _, y in pts_])
        fits[p] = {"a": a, "b": b, "r2": round(r2, 3), "n": len(pts_)}
    curve = lambda p, vbd: fits[p]["a"] * max(vbd, 0.01) ** fits[p]["b"]

    for r in rows:
        p = r["p"]
        model = curve(p, r["vbdL"]) if r["vbdL"] > 0 else 0.0
        if r.get("chart"):
            if r["vbdC"] > 5 and r["vbdL"] > 0:
                ratio = min(max(r["vbdL"] / r["vbdC"], .5), 1.8)
                adj = r["chart"] * ratio
            else:  # too little VBD to re-price multiplicatively; move the market number toward the model
                adj = .5 * r["chart"] + .5 * model
            r["adj"] = round(adj * 2) / 2; r["src"] = "chart"
        else:
            r["adj"] = round(model * 2) / 2; r["src"] = "model"
        r["delta"] = round(r["adj"] - r["chart"], 1) if r.get("chart") else None

    rows = [r for r in rows if r["adj"] >= 1 or r.get("chart") or r["own"] == users.get(ME)]
    rows.sort(key=lambda r: -r["adj"])
    out = {"built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "week": week, "chartDate": CHART_DATE,
           "fits": fits, "replL": repl_l, "replC": repl_c, "me": users.get(ME), "rows": rows}
    (HERE / "trade_data.js").write_text("window.TRADE=" + json.dumps(out) + ";", encoding="utf-8")
    for p in POS: print(p, fits[p], "repl:", repl_c[p + "_name"], repl_c[p], "->", repl_l[p + "_name"], repl_l[p])
    print(len(rows), "rows")


if __name__ == "__main__":
    main()
