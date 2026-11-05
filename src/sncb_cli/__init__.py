#!/usr/bin/env python3
"""sncb — Belgian train (SNCB/NMBS) times from the terminal.

Data comes from the iRail API (https://api.irail.be), which serves
SNCB/NMBS real-time data. Times are shown in Belgian time.

Examples:
  sncb Charleroi-Central Ottignies            next trains from A to B
  sncb charleroi ottignies 17:29              trains leaving from 17:29
  sncb gent brugge 8:00 --date tomorrow --arrive   arrive by 8:00 tomorrow
  sncb board "Brussels-Central"               departure board
  sncb board leuven --arrivals                arrival board
  sncb train IC1538                           stops of one train
  sncb stations namur                         find station names
  sncb alerts                                 current disruptions
"""

import argparse
import datetime as dt
import difflib
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

API = "https://api.irail.be/v1"
USER_AGENT = "sncb-cli/0.1 (personal command-line tool)"
TZ = ZoneInfo("Europe/Brussels")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "sncb-cli")
STATIONS_TTL = 7 * 24 * 3600
COMMANDS = {"trip", "board", "train", "stations", "alerts", "shortcut", "completion"}
CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"), "sncb")
SHORTCUTS_FILE = os.path.join(CONFIG_DIR, "shortcuts.json")


# ── output helpers ──────────────────────────────────────────────────────────

class C:
    on = sys.stdout.isatty() and not os.environ.get("NO_COLOR")

    @staticmethod
    def wrap(code, s):
        return f"\033[{code}m{s}\033[0m" if C.on else s

    bold = staticmethod(lambda s: C.wrap("1", s))
    dim = staticmethod(lambda s: C.wrap("2", s))
    red = staticmethod(lambda s: C.wrap("31", s))
    green = staticmethod(lambda s: C.wrap("32", s))
    yellow = staticmethod(lambda s: C.wrap("33", s))
    cyan = staticmethod(lambda s: C.wrap("36", s))
    strike = staticmethod(lambda s: C.wrap("9", s))


def die(msg, code=1):
    print(C.red("error: ") + msg, file=sys.stderr)
    sys.exit(code)


def hhmm(ts):
    return dt.datetime.fromtimestamp(int(ts), TZ).strftime("%H:%M")


def delay_str(delay):
    d = int(delay or 0) // 60
    return C.red(f"+{d}'") if d > 0 else ""


def dur_str(seconds):
    m = int(seconds) // 60
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m}m"


def is_on(v):
    return str(v) == "1"


def platform_str(info, plain=None):
    if not info and not plain:
        return ""
    name = (info or {}).get("name", plain) or ""
    if not name or name == "?":
        return ""
    changed = info and str(info.get("normal", "1")) == "0"
    s = f"pl. {name}"
    return C.yellow(s + " (changed)") if changed else s


def occupancy_str(occ):
    name = (occ or {}).get("name", "")
    return {"low": C.green("●○○"), "medium": C.yellow("●●○"), "high": C.red("●●●")}.get(name, "")


def vlen(s):
    """Visible length (ignoring ANSI codes)."""
    out, esc = 0, False
    for ch in s:
        if ch == "\033":
            esc = True
        elif esc and ch == "m":
            esc = False
        elif not esc:
            out += 1
    return out


def pad(s, width):
    return s + " " * max(0, width - vlen(s))


# ── API ─────────────────────────────────────────────────────────────────────

def api(endpoint, **params):
    params = {k: v for k, v in params.items() if v is not None}
    params.setdefault("format", "json")
    url = f"{API}/{endpoint}/?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last_err = None
    for attempt in range(4):
        if attempt:
            time.sleep(1.5 * attempt)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                msg = json.loads(body).get("message", body)
            except ValueError:
                msg = body[:200]
            if e.code == 429 or e.code >= 500:
                last_err = f"HTTP {e.code}: {msg}"
                continue
            die(f"iRail said: {msg} (HTTP {e.code})")
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = str(getattr(e, "reason", e))
            continue
        try:
            return json.loads(body)
        except ValueError:
            # Rate-limited requests get an HTML page instead of JSON.
            last_err = "got a non-JSON reply (probably rate-limited)"
            continue
    die(f"could not reach iRail: {last_err}")


# ── stations ────────────────────────────────────────────────────────────────

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(ch if ch.isalnum() else " " for ch in s).split()


