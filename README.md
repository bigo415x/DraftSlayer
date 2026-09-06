# Draft Slayer — Loser Squad 2026

A live draft board for a 12-team, keeper, superflex league. Built to run as a static
GitHub Pages site so it works from a phone or a second screen during the draft.

**Live site:** https://bigo415x.github.io/DraftSlayer/

## What it does

Four position columns like the CSG sheet, plus the one thing Draft Slayer does well:
it tells you **what to pick right now** and why.

- **Click a player** to draft him. He's assigned to whoever is on the clock, and the
  draft advances one pick. That keeps the available pool honest without any extra bookkeeping.
- **The red banner** is the recommendation — highest VONA among reachable players.
- **Colored dots** answer "will he still be there when I pick again?"
  green = should last, amber = coin flip, red = gone.
- **Your roster** fills the real lineup (QB / RB / RB / WR / WR / TE / FLEX / SUPERFLEX + 6 bench).

Three tabs:

| Tab | What it shows |
|---|---|
| **Make a pick** | Four position columns, the recommendation banner, your roster |
| | `Sort: VALUE / VONA` toggles what the columns are ordered by. In VONA mode each player carries his **overall VONA rank** across all four positions — top 5 in red |
| **Draft board** | The full snake grid, round by round, filling in as picks land. Your column is outlined |
| **Teams** | All 12 rosters by slot, each with the starting spots it still needs |
| **Strategy** | Board shape, a plan for each draft-slot range (1-3 / 4-6 / 7-9 / 10-12), and the rules that hold regardless of slot |

Team names are editable under **League setup & team names** and persist with the draft.
- Everything persists in `localStorage`, so a refresh mid-draft costs nothing.
  `Undo` steps back one pick; `Reset` clears the draft.

## The two numbers on every row

Each column is headed `Player | VONA | VAL`.

- **VAL** — value over replacement. Static, computed before the draft from this league's scoring.
  Allen is 138 at pick 1 and 138 at pick 100. It answers *who is genuinely most valuable here*.
- **VONA** — value over next available. Recomputed after every pick against what ADP says will
  survive until your next turn. It answers *what do I lose by waiting*. Sort by it to rank the
  board live.

So `Josh Allen +68 138` reads: he is 138 points above a replacement QB, and taking him now rather
than at your next pick gains you 68.

**The whole row is tinted by tier**, in that column's own colour, fading as the tier deepens —
so a block of same-coloured rows *is* a tier, and the moment the colour steps down is a cliff you
can see without reading a number. Players inside one tier are near-interchangeable; the drop
*between* tiers is what costs you, so the last player in a tier is the one worth reaching for.

VONA is set larger than VAL and turns red when positive, because it is the number you act on.
Player names quoted in the recommendation carry the same tier tint they have on the board, so the
banner and the columns read as one thing.

Hover any row for the full picture: projection, VAL, VONA, 2025 production and snap share, who he
backs up, and the injury note.

## The numbers

`VAL` is VBD from `DraftSheets_2026`, configured for this league's actual scoring —
superflex on, **WR 1.0 / TE 1.5 / RB 0.5 per reception**, 4-point passing TDs, −1 per
interception. That matters: generic rankings misprice this league badly, undervaluing
tight ends and treating quarterbacks as a one-slot position.

`VONA` is Value Over Next Available — this player's projected points minus the best
player at his position expected to survive until your next pick, plus half the same
comparison against the pick after that, then scaled by what your roster still needs.
It answers "how much do I lose by waiting?" rather than "who is best?", which is the
only question that matters when you're on the clock.

**Injury designations** (Q / OUT / IR / SUSP) come from ESPN's public injuries feed, pulled
2026-09-05. Hover a badge for the beat-writer note behind it. They are displayed, not baked
into the value — a questionable tag is information for you, not a number the model should
quietly apply on your behalf.

Availability uses **Sleeper 2QB ADP**. ADP is a crowd average, not a promise — the dots
are odds, not facts.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app — no build step, no dependencies |
| `data.js` | 814 players — 231 projected (value, points, tier, bye, superflex ADP) plus 583 depth players from Sleeper's roster feed |

## Live sync

`Sync: ON` polls Sleeper every 5 seconds for the league's draft — it discovers the draft id
itself, so a recreated draft is picked up automatically. Picks, team count and round count come
straight from Sleeper; once the commissioner sets the draft order it also fills in **every team
name and your own draft slot**.

Manual clicking is disabled while sync is on, because Sleeper owns the pick list. Toggle it off
and the board reverts to click-to-draft with whatever it last pulled.

Sync needs a real origin, so it works on the **GitHub Pages site**, not inside a Claude Artifact
(artifact CSP blocks outbound fetch).

## Unprojected players and contingent value

Every rostered player now carries a value. The 231 from DraftSheets are the spine. The other 575
are **estimated**: Sleeper's own 2026 projections, scored with this league's exact rules, then
calibrated onto the DraftSheets scale by the per-position median ratio (QB 0.89, RB 0.94, WR 0.85,
TE 0.82 — Sleeper projects 18 games and runs optimistic). They render in italic so you always know
which number you are looking at, and 8 players with no projection from either source show `—`.

Each also carries **2025 actual points under this league's scoring**, games played and snap share,
so a name you don't recognize comes with evidence rather than a shrug.

Backups additionally show
his **depth-chart role and the starter he sits behind**, and where that starter is projected,
an inherited value: `→44`.

> `Jake Tonges · SF · TE2 behind George Kittle (Q) · →44`

He is worth nothing as a bench tight end and roughly a 44-value starter the day Kittle misses a
game. Those are two different numbers and the board shows both rather than averaging them into
one misleading figure. 262 players carry a named starter ahead of them.

## Depth players

The 231 projected players come from DraftSheets. Everyone else on an NFL roster at QB/RB/WR/TE
is merged in from Sleeper's public player feed and marked `d:1` — no projection, no value, never
recommended. They stay hidden until you search for one.

That matters because the board tracks the whole draft: when a rival takes a fifth-string tight
end, you still need to record it or every later pick is misattributed. Search the name, click it,
carry on.

## Setup

Open **League setup** at the bottom right to change teams, your draft slot, or rounds.
It defaults to 12 teams, slot 7, 14 rounds.

> Draft slot 7 came from the CSG xlsm. The Google copy of CSG showed a different order —
> confirm which is real before trusting the pick numbers.

## Refreshing the data

`data.js` is generated from the configured `DraftSheets_2026.xlsx` (values) joined to the
CSG sheet's `Sleep2QB` column (ADP). Both are point-in-time as of 2026-09-05.
