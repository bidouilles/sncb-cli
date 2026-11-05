# sncb: Belgian trains in the terminal

`sncb` gives live SNCB/NMBS train times in the terminal: trips from A to B with
platforms, delays, changes and station notices, plus station boards, single
trains and disruptions. It ships with a Claude Code skill, so you can ask an
agent "I want to go from Charleroi to Louvain-la-Neuve, leaving now".

Data comes from the public [iRail API](https://docs.irail.be), which serves
SNCB's real-time data. You need no account or key, and the only requirement is
Python ≥ 3.9 (no third-party packages).

```
$ sncb Charleroi-Central Louvalaneuve --lang fr
'Louvalaneuve' → Louvain-la-Neuve
Charleroi-Central → Louvain-la-Neuve  ·  leaving from Thu 05 Nov 2026, 17:35 (Belgian time)

1. 17:39 → 18:38   59m · 1 change · IC 5717 + S4 6366  ●○○
   17:39      Charleroi-Central              pl. 3
             │ IC 5717 → Louvain  ●○○
   18:10      Ottignies                      pl. 10
             ┆ change at Ottignies, 21m
   18:31      Ottignies                      pl. 6
             │ S4 6366 → Louvain-la-Neuve  ●○○
   18:38      Louvain-la-Neuve               pl. 1
   ⚠ Ottignies : nous rénovons votre gare
```

## Quick start

1. Install [uv](https://docs.astral.sh/uv/) if you don't have it
   (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`).
2. Clone the repo anywhere and run the installer:

   ```bash
   git clone https://github.com/bidouilles/sncb-cli.git && cd sncb-cli
   ./install.sh
   ```

   If you only want the CLI, without the skill, you don't need to clone:
   `uv tool install git+https://github.com/bidouilles/sncb-cli`

3. Try it in the terminal, or ask Claude Code:

   ```bash
   sncb Charleroi-Central Ottignies
   ```

   > I want to go from Charleroi to Louvain-la-Neuve, I'm leaving now.

See [Ask the agent](#ask-the-agent) for more questions to try.

## Install

You need [uv](https://docs.astral.sh/uv/).

```bash
./install.sh                # CLI → ~/.local/bin/sncb, skill → ~/.claude/skills/sncb
./install.sh --completion   # same, plus zsh tab completion in ~/.zshrc
```

The CLI is installed in editable mode and the skill is a symlink to `skill/`,
so changes in this repo apply right away. To do it by hand:

```bash
uv tool install --editable .
ln -sfn "$PWD/skill" ~/.claude/skills/sncb
```

To run it without installing: `uv run sncb …` from this folder.

To uninstall:

```bash
uv tool uninstall sncb-cli
rm ~/.claude/skills/sncb
```

## Use

```bash
sncb Charleroi-Central Louvain-la-Neuve          # leave now
sncb ottignies "bruxelles midi" 17:30            # leave from 17:30
sncb gent brugge 8:00 --date tomorrow --arrive   # arrive by 8:00 tomorrow
sncb charleroi-central ottignies --details       # + intermediate stops, full notices
sncb charleroi-central ottignies --brief -n 6    # one line per trip
sncb Ottignies                                   # one station = its departure board
sncb board leuven 18:00 --arrivals               # arrival board
sncb train IC5717                                # all stops of one train
sncb stations brussels                           # find station names
sncb alerts ottignies -v                         # disruptions and planned works
```

- **Times** are Belgian time (Europe/Brussels), in and out, wherever you are.
- **Station names** can be partial, unaccented or misspelled ("Ottini" →
  Ottignies). When a name fits several stations ("Brussels", "Charleroi"),
  you get a numbered menu in a terminal. Without a terminal (scripts,
  agents) it prints the choices and exits with code **2**.
- **Language:** `--lang fr|nl|de|en` sets the language of station names and
  notices. The default is `$SNCB_LANG`, else `en`.
- `--json` prints the raw API reply.

### Shortcuts

```bash
sncb shortcut add work ottignies brussels-central   # a route
sncb shortcut add home ottignies                    # one station = its board
sncb work 8:00 --date tomorrow
sncb shortcut list
sncb shortcut rm work
```

Shortcuts are saved in `~/.config/sncb/shortcuts.json` by station ID, so they
work in any `--lang`.

### Tab completion (zsh)

Completes commands, shortcuts and station names:

```bash
eval "$(sncb completion zsh)"     # in ~/.zshrc (or ./install.sh --completion)
```

## Ask the agent

Once the skill is installed, ask Claude Code in plain words, in English,
French or Dutch. The skill (`skill/SKILL.md`) picks the right command and
answers like a station screen: the next train first (time, platform, train,
changes, arrival), then one or two later options.

### Getting somewhere

| You ask | The agent runs |
| --- | --- |
| I want to go from Charleroi to Louvain-la-Neuve, I'm leaving now. | asks "Charleroi-Central or Charleroi-Ouest?", then `sncb Charleroi-Central Louvain-la-Neuve` |
| Trains from Ottignies to Leuven after 17:30? | `sncb Ottignies Leuven 17:30` |
| I need to be in Ghent by 9 tomorrow. When do I leave Brussels-Midi? | `sncb Brussels-Midi Gent-Sint-Pieters 9:00 --date tomorrow --arrive` |
| How do I get from Namur to Liège on Saturday morning? | `sncb Namur Liège-Guillemins 8:00 --date 07/11` |
| Prochain train de Mons vers Bruxelles ? | `sncb Mons Bruxelles --lang fr` (then asks: which Brussels station?) |

When a name fits several stations ("Brussels", "Charleroi", "Liège"), the
agent asks which one you mean instead of guessing. Close spellings are fine:
"Ottini" or "Louvalaneuve" work.

### On the platform

| You ask | The agent runs |
| --- | --- |
| Which platform for my train to Ottignies? | `sncb <your station> Ottignies` |
| What are the stops between Charleroi and Ottignies? | `sncb Charleroi-Central Ottignies --details` |
| Is the IC 5717 late? Where is it now? | `sncb train IC5717` |
| What leaves Ottignies in the next half hour? | `sncb board Ottignies` |
| What arrives in Leuven after 18:00? | `sncb board Leuven 18:00 --arrivals` |

### Problems on the line

| You ask | The agent runs |
| --- | --- |
| Any problems on the trains today? | `sncb alerts` |
| Are there works around Ottignies? | `sncb alerts ottignies -v` |

### Your usual trips

| You ask | The agent runs |
| --- | --- |
| Save my commute: Ottignies to Brussels-Central, call it "work". | `sncb shortcut add work Ottignies Brussels-Central` |
| When's my next train to work? | `sncb shortcut list`, then `sncb work` |
| I want to be at work by 8:30 tomorrow. | `sncb work 8:30 --date tomorrow --arrive` |

All times are Belgian time, even if you ask from another time zone.

## Layout

| Path | What |
| --- | --- |
| `src/sncb_cli/__init__.py` | The CLI: one file, standard library only |
| `pyproject.toml` | Package metadata and the `sncb` entry point |
| `skill/SKILL.md` | Claude Code skill (`~/.claude/skills/sncb` → `skill/`) |
| `install.sh` | Installs the CLI and the skill, optionally zsh completion |
| `AGENTS.md` | Notes for coding agents working on this repo |

Cached station list: `~/.cache/sncb-cli/stations-<lang>.json` (refreshed
weekly).

## Credits

Data: [iRail](https://irail.be) (open source, SNCB/NMBS real-time data).
Shortcuts, the station board shortcut and shell completion were inspired by
[commandtrein](https://github.com/Kaya-Sem/commandtrein).

## License

MIT. See `LICENSE`.