def load_stations(lang):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"stations-{lang}.json")
    try:
        if time.time() - os.path.getmtime(path) < STATIONS_TTL:
            with open(path) as f:
                return json.load(f)
    except (OSError, ValueError):
        pass
    data = api("stations", lang=lang)["station"]
    stations = [{"id": s["id"], "name": s["name"], "standardname": s["standardname"]} for s in data]
    try:
        with open(path, "w") as f:
            json.dump(stations, f)
    except OSError:
        pass
    return stations


MAIN_HINTS = ("central", "centraal", "centrale", "zuid", "midi", "sud", "south", "noord", "nord", "north",
              "sint pieters", "guillemins")


def scored_stations(query, lang):
    """Return [(score, station)], best first. Lower score = better match."""
    q = norm(query)
    if not q:
        return []
    qs = " ".join(q)
    scored = []
    stations = load_stations(lang)
    for s in stations:
        best = None
        for name in {s["name"], s["standardname"]}:
            n = norm(name)
            ns = " ".join(n)
            if ns == qs:
                score = 0
            elif ns.startswith(qs):
                score = 1
            elif all(any(w.startswith(t) for w in n) for t in q):
                score = 2
            elif qs in ns:
                score = 3
            else:
                continue
            best = score if best is None else min(best, score)
        if best is not None:
            scored.append((best, s))
    if not scored:
        # Typos / spoken spellings ("louvalaneuve", "ottini"): fuzzy match on squashed names.
        squashed = "".join(q)
        for s in stations:
            ratio = max(difflib.SequenceMatcher(None, squashed, "".join(norm(n))).ratio()
                        for n in {s["name"], s["standardname"]})
            if ratio >= 0.75:
                scored.append((round(5 - ratio, 2), s))

    def key(item):
        score, st = item
        main = any(h in " ".join(norm(st["name"] + " " + st["standardname"])) for h in MAIN_HINTS)
        return (score, not main, len(st["name"]), st["name"])

    scored.sort(key=key)
    return scored


def search_stations(query, lang):
    return [s for _, s in scored_stations(query, lang)]


def resolve_station(query, lang):
    """Find the one station meant by `query`; ask (or exit 2) when several fit equally well."""
    if query.startswith("BE.NMBS."):
        for st in load_stations(lang):
            if st["id"] == query:
                return st
        die(f"unknown station id {query}")
    scored = scored_stations(query, lang)
    if not scored:
        die(f"no station matches '{query}'. Try: sncb stations <part of the name>")
    best = scored[0][0]
    # For typos, anything within 0.05 of the best fuzzy score is also a candidate.
    top = [st for sc, st in scored if sc == best or (best >= 4 and sc - best < 0.05)]
    if len(top) == 1:
        st = top[0]
        if best > 0:
            print(C.dim(f"'{query}' → {st['name']}"), file=sys.stderr)
        return st
    top = top[:12]
    if sys.stdin.isatty() and sys.stdout.isatty():
        print(C.bold(f"'{query}' matches several stations. Which one?"), file=sys.stderr)
        for i, st in enumerate(top, 1):
            print(f"  {i:>2}. {st['name']}", file=sys.stderr)
        while True:
            try:
                ans = input(f"Number [1-{len(top)}, Enter = 1]: ").strip()
            except EOFError:
                sys.exit(2)
            if not ans:
                return top[0]
            if ans.isdigit() and 1 <= int(ans) <= len(top):
                return top[int(ans) - 1]
    print(f"AMBIGUOUS STATION: '{query}' matches several stations. Which one?", file=sys.stderr)
    for st in top:
        print(f"  - {st['name']}", file=sys.stderr)
    print("Re-run with the exact name.", file=sys.stderr)
    sys.exit(2)


# ── date / time parsing ─────────────────────────────────────────────────────

def parse_time(s):
    s = s.strip().lower().replace("h", ":").replace(".", ":")
    if s == "now":
        return None
    if ":" in s:
        h, _, m = s.partition(":")
        m = m or "0"
    elif len(s) in (3, 4) and s.isdigit():
        h, m = s[:-2], s[-2:]
    elif s.isdigit():
        h, m = s, "0"
    else:
        raise ValueError
    h, m = int(h), int(m)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError
    return dt.time(h, m)


def looks_like_time(s):
    try:
        parse_time(s)
        return True
    except ValueError:
        return False


