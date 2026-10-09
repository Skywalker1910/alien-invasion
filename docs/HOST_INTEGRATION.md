# Host integration (browser build)

The browser build is the same Python game packaged with
[Pygbag](https://github.com/pygame-web/pygbag) (pygame-ce compiled to
WebAssembly). A JavaScript host page, such as a portfolio site, can embed it and
talk to it through a small bridge (`invasion/bridge.py`).

The bridge is only active when the game runs in the browser
(`sys.platform == "emscripten"`). On desktop it does nothing. If a call to the
host fails, the bridge turns itself off and the game keeps running.

## What the game keeps, and what the host can add

The game keeps a **local leaderboard** itself. After a run, the player types a pilot name (a game name, up to 14 plain characters) and picks a country flag. The entry is stored in the browser's `localStorage` (or in SQLite on desktop), and the game sends a `score_saved` event.

A host page can add things the game deliberately doesn't do:

- a public, cross-device leaderboard: listen for `score_saved` (or `game_over`) and submit it to your own service
- sign-in, analytics and sharing

The game never stores credentials, never asks for a real name, and makes no network calls of its own.

## Building

```bash
pip install -r requirements-dev.txt
python build_web.py           # writes build/web/ (index.html, alien_invasion.apk, ...)
python build_web.py --serve   # same, then serves it on http://localhost:8000
```

`build_web.py` copies only `main.py`, `invasion/` and `assets/` into a clean
staging folder before calling Pygbag. That keeps virtualenvs, tests and caches
out of the bundle; Pygbag's own ignore rules leaked them on Windows. The build
passes `--ume_block 0`, so the game starts without an extra "click to start"
step (it has no audio that would need it).

Host the contents of `build/web/` as static files. At load time the page pulls
the Python/WebAssembly runtime from Pygbag's CDN (`pygame-web.github.io`). If
you serve the page with a strict Content-Security-Policy, allow that origin.

## Embedding

```html
<iframe id="game" src="/alien-invasion/index.html?parentOrigin=https://your-site.example"
        style="aspect-ratio: 3 / 2; width: 100%; border: 0"></iframe>
```

The game always draws a fixed 960 × 640 logical playfield, and the canvas
scales to fit whatever size you give it. It stays readable down to roughly
480 × 320.

`parentOrigin` is optional. When you set it, the game only posts events to that
origin. Without it, events are posted with target origin `"*"`. They contain
nothing sensitive, but pinning the origin is better practice.

`docs/host-example.html` is a complete working host page with a score display,
start/pause buttons and on-screen touch controls.

## Game → host events

Every event is a plain JSON object with a `type`. The game sends each one three
ways:

1. `window.parent.postMessage({source: "alien-invasion", ...event}, parentOrigin)` when embedded in an iframe
2. `window.dispatchEvent(new CustomEvent("alien-invasion", {detail: event}))` inside the game page
3. `window.AlienInvasionBridge.onEvent(event)`, if the host page set that function

| type | when | fields |
| --- | --- | --- |
| `ready` | the game loaded and is showing the title screen | `version`, `width`, `height` |
| `run_started` | a new run began | `run_id`, `seed`, `version` |
| `state` | something on the HUD changed. Lives, level, wave, pause and game state go out at once; score, hull, ammo and timers at most every 0.25 s | `state` (`title` / `playing` / `game_over`), `paused`, `score`, `multiplier`, `level`, `wave`, `lives`, `health`, `armor`, `shield` (hits left), `weapon` (`{name, ammo, time}` or `null`), `inventory` (list of `{kind, ammo, time}`, weapons only), `selected` (index of the equipped slot or `null`), `buffs` (`{kind: seconds_left}`), `shock` (0–1 charge), `boss` (`{name, stage, stages, stage_hp}` or `null`), `run_id` |
| `level_started` | a level (or boss level) begins | `level`, `name`, `boss`, `hint`, `theme` |
| `wave_started` | a new wave of a normal level begins | `level`, `wave`, `waves` |
| `level_cleared` | the level is done (all waves or the boss) | `level`, `bonus` |
| `boss_spawned` / `boss_stage` / `boss_defeated` | boss fight starts / reaches stage 2 or 3 / ends | `name`, `stages` / `stage`, `stages` / `points`, `level` |
| `player_destroyed` | the player lost a ship | `lives`, `cause` (`bullet`, `orb`, `bolt`, `missile`, `beam`, `ram`, `mine`) |
| `pickup` | a capsule was collected | `kind`, `category` (`weapon` / `utility`), `label`, `bonus` |
| `weapon_switched` | the player changed weapon | `weapon`, `slot` |
| `briefing_started` / `briefing_finished` | Orbi's story briefing opened / was finished or skipped (the game is frozen in between) | |
| `score_saved` | the player saved a run to the local leaderboard | `name`, `country` (ISO code or empty), `score`, `level`, `run_id`, `seed`, `rank` (local) |
| `paused` / `resumed` | pause state changed (keyboard, focus or host) | |
| `run_abandoned` | the player left a run from the pause menu (Restart run / Main menu). Not a finished run: don't submit it. | `run_id`, `score`, `level` |
| `game_over` | the run ended. **Sent exactly once per run.** | `run_id`, `seed`, `score`, `level`, `wave`, `kills`, `ticks`, `duration`, `version` |

`run_id` is `"<seed>-<run number>"`. The simulation runs at a fixed 60 steps
per second and takes all of its randomness from `seed`. That means the same seed
and the same inputs always produce the same run. `ticks` is the number of
simulation steps. Together these lay the groundwork for server-side score
checks later, for example by recording inputs and replaying them.

## Host → game commands

Send commands either with
`iframe.contentWindow.postMessage({target: "alien-invasion", type, ...}, gameOrigin)`
from the parent page (the game only accepts these from its direct parent), or
with `window.AlienInvasionBridge.send({type, ...})` from inside the game page.

| type | effect |
| --- | --- |
| `start` | start a run from the main menu or game-over screen (closes the menu). Optional integer `seed`. |
| `restart` | same as pressing R. Only works on the game-over screen. Optional `seed`. |
| `pause` / `resume` | pause (opens the pause menu) or resume a run in progress, e.g. on `visibilitychange` |
| `input` | virtual buttons for touch controls: any of `left`, `right`, `up`, `down`, `fire` as booleans. Values you leave out keep their previous state. They are combined (OR) with the keyboard. |
| `special` | fire the shockwave if it is charged (like pressing Shift) |
| `switch` | previous / next weapon: `direction` -1 or 1 (like Q / E) |
| `select` | equip the weapon in inventory `slot` (0–9, like keys 1–0) |
| `skip_briefing` | close Orbi's briefing (like Esc) |

Unknown commands are ignored.

In the browser the game does not pause itself when the canvas loses focus,
because the host's own buttons take focus. Pause from the host instead, for
example on `visibilitychange` as the example page does. On desktop the game
pauses when its window loses focus.
