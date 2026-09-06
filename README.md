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
| **Draft board** | The full snake grid, round by round, filling in as picks land. Your column is outlined |
| **Teams** | All 12 rosters by slot, each with the starting spots it still needs |

Team names are editable under **League setup & team names** and persist with the draft.
- Everything persists in `localStorage`, so a refresh mid-draft costs nothing.
  `Undo` steps back one pick; `Reset` clears the draft.

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

Availability uses **Sleeper 2QB ADP**. ADP is a crowd average, not a promise — the dots
are odds, not facts.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app — no build step, no dependencies |
| `data.js` | 231 players: value, projected points, tier, team, bye, superflex ADP |

## Setup

Open **League setup** at the bottom right to change teams, your draft slot, or rounds.
It defaults to 12 teams, slot 7, 14 rounds.

> Draft slot 7 came from the CSG xlsm. The Google copy of CSG showed a different order —
> confirm which is real before trusting the pick numbers.

## Refreshing the data

`data.js` is generated from the configured `DraftSheets_2026.xlsx` (values) joined to the
CSG sheet's `Sleep2QB` column (ADP). Both are point-in-time as of 2026-09-05.