def parse_date(s):
    today = dt.datetime.now(TZ).date()
    s = s.strip().lower()
    if s in ("today", "auj", "aujourd'hui", "vandaag"):
        return today
    if s in ("tomorrow", "demain", "morgen"):
        return today + dt.timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    for fmt in ("%d/%m", "%d-%m", "%d.%m"):
        try:
            d = dt.datetime.strptime(s, fmt).date().replace(year=today.year)
            return d if d >= today - dt.timedelta(days=1) else d.replace(year=today.year + 1)
        except ValueError:
            pass
    raise ValueError


def when_params(args):
    """Return (date, time, label) in Belgian time for the API."""
    now = dt.datetime.now(TZ)
    try:
        d = parse_date(args.date) if args.date else now.date()
    except ValueError:
        die(f"can't read date '{args.date}' (use DD/MM, DD/MM/YYYY, today, tomorrow)")
    try:
        t = parse_time(args.time) if args.time else None
    except ValueError:
        die(f"can't read time '{args.time}' (use HH:MM, e.g. 17:29)")
    if t is None:
        t = now.time() if d == now.date() else dt.time(0, 0)
    label = dt.datetime.combine(d, t).strftime("%a %d %b %Y, %H:%M")
    return d.strftime("%d%m%y"), t.strftime("%H%M"), label


# ── commands ────────────────────────────────────────────────────────────────

def leg_list(c):
    """Split a connection into legs: [(departure_point, arrival_point), ...]."""
    legs, cur = [], c["departure"]
    for v in (c.get("vias") or {}).get("via", []):
        legs.append((cur, v["arrival"], v))
        cur = v["departure"]
    legs.append((cur, c["arrival"], None))
    return legs


def train_name(point):
    vi = point.get("vehicleinfo") or {}
    name = vi.get("shortname") or (point.get("vehicle") or "").replace("BE.NMBS.", "")
    if is_on(point.get("walking")):
        return "walk"
    return name


def point_line(ts, delay, station, platform_info, platform, canceled=False, indent="   "):
    t = pad(f"{hhmm(ts)} {delay_str(delay)}".rstrip(), 10)
    line = f"{indent}{C.bold(t)} {pad(C.bold(station), 30)} {platform_str(platform_info, platform)}"
    return C.strike(line) + "  " + C.red("CANCELLED") if canceled else line


def cmd_trip(args):
    a = resolve_station(args.origin, args.lang)
    b = resolve_station(args.destination, args.lang)
    date, tm, label = when_params(args)
    data = api("connections", **{"from": a["id"], "to": b["id"]}, date=date, time=tm,
               timesel="arrival" if args.arrive else "departure", lang=args.lang,
               results=max(args.number, 6) if args.arrive else args.number)
    if args.json:
        return print(json.dumps(data, indent=2, ensure_ascii=False))
    conns = data.get("connection", [])
    # Arrive-by returns trips in ascending order up to the target: keep the latest ones.
    conns = conns[-args.number:] if args.arrive else conns[: args.number]
    mode = "arriving by" if args.arrive else "leaving from"
    print(C.bold(f"{a['name']} → {b['name']}") + C.dim(f"  ·  {mode} {label} (Belgian time)"))
    if not conns:
        return print("No trains found.")
    for i, c in enumerate(conns, 1):
        dep, arr = c["departure"], c["arrival"]
        legs = leg_list(c)
        changes = len(legs) - 1
        cancelled = any(is_on(p.get("canceled")) for leg in legs for p in leg[:2])
        times = (f"{hhmm(dep['time'])}{' ' + delay_str(dep.get('delay')) if delay_str(dep.get('delay')) else ''}"
                 f" → {hhmm(arr['time'])}{' ' + delay_str(arr.get('delay')) if delay_str(arr.get('delay')) else ''}")
        chg = "direct" if changes == 0 else f"{changes} change{'s' if changes > 1 else ''}"
        trains = " + ".join(train_name(l[0]) for l in legs)
        head = f"{i}. {C.strike(times) if cancelled else C.bold(times)}   {dur_str(c['duration'])} · {chg} · {trains}"
        occ = occupancy_str(dep.get("occupancy"))
        print(("\n" if not args.brief or i == 1 else "") + head + (f"  {occ}" if occ else "")
              + (C.red("  CANCELLED") if cancelled else ""))
        if args.brief:
            continue
        for d_pt, a_pt, via in legs:
            print(point_line(d_pt["time"], d_pt.get("delay"), d_pt.get("station", ""),
                             d_pt.get("platforminfo"), d_pt.get("platform"), is_on(d_pt.get("canceled"))))
            direction = (d_pt.get("direction") or {}).get("name", "")
            occ = occupancy_str(d_pt.get("occupancy"))
            print(C.dim("             │ ") + C.cyan(train_name(d_pt))
                  + (f" → {direction}" if direction else "") + (f"  {occ}" if occ else ""))
            if args.details:
                for s in (d_pt.get("stops") or {}).get("stop", []):
                    t = s.get("scheduledArrivalTime") or s.get("scheduledDepartureTime")
                    if not t:
                        continue
                    d = delay_str(s.get("arrivalDelay") or s.get("departureDelay"))
                    line = f"             │   {hhmm(t)}{' ' + d if d else ''}  {s['station']}"
                    if is_on(s.get("arrivalCanceled")) and is_on(s.get("departureCanceled")):
                        line = C.strike(line) + C.red("  cancelled")
                    print(C.dim(line) if not d else line)
            print(point_line(a_pt["time"], a_pt.get("delay"), a_pt.get("station", ""),
                             a_pt.get("platforminfo"), a_pt.get("platform"), is_on(a_pt.get("canceled"))))
            if via:
                print(C.dim(f"             ┆ change at {via.get('station', '')}, {dur_str(via.get('timebetween', 0))}"))
        seen = set()
        for al in (c.get("alerts") or {}).get("alert", []):
            h = (al.get("header") or al.get("lead") or "").strip()
            if h and h not in seen:
                seen.add(h)
                print(C.yellow(f"   ⚠ {h}"))
                if args.details and al.get("description"):
                    print(C.dim("     " + al["description"].strip().replace("\n", "\n     ")))
    if not args.details and not args.brief:
        print(C.dim("\n(--details: intermediate stops and full notices · --brief: one line per trip)"))


