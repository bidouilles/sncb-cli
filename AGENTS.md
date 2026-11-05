# AGENTS.md

`sncb`: a CLI for live Belgian train times (SNCB/NMBS) on the iRail API,
plus a Claude Code skill. See `README.md` for usage and `skill/SKILL.md` for
how an agent should phrase answers.

## Project

- `src/sncb_cli/__init__.py` is the whole CLI: one file, Python ≥ 3.9,
  **standard library only**. Don't add dependencies.
- Installed with `./install.sh`: `uv tool install --editable .` puts it in
  `~/.local/bin/sncb`, and `~/.claude/skills/sncb` is a symlink to `skill/`.
  Both are editable, so changes apply right away without reinstalling.
  Run from the repo with `uv run sncb …`.
- No absolute paths in the repo or the skill: it must work wherever it's
  cloned. `install.sh` works from its own folder, and the skill finds the
  repo by resolving its own symlink.

## Data source

- iRail API, `https://api.irail.be/v1/{connections,liveboard,vehicle,stations,disturbances}/?format=json`.
  Docs: https://docs.irail.be. Values come back as strings (`"0"`/`"1"`,
  unix timestamps, delays in seconds).
- iRail sometimes answers with an **HTML page instead of JSON** (Cloudflare /
  rate limiting, roughly more than 3 requests per second). `api()` retries up
  to 4 times. When testing, leave a second between calls.
- Don't switch to the belgiantrain.be website endpoints. They need browser
  cookies (Cloudflare clearance and a CSRF token) and break within minutes.
- The User-Agent is a generic `sncb-cli/0.1 (…)`. Don't put personal contact
  details in it.

## Behaviour to keep

- **Belgian time everywhere.** Input times are interpreted in Europe/Brussels
  and output is shown in it, whatever the machine's time zone.
- **Station resolution** (`resolve_station`): exact name, then prefix, then
  all words, then substring, then a fuzzy `difflib` match (≥ 0.75) for typos
  and spellings from speech. If several stations tie for the best score, it
  **must not guess**: it shows a menu on a TTY, otherwise prints
  `AMBIGUOUS STATION: …` with the choices on stderr and exits **2**. The
  skill relies on that exit code to ask the user.
- Arrive-by (`--arrive`): iRail returns trips in ascending order up to the
  target time, so request 6 and keep the **last** N.
- Argument short forms in `main()`: a shortcut name comes first; otherwise one
  station (optionally followed by a time) means `board`, and two stations
  mean `trip`.
- Shortcuts are stored by station **ID** in `~/.config/sncb/shortcuts.json`
  (or `$XDG_CONFIG_HOME/sncb`), so they work in every `--lang`.

## Checking changes

There's no test suite. Run the real commands against the live API, a second
apart:

```bash
uv run sncb Charleroi-Central Louvalaneuve --lang fr --details -n 2   # fuzzy name, change, notices
uv run sncb Ottini Brussels </dev/null; echo $?                       # ambiguity → exit 2
uv run sncb Ottignies Brussels-Central 8:00 --date tomorrow --arrive -b
uv run sncb Ottignies -n 3                                            # single station → board
uv run sncb train IC5717 && uv run sncb alerts | head
XDG_CONFIG_HOME=$(mktemp -d) uv run sncb shortcut add t ottignies leuven   # don't touch the real config
```

Keep `README.md` and `skill/SKILL.md` in step with CLI changes, then commit.
