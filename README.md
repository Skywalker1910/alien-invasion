# 👾 Alien Invasion

A simple 2D space shooter I built in Python with Pygame.

## How this project started

I wrote this game back in my 2nd year of engineering, when I was just learning Python. I followed along with the Alien Invasion project from *Python Crash Course* by Eric Matthes. It was one of the first "real" programs I made: a window, a ship, aliens, and a lot of trial and error.

The code is a bit rough in places (yes, the file is called `game_funtions.py` 😅). I kept it that way on purpose so you can see where I started.

## What I'm doing with it now

These days this is my **weekend hobby project**. I'm using AI coding agents to help me improve the game step by step. I want to see how far an old beginner project can go, and learn how to work well with AI tools along the way.

Every change goes in as its own commit, so the git history shows how the game grows over time.

## How to play

Aliens move across the screen in a group and drop down a bit each time they hit the edge. Shoot them all before they reach you!

- You get **3 ships** (lives).
- Clear all the aliens and a new, faster wave shows up.
- Aliens in the front row shoot back, so watch out for their red bullets.
- Your bullets can hit their bullets and cancel them out.
- Each level gives more points per alien.

### Controls

| Key | What it does |
| --- | --- |
| ⬅️ / ➡️ Arrow keys | Move the ship |
| Spacebar | Shoot |
| Mouse click on **Play** | Start a new game |
| Q | Quit |

## How to run it

You need Python 3 and Pygame.

```bash
pip install pygame
python alien_invasion.py
```

## What's in the folder

| File | What it does |
| --- | --- |
| `alien_invasion.py` | Starts the game and runs the main loop |
| `game_funtions.py` | Most of the game logic (input, movement, collisions) |
| `settings.py` | All the numbers you can tweak: speeds, sizes, colors |
| `ship.py` | The player's ship |
| `alien.py` | One alien |
| `bullet.py` | The player's bullets |
| `alien_bullet.py` | The aliens' bullets |
| `game_stats.py` | Keeps track of score, level and lives |
| `scoreboard.py` | Draws the score, high score, level and lives |
| `button.py` | The Play button |
| `images/` | Pictures for the ship and the aliens |

## Changes so far

- ✅ The original game from my college days
- ✅ Aliens shoot back (front row only, with a limit on bullets so it stays fair)

## Ideas for what's next

Some things I'd like to try:

- Sound effects and music
- Saving the high score between games
- Different kinds of aliens and boss fights
- Power-ups
- Cleaning up the code as I go

## License

This is a personal learning project. Feel free to look around and learn from it.