def cmd_board(args):
    st = resolve_station(args.station, args.lang)
    date, tm, label = when_params(args)
    kind = "arrival" if args.arrivals else "departure"
    data = api("liveboard", id=st["id"], arrdep=kind, date=date, time=tm, lang=args.lang)
    if args.json:
        return print(json.dumps(data, indent=2, ensure_ascii=False))
    rows = (data.get(kind + "s") or {}).get(kind, [])[: args.number]
    title = "Arrivals" if args.arrivals else "Departures"
    print(C.bold(f"{title} · {st['name']}") + C.dim(f"  ·  from {label}") + "\n")
    if not rows:
        return print("Nothing found.")
    for r in rows:
        t = f"{hhmm(r['time'])} {pad(delay_str(r.get('delay')), 4)}"
        where = r.get("station", "")
        line = (f"{C.bold(t)}  {pad(where, 28)} {pad(C.cyan(train_name(r)), 10)} "
                f"{pad(platform_str(r.get('platforminfo'), r.get('platform')), 7)} {occupancy_str(r.get('occupancy'))}")
        if is_on(r.get("canceled")):
            line = C.strike(line) + "  " + C.red("CANCELLED")
        print(line)


def cmd_train(args):
    vid = args.train.replace(" ", "").upper()
    date = None
    if args.date:
        try:
            date = parse_date(args.date).strftime("%d%m%y")
        except ValueError:
            die(f"can't read date '{args.date}'")
    data = api("vehicle", id=vid, date=date, lang=args.lang)
    if args.json:
        return print(json.dumps(data, indent=2, ensure_ascii=False))
    name = (data.get("vehicleinfo") or {}).get("shortname", vid)
    stops = (data.get("stops") or {}).get("stop", [])
    if stops:
        print(C.bold(f"{name}") + C.dim(f"  ·  {stops[0]['station']} → {stops[-1]['station']}") + "\n")
    for s in stops:
        passed = is_on(s.get("left")) or (s is stops[-1] and is_on(s.get("arrived")))
        mark = C.dim("✓") if passed else " "
        dly = s.get("departureDelay") if s is not stops[-1] else s.get("arrivalDelay", s.get("delay"))
        t = f"{hhmm(s['time'])} {pad(delay_str(dly if dly is not None else s.get('delay')), 4)}"
        line = f"{mark} {t}  {pad(s['station'], 30)} {platform_str(s.get('platforminfo'), s.get('platform'))}"
        if is_on(s.get("canceled")):
            line = C.strike(line) + "  " + C.red("CANCELLED")
        print(C.dim(line) if passed else line)


