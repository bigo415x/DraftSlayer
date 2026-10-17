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
CHART_DATE = "09/29/26"
CHART = {  # PeakedInHighSkool week 4, 4pt / 2QB / 1.0 PPR
 "RB": {"Jahmyr Gibbs":80.5,"Bijan Robinson":79.5,"Kenneth Walker":78,"Jonathan Taylor":73,"Christian McCaffrey":68,
  "Derrick Henry":63.5,"James Cook":62.5,"Ashton Jeanty":61.5,"Chase Brown":58,"Javonte Williams":52,"D'Andre Swift":50.5,
  "Saquon Barkley":47,"Kyren Williams":45,"Jeremiyah Love":44.5,"Breece Hall":39.5,"Bucky Irving":39.5,"Omarion Hampton":39,
  "Chuba Hubbard":35,"Cam Skattebo":34.5,"Bhayshul Tuten":31.5,"David Montgomery":31,"Jaylen Warren":27.5,
  "TreVeyon Henderson":25.5,"Travis Etienne":24,"Quinshon Judkins":24,"Aaron Jones":23,"Rhamondre Stevenson":21.5,
  "Jadarian Price":21.5,"Tony Pollard":20.5,"Josh Jacobs":20,"RJ Harvey":19,"Blake Corum":18.5,"Kyle Monangai":18.5,
  "Rachaad White":18,"Jacory Croskey-Merritt":17.5,"J.K. Dobbins":14.5,"Rico Dowdle":14,"Woody Marks":13,"Jordan Mason":12.5,
  "Alvin Kamara":11,"MarShawn Lloyd":8.5,"Jonah Coleman":7,"Kenneth Gainwell":3,"Tyler Allgeier":3,"Zach Charbonnet":1,
  "Emmett Johnson":0.5},
 "WR": {"Jaxon Smith-Njigba":80.5,"Ja'Marr Chase":76.5,"Amon-Ra St. Brown":73.5,"CeeDee Lamb":71,"Chris Olave":68,
  "Puka Nacua":68,"Justin Jefferson":60,"Drake London":55,"Nico Collins":53,"Zay Flowers":51,"Garrett Wilson":47,
  "DeVonta Smith":46.5,"George Pickens":43,"Christian Watson":43,"Parker Washington":39,"Davante Adams":38,"Tee Higgins":36,
  "Malik Nabers":35.5,"Rashee Rice":33,"Tetairoa McMillan":33,"Jaylen Waddle":32.5,"D.J. Moore":30.5,"Ladd McConkey":30.5,
  "Matthew Golden":29.5,"Emeka Egbuka":29.5,"Jalen Coker":28,"A.J. Brown":27.5,"Terry McLaurin":26.5,"Luther Burden":26.5,
  "Mike Evans":25.5,"Michael Wilson":25.5,"Jameson Williams":24.5,"Josh Downs":24,"Stefon Diggs":23,"DK Metcalf":21,
  "Deebo Samuel":20,"Carnell Tate":20,"Denzel Boston":20,"Rome Odunze":19,"Jakobi Meyers":17.5,"Jordan Addison":17.5,
  "Devaughn Vele":17.5,"Courtland Sutton":17,"Chris Godwin":17,"KC Concepcion":16.5,"Wan'Dale Robinson":16,"Jordyn Tyson":15.5,
  "Adonai Mitchell":15,"Dontayvion Wicks":14.5,"Brian Thomas":14,"Xavier Worthy":13.5,"Romeo Doubs":12,"Tre Tucker":12,
  "Khalil Shakir":9.5,"Malik Washington":6.5,"Quentin Johnston":6,"Michael Pittman":4.5,"Marvin Harrison":4.5,"Tre Harris":4.5,
  "Rashod Bateman":2.5,"Keenan Allen":2},
 "TE": {"Brock Bowers":53.5,"Trey McBride":51.5,"Tyler Warren":31.5,"Dalton Kincaid":27.5,"George Kittle":24.5,"Sam LaPorta":24,
  "Travis Kelce":20.5,"Juwan Johnson":17.5,"Colston Loveland":17,"Tucker Kraft":16.5,"Harold Fannin":16.5,"Isaiah Likely":15.5,
  "Dalton Schultz":15,"Jake Ferguson":14,"Mark Andrews":13.5,"Kenyon Sadiq":11.5,"Kyle Pitts":10.5,"Dallas Goedert":10},
 "QB": {"Josh Allen":83,"Lamar Jackson":78.5,"Joe Burrow":68,"Brock Purdy":60.5,"Patrick Mahomes":58,"Jalen Hurts":55,
  "Dak Prescott":53,"Caleb Williams":50,"Tyler Shough":49.5,"Trevor Lawrence":48.5,"Jared Goff":47,"Drake Maye":42.5,
  "Matthew Stafford":36.5,"Jordan Love":35,"Bryce Young":34.5,"Bo Nix":33,"Justin Herbert":32.5,"C.J. Stroud":29,
  "Jayden Daniels":28.5,"Sam Darnold":24.5,"Baker Mayfield":22.5,"Malik Willis":21.5,"Kyler Murray":21,"Kirk Cousins":20.5,
  "Geno Smith":19.5,"Daniel Jones":19,"Jacoby Brissett":18.5,"Michael Penix":18,"Cam Ward":15.5,"Aaron Rodgers":13,
  "Deshaun Watson":13},
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
            if LEAGUE_REC[p] == CHART_REC[p]:  # same scoring as the chart: nothing to re-price
                adj = r["chart"]
            elif r["vbdC"] > 5 and r["vbdL"] > 0:
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
