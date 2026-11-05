---
name: sncb
description: Belgian train times (SNCB/NMBS) via the `sncb` CLI — next trains from one station to another, leave-now or leave/arrive at a given time, platforms, delays, changes, intermediate stops, station departure/arrival boards, one train's stops, and current disruptions. Use when the user asks about trains in Belgium, e.g. "I want to go from Charleroi to Louvain-la-Neuve", "next train to Brussels", "when do I need to leave to be in Ghent by 9", "is my IC 5717 late", "which platform", "any problems on the line", or mentions SNCB, NMBS, belgiantrain, iRail.
---

# SNCB train times

`sncb` is a command on the PATH (installed with uv). It reads live SNCB/NMBS
data from the public iRail API (no login, no key).

If `command -v sncb` finds nothing, install it from the repo this skill lives
in. `install.sh` links this skill folder to `<repo>/skill`, so resolving the
link and going up one level finds the clone, wherever it is:

```bash
sh "$(cd -P "<this skill's base directory>" && cd .. && pwd)/install.sh"
```

If there is no `install.sh` there (the skill folder was copied rather than
linked), ask the user where they cloned the repo and run its `install.sh`.

All times are **Belgian time** (Europe/Brussels), both what you pass in and
what comes out. The user may be in another time zone: say "Belgian time" when
it could be unclear.

## Commands

```bash
sncb "<from>" "<to>"                        # leave now: next 4 trips, every leg
sncb "<from>" "<to>" 17:30                  # leave from 17:30
sncb "<from>" "<to>" 8:00 --arrive          # arrive by 8:00
sncb "<from>" "<to>" 9:15 --date tomorrow   # --date: today, tomorrow, DD/MM, DD/MM/YYYY
sncb "<from>" "<to>" --details              # + intermediate stops and full notices
sncb "<from>" "<to>" --brief -n 6           # one line per trip
sncb board "<station>" [HH:MM]              # departure board (--arrivals for arrivals)
sncb train IC5717                           # all stops of one train, with delays
sncb stations "<text>"                      # look up station names
sncb alerts ["<station or line>"] [-v]      # current disruptions / planned works
sncb shortcut list                          # the user's saved routes (e.g. work, home)
sncb <shortcut> [HH:MM]                     # run a saved route
sncb shortcut add <name> "<from>" ["<to>"]  # save one (only when the user asks)
```

When the user says "my commute", "going to work", "home", or another name
that isn't a station, run `sncb shortcut list` first and use the matching
shortcut.

Add `--lang fr` (or `nl`, `de`) to get station names and notices in that
language. Match the language the user is speaking: French → `--lang fr`.

## Station names

Pass the user's words as they are. Partial names, accents and spellings from
speech are handled ("Ottini" → Ottignies, "Louvalaneuve" → Louvain-la-Neuve).
A resolved guess is printed on stderr as `'ottini' → Ottignies`.

**When a name fits several stations, the command exits with code 2** and
prints:

```
AMBIGUOUS STATION: 'Brussels' matches several stations. Which one?
  - Brussels-North
  - Brussels-Central
  - Brussels-South/Brussels-Midi
  ...
```

Then **ask the user which one**, offering the 3-5 most likely (main stations
are listed first). Do not pick one yourself, unless the conversation already
says which (they said "Midi", "Gare du Nord", "Central", or named it earlier).
Once they answer, re-run with the exact name from the list.

## How to answer

Run the trip command without `--json`; the text output is meant to be read.
For "I want to leave now" or "from X to Y", answer like a station screen:

- **Next train first**: departure time and platform, train (IC 5717) and its
  direction, arrival time and platform. For a change, give the station, the
  wait, and the platform of the next train.
- Delays (`+5'`), platform changes, `CANCELLED`, and the ⚠ station notices
  (works, longer walk to the platforms) when they matter.
- Then 1-2 later options in one line each (time → time, duration, changes).
- Mention intermediate stops only when asked (use `--details`).

Keep it short. Don't paste the raw output.

## Errors

- Exit 2 → ambiguous station, ask the user (see above).
- `no station matches` → run `sncb stations "<part of name>"` and suggest names.
- `could not reach iRail` → the API is down or rate-limited. Wait a few
  seconds and try once more, then say so. The CLI already retries.