def cmd_stations(args):
    matches = search_stations(args.query, args.lang) if args.query else load_stations(args.lang)
    if args.names:
        for m in matches:
            print(m["name"])
        return
    if args.json:
        return print(json.dumps(matches, indent=2, ensure_ascii=False))
    if not matches:
        return print("No station found.")
    for m in matches if not args.query else matches[:25]:
        extra = f"  {C.dim(m['standardname'])}" if m["standardname"] != m["name"] else ""
        print(f"{m['name']}{extra}")


def cmd_alerts(args):
    data = api("disturbances", lang=args.lang)
    if args.json:
        return print(json.dumps(data, indent=2, ensure_ascii=False))
    items = data.get("disturbance", [])
    if args.filter:
        f = " ".join(norm(args.filter))
        items = [d for d in items if f in " ".join(norm(d.get("title", "") + " " + d.get("description", "")))]
    if not items:
        return print("No current disruptions." if not args.filter else "No disruptions match.")
    for d in items:
        when = dt.datetime.fromtimestamp(int(d["timestamp"]), TZ).strftime("%d/%m %H:%M")
        kind = C.dim("[planned] ") if d.get("type") == "planned" else ""
        print(f"{C.dim(when)}  {kind}{C.bold(d['title'])}")
        if args.verbose:
            for line in d.get("description", "").strip().splitlines():
                if line.strip():
                    print("    " + line.strip())
            print()


def load_shortcuts():
    try:
        with open(SHORTCUTS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_shortcuts(sc):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SHORTCUTS_FILE, "w") as f:
        json.dump(sc, f, indent=2, ensure_ascii=False)


def cmd_shortcut(args):
    sc = load_shortcuts()
    if args.action == "list":
        if args.names:
            return print("\n".join(sorted(sc)))
        if args.json:
            return print(json.dumps(sc, indent=2, ensure_ascii=False))
        if not sc:
            return print("No shortcuts yet. Add one: sncb shortcut add work ottignies brussels-central")
        for name, v in sorted(sc.items()):
            where = f"{v['from_name']} → {v['to_name']}" if v.get("to_id") else f"{v['from_name']} (board)"
            print(f"{C.bold(pad(name, 12))} {where}")
        return
    if not args.name:
        die(f"usage: sncb shortcut {args.action} NAME" + (" FROM [TO]" if args.action == "add" else ""))
    if args.action == "rm":
        if sc.pop(args.name, None) is None:
            die(f"no shortcut named '{args.name}'")
        save_shortcuts(sc)
        return print(f"Removed '{args.name}'.")
    # add
    if args.name in COMMANDS:
        die(f"'{args.name}' is a command name, pick another")
    if not 1 <= len(args.stations) <= 2:
        die("usage: sncb shortcut add NAME FROM [TO]   (one station = its departure board)")
    pts = [resolve_station(q, args.lang) for q in args.stations]
    entry = {"from_id": pts[0]["id"], "from_name": pts[0]["name"]}
    if len(pts) == 2:
        entry.update(to_id=pts[1]["id"], to_name=pts[1]["name"])
    sc[args.name] = entry
    save_shortcuts(sc)
    what = f"{entry['from_name']} → {entry['to_name']}" if len(pts) == 2 else f"{entry['from_name']} (board)"
    print(f"Saved '{args.name}': {what}.  Use: sncb {args.name} [HH:MM]")


ZSH_COMPLETION = r'''#compdef sncb
# zsh completion for sncb. Install: sncb completion zsh > "${fpath[1]}/_sncb"
# or add to ~/.zshrc:  eval "$(sncb completion zsh)"
_sncb() {
  local -a cmds stations shortcuts
  cmds=(trip board train stations alerts shortcut completion)
  stations=("${(@f)$(sncb stations --names 2>/dev/null)}")
  if (( CURRENT == 2 )); then
    shortcuts=("${(@f)$(sncb shortcut list --names 2>/dev/null)}")
    compadd -a cmds
    (( ${#shortcuts} )) && [[ -n $shortcuts[1] ]] && compadd -a shortcuts
    compadd -a stations
    return
  fi
  case $words[2] in
    shortcut)
      if (( CURRENT == 3 )); then compadd add list rm
      elif [[ $words[3] == rm ]]; then compadd ${(f)"$(sncb shortcut list --names 2>/dev/null)"}
      elif (( CURRENT > 4 )); then compadd -a stations; fi ;;
    completion) compadd zsh ;;
    train|alerts) ;;
    *) compadd -a stations ;;
  esac
}
if [[ $zsh_eval_context[-1] == loadautofunc ]]; then _sncb "$@"; else compdef _sncb sncb; fi
'''


