# 👾 Alien Invasion

A 2D arcade space shooter I built in Python with Pygame. It runs on the desktop and in the browser.

## How this project started

I wrote this game back in my 2nd year of engineering, when I was just learning Python. I followed along with the Alien Invasion project from *Python Crash Course* by Eric Matthes. It was one of the first "real" programs I made: a window, a ship, aliens, and a lot of trial and error.

If you want to see where I started, the original code (yes, with a file called `game_funtions.py` 😅) is still in the git history. Look at the first commits on `main`.

## What I'm doing with it now

These days this is my **weekend hobby project**. I'm using AI coding agents to help me improve the game step by step. I want to see how far an old beginner project can go, and learn how to work well with AI tools along the way.

Every change goes in as its own commit, so the git history shows how the game grows over time.

## How to play

Aliens march across the screen in formation and drop down each time they hit an edge. Shoot them before they land!

- You have **3 lives**, and each hit costs exactly one. After a hit your ship comes back blinking and can't be hurt for 2 seconds.
- Clear a wave and the next one arrives in a new formation with a different mix of enemies.
- **Every 5th wave is a boss.** It glows red before each attack, so watch for that.
- Aliens glow before they shoot, and they never fire from point-blank range.
- Your bullets can shoot enemy bullets out of the air.

### Enemies

| Enemy | What to know |
| --- | --- |
| 🟢 Standard | One hit. Shoots straight down. |
| 🔵 Armored | Three hits (the little bars show what's left). From wave 4 they aim at you. |
| 🟠 Agile | One hit. Shakes for a moment, then dives at you in a swaying path. |
| 🔴 Boss | Big health bar. Fires aimed bursts and bullet fans, and gets angrier at half health. |

### Power-ups

Defeated enemies sometimes drop a power-up. Fly into it to collect it.

| Pickup | Effect |
| --- | --- |
| **S** Shield | Blocks bullets and rams for 8 s |
| **3** Spread | Fires 3 bullets in a fan for 10 s |
| **P** Pierce | Bullets pass through up to 3 extra enemies for 10 s |
| **+** Extra life | One more life, up to 5 (rare) |

The rules are kept simple:
- Different power-ups stack. Spread and pierce together give you piercing spread shots.
- Picking up one you already have resets its timer to full. Timers never add up.
- The bottom-left corner shows every active power-up and the time it has left. A bar blinks when it's about to run out.
- Losing a life removes your power-ups, but you keep your special charges.
- A new game always starts clean.
- If aliens reach your row, you lose a life even with a shield on.

### Controls

| Key | What it does |
| --- | --- |
| ⬅️ / ➡️ or A / D | Move |
| Space (hold) | Shoot |
| Shift | Special shockwave: clears every enemy bullet and damages nearby aliens. You start with 2 charges and earn 1 per boss (max 3). |
| P or Esc | Pause / resume |
| R | Play again after game over |
| Space / Enter / click | Start from the title screen |
| Q | Quit (desktop only) |

## How to run it

You need Python 3.9 or newer.

```bash
pip install -r requirements.txt
python main.py               # or: python alien_invasion.py
python main.py --seed 1234   # play the exact same run again
```

The game uses [pygame-ce](https://pyga.me/), the community edition that also powers the browser build. Classic `pygame` 2.x works on the desktop too.

### Browser version

The browser build is the same Python code, packaged with [Pygbag](https://github.com/pygame-web/pygbag) (pygame-ce compiled to WebAssembly).

```bash
pip install -r requirements-dev.txt
python build_web.py --serve   # open http://localhost:8000
python build_web.py           # just build into build/web/
```

My portfolio page embeds this build. The game reports things like run started, score and game over to the page, and the page can pause it or send touch controls. The page handles player names and the leaderboard, never the game. The details are in [docs/HOST_INTEGRATION.md](docs/HOST_INTEGRATION.md).

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests check the important rules: 3 lives means 3 hits, one collision never costs two lives, shields and weapons expire on time, restarting cleans everything up, waves and bosses arrive in order, game over is reported once per run, the same seed replays the same run, and the frame rate doesn't change how fast anything moves.

## Tweaking the balance

Every number lives in `invasion/config.py`, grouped by topic, with units in the comments (pixels, pixels per second, seconds, probabilities). The ones I tune most:

| Setting | Default | What it does |
| --- | --- | --- |
| `player.start_lives` / `max_lives` | 3 / 5 | Lives at the start / life cap |
| `player.invulnerable_time` | 2.0 s | Blinking grace period after a hit |
| `player.fire_cooldown` | 0.24 s | Time between your shots |
| `enemy_fire.interval` → `interval_min` | 1.7 s → 0.6 s | Time between enemy shots, wave 1 → late waves |
| `enemy_fire.max_bullets` → `max_bullets_cap` | 2 → 6 | Enemy bullets on screen at once |
| `enemy_fire.safe_distance` | 170 px | Enemies never shoot from closer than this |
| `boss.every` | 5 | Waves between bosses |
| `powerups.weights` | 35 / 30 / 25 / 10 | Shield / spread / pierce / life drop odds |
| `powerups.durations` | 8 / 10 / 10 s | How long timed power-ups last |
| `enemy.*.drop_chance` | 5–14 % | Chance an enemy drops something |

## What's in the folder

| Path | What it does |
| --- | --- |
| `main.py` | Starts the game (desktop and browser) |
| `alien_invasion.py` | The old desktop launcher, kept so the original command still works |
| `invasion/config.py` | All the balance numbers |
| `invasion/game.py` | The game rules: lives, waves, power-ups, collisions. No drawing. |
| `invasion/waves.py` | Wave formations, enemy mix and difficulty per wave |
| `invasion/entities.py` | Ship, aliens, boss, bullets, pickups |
| `invasion/render.py` | Drawing, effects, HUD and menus |
| `invasion/controls.py` | Keyboard plus virtual (touch) input |
| `invasion/app.py` | The window and the main loop |
| `invasion/bridge.py` | Talks to the web page in the browser build (does nothing on desktop) |
| `assets/images/` | Ship and alien pictures (PNG) |
| `build_web.py` | Builds the browser version |
| `tests/` | Automated tests |
| `docs/` | Browser host integration guide and an example host page |

## Changes so far

- ✅ The original game from my college days
- ✅ Aliens shoot back (front row only, with a limit on bullets so it stays fair)
- ✅ **Arcade upgrade:** three enemy types, six formations, bosses, power-ups, a special attack, pause/restart, new HUD and effects, frame-rate independent timing, a fixed lives bug (the old code gave you 4 hits), tests, and a browser build

## Ideas for what's next

- Sound effects and music
- Saving the high score between games
- On-screen touch controls inside the game itself
- Recording inputs so a run's score can be replayed and verified

## License

This is a personal learning project. Feel free to look around and learn from it.