def cmd_completion(args):
    print(ZSH_COMPLETION, end="")


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        prog="sncb", description="Belgian train (SNCB/NMBS) times from the terminal. Data: iRail API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Short forms:\n"
               "  sncb A B [TIME]   = sncb trip A B [TIME]\n"
               "  sncb A [TIME]     = sncb board A [TIME]\n"
               "  sncb NAME [TIME]  = a saved shortcut (sncb shortcut add NAME A [B])\n"
               "Station names can be partial, misspelled, or in any language (gent, bruxelles midi, liege).")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--lang", default=os.environ.get("SNCB_LANG", "en"), choices=["en", "fr", "nl", "de"],
                        help="language for station names and notices (default: $SNCB_LANG or en)")
    common.add_argument("--json", action="store_true", help="print the raw API reply")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trip", parents=[common], help="trains from A to B")
    t.add_argument("origin")
    t.add_argument("destination")
    t.add_argument("time", nargs="?", help="HH:MM (default: now)")
    t.add_argument("-d", "--date", help="DD/MM, DD/MM/YYYY, today, tomorrow")
    t.add_argument("-a", "--arrive", action="store_true", help="TIME is the arrival time, not departure")
    t.add_argument("-n", "--number", type=int, default=4, help="how many trips (default 4)")
    t.add_argument("-s", "--details", action="store_true", help="also show intermediate stops and full notices")
    t.add_argument("-b", "--brief", action="store_true", help="one line per trip")
    t.set_defaults(func=cmd_trip)

    b = sub.add_parser("board", parents=[common], help="departure/arrival board of a station")
    b.add_argument("station")
    b.add_argument("time", nargs="?", help="HH:MM (default: now)")
    b.add_argument("-d", "--date")
    b.add_argument("--arrivals", action="store_true", help="show arrivals instead of departures")
    b.add_argument("-n", "--number", type=int, default=15)
    b.set_defaults(func=cmd_board)

    v = sub.add_parser("train", parents=[common], help="all stops of one train (e.g. IC1538)")
    v.add_argument("train")
    v.add_argument("-d", "--date")
    v.set_defaults(func=cmd_train)

    s = sub.add_parser("stations", parents=[common], help="search station names")
    s.add_argument("query", nargs="?", help="part of a name (omit to list all)")
    s.add_argument("--names", action="store_true", help="plain names only, one per line")
    s.set_defaults(func=cmd_stations)

    al = sub.add_parser("alerts", parents=[common], help="current disruptions and works")
    al.add_argument("filter", nargs="?", help="only show alerts mentioning this (e.g. a station)")
    al.add_argument("-v", "--verbose", action="store_true", help="show full descriptions")
    al.set_defaults(func=cmd_alerts)

    sh = sub.add_parser("shortcut", parents=[common], help="saved routes: add / list / rm",
                        description="sncb shortcut add work ottignies brussels-central   then: sncb work 8:00")
    sh.add_argument("action", choices=["add", "list", "rm"])
    sh.add_argument("name", nargs="?")
    sh.add_argument("stations", nargs="*", help="FROM [TO] (one station = its board)")
    sh.add_argument("--names", action="store_true", help=argparse.SUPPRESS)
    sh.set_defaults(func=cmd_shortcut)

    co = sub.add_parser("completion", help="print the zsh completion script")
    co.add_argument("shell", nargs="?", default="zsh", choices=["zsh"])
    co.set_defaults(func=cmd_completion)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and argv[0] not in ("-h", "--help"):
        sc = load_shortcuts().get(argv[0])
        if sc:
            argv = (["trip", sc["from_id"], sc["to_id"]] if sc.get("to_id") else ["board", sc["from_id"]]) + argv[1:]
        else:
            pos, skip = [], False
            for a in argv:
                if skip:
                    skip = False
                elif a in ("-d", "--date", "-n", "--number", "--lang"):
                    skip = True
                elif not a.startswith("-"):
                    pos.append(a)
            single = len(pos) == 1 or (len(pos) == 2 and looks_like_time(pos[1]))
            argv.insert(0, "board" if single else "trip")
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
