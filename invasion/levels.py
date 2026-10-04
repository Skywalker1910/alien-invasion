"""Level content: sectors, enemy mixes, squadron patterns and boss levels.

Each level is a short run of waves. A wave is a random set of squadrons
picked from the level's enemy pool until its threat budget is spent, so no
two runs look the same, but the same seed always builds the same waves.

Squadron patterns:
  swoop   curve in from a top corner and settle into a V formation
  flank   slide in from one side and hold a row
  stream  fly straight through in a sine-wave line and leave again
  rain    wasps drop to a hover, aim, then dive at the ship
  solo    a heavy ship enters from the top and takes a position
  cross   a supply pod crosses the screen (shoot it for 2 pickups)
"""
from dataclasses import dataclass, field

# Each theme: (space color, nebula colors)
THEMES = [
    ((6, 8, 22), [(40, 60, 140), (90, 40, 130)]),
    ((14, 8, 20), [(150, 60, 40), (120, 40, 90)]),
    ((4, 14, 18), [(30, 120, 120), (40, 70, 140)]),
    ((10, 10, 10), [(110, 90, 60), (70, 70, 90)]),
    ((16, 6, 24), [(130, 40, 160), (60, 30, 120)]),
    ((4, 10, 24), [(40, 90, 170), (30, 140, 160)]),
]


@dataclass
class LevelSpec:
    number: int
    name: str
    pool: dict = field(default_factory=dict)       # enemy kind -> weight
    waves: int = 5
    budget: int = 8                                # threat budget of wave 1
    budget_step: int = 2                           # extra budget per later wave
    hazards: dict = field(default_factory=dict)    # hazard kind -> spawns per second
    boss: int = -1                                 # index into cfg.bosses, -1 = none
    boss_cycle: int = 0                            # endless repeats get tougher
    hint: str = ""
    theme: int = 0

    @property
    def is_boss(self):
        return self.boss >= 0


CAMPAIGN = {
    1: dict(name="Outer Rim", pool={"drone": 1}, waves=4, budget=7, budget_step=2,
            hint="Drones incoming! Wrecks drop power-up capsules: grab them"),
    2: dict(name="Hornet Nest", pool={"drone": 3, "wasp": 2, "striker": 1}, waves=5, budget=9,
            hint="Wasps dive straight at you. Strikers fire twin shots"),
    4: dict(name="Shattered Belt", pool={"drone": 2, "striker": 2, "lancer": 1}, waves=5,
            budget=12, hazards={"asteroid": 0.7},
            hint="Lancers charge a beam: get out of the red line!"),
    5: dict(name="Bastion", pool={"striker": 2, "lancer": 1, "guardian": 1, "wasp": 1}, waves=5,
            budget=15, budget_step=3, hint="Guardians soak damage. Bring out your best weapon"),
    7: dict(name="Minefield", pool={"striker": 2, "lancer": 1, "guardian": 1, "dreadnought": 0.5},
            waves=5, budget=18, budget_step=3, hazards={"mine": 0.5},
            hint="Mines blink before they blow. Dreadnoughts fire homing missiles"),
    8: dict(name="The Swarm", pool={"drone": 3, "wasp": 3, "striker": 1}, waves=6, budget=20,
            budget_step=3, hint="Here comes the swarm!"),
    9: dict(name="Iron Armada", pool={"striker": 2, "lancer": 2, "guardian": 2, "dreadnought": 1},
            waves=6, budget=24, budget_step=3, hazards={"asteroid": 0.3},
            hint="Their heaviest ships, all at once"),
}

BOSS_HINT = "Shoot the glowing weapons - the hull is armored"

SQUAD_SIZE = {"drone": (3, 6), "wasp": (3, 5), "striker": (2, 4), "lancer": (1, 2),
              "guardian": (1, 2), "dreadnought": (1, 1)}
PATTERNS = {"drone": ("swoop", "flank", "stream"), "wasp": ("rain",), "striker": ("swoop", "flank"),
            "lancer": ("solo",), "guardian": ("solo",), "dreadnought": ("solo",)}


def level_spec(n, cfg):
    """The spec for level n (1-based). Levels after 10 are endless remixes."""
    boss_levels = cfg.boss.levels
    if n in boss_levels:
        return LevelSpec(n, f"Boss: {cfg.bosses[boss_levels.index(n)].label}",
                         boss=boss_levels.index(n), hint=BOSS_HINT, theme=(n - 1) % len(THEMES))
    if n in CAMPAIGN:
        return LevelSpec(n, theme=(n - 1) % len(THEMES), **CAMPAIGN[n])
    # Endless: everything at once, a little harder every level.
    extra = n - max(boss_levels)
    if extra % cfg.boss.endless_every == 0:
        index = (extra // cfg.boss.endless_every - 1) % len(cfg.bosses)
        cycle = extra // cfg.boss.endless_every
        return LevelSpec(n, f"Boss: {cfg.bosses[index].label} Mk {cycle + 1}", boss=index,
                         boss_cycle=cycle, hint=BOSS_HINT, theme=(n - 1) % len(THEMES))
    hazards = {}
    if n % 2:
        hazards["asteroid"] = 0.4
    if n % 3 == 0:
        hazards["mine"] = 0.35
    return LevelSpec(n, f"Deep Space {extra}",
                     pool={"drone": 2, "wasp": 2, "striker": 2, "lancer": 2, "guardian": 1.5,
                           "dreadnought": 0.7},
                     waves=6, budget=22 + 2 * extra, budget_step=3, hazards=hazards,
                     hint="Endless mode: how far can you go?", theme=(n - 1) % len(THEMES))


@dataclass
class Spawn:
    time: float                  # seconds after the wave starts
    kind: str
    pattern: str
    start: tuple
    anchor: tuple = None         # where it settles (None = passes through)
    ctrl: tuple = None           # two bezier control points for the entry
    end: tuple = None            # stream / cross: where it leaves the screen
    amp: float = 0.0             # stream sway
    freq: float = 0.0


def _weighted(rng, weights):
    kinds = list(weights)
    return rng.choices(kinds, weights=[weights[k] for k in kinds])[0]


def build_wave(spec, wave_no, cfg, rng, with_cargo=False):
    budget = spec.budget + spec.budget_step * (wave_no - 1)
    spawns = []
    t = 0.0
    while budget > 0:
        affordable = {k: w for k, w in spec.pool.items() if cfg.enemies[k].threat <= budget}
        if not affordable:
            break
        kind = _weighted(rng, affordable)
        threat = cfg.enemies[kind].threat
        lo, hi = SQUAD_SIZE[kind]
        count = max(1, min(rng.randint(lo, hi), budget // threat))
        pattern = rng.choice(PATTERNS[kind])
        spawns += make_squad(kind, count, pattern, t, cfg, rng)
        budget -= count * threat
        t += rng.uniform(0.7, 1.4)
    if with_cargo:
        spawns += make_squad("cargo", 1, "cross", rng.uniform(0.5, max(1.0, t)), cfg, rng)
    return spawns


def make_squad(kind, count, pattern, t0, cfg, rng):
    width, height = cfg.display.width, cfg.display.height
    top = cfg.display.hud_height
    out = []
    if pattern == "swoop":
        left = rng.random() < 0.5
        d = 1 if left else -1
        cx = rng.uniform(200, width - 200)
        cy = rng.uniform(top + 80, height * 0.36)
        start = (70 if left else width - 70, -40)
        for i in range(count):
            off = i - (count - 1) / 2
            ax = min(width - 40, max(40, cx + off * 64))
            ay = cy - abs(off) * 18
            ctrl = ((start[0] + d * width * 0.35, height * 0.6), (ax - d * 140, ay + 170))
            out.append(Spawn(t0 + i * 0.16, kind, pattern, start, (ax, ay), ctrl))
    elif pattern == "flank":
        left = rng.random() < 0.5
        d = 1 if left else -1
        y = rng.uniform(top + 70, height * 0.38)
        for i in range(count):
            ax = (width - 90 - i * 70) if left else (90 + i * 70)
            start = (-40 if left else width + 40, y + rng.uniform(-50, 50))
            ctrl = ((start[0] + d * 220, start[1]), (ax - d * 160, y))
            out.append(Spawn(t0 + i * 0.14, kind, pattern, start, (ax, y), ctrl))
    elif pattern == "stream":
        x0 = rng.uniform(80, width - 80)
        x1 = width - x0
        amp = rng.uniform(60, 140)
        freq = rng.uniform(0.8, 1.4)
        for i in range(count):
            out.append(Spawn(t0 + i * 0.22, kind, pattern, (x0, -30), end=(x1, height + 40),
                             amp=amp, freq=freq))
    elif pattern == "rain":
        for i in range(count):
            x = rng.uniform(60, width - 60)
            anchor = (min(width - 40, max(40, x + rng.uniform(-60, 60))), rng.uniform(top + 60, 210))
            start = (x, -40)
            ctrl = ((x, anchor[1] * 0.4), (anchor[0], anchor[1] * 0.8))
            out.append(Spawn(t0 + i * 0.35, kind, pattern, start, anchor, ctrl))
    elif pattern == "solo":
        for i in range(count):
            start = (rng.uniform(140, width - 140), -70)
            anchor = (rng.uniform(140, width - 140), rng.uniform(top + 90, height * 0.32))
            ctrl = ((start[0], anchor[1] * 0.5), (anchor[0], anchor[1] * 0.8))
            out.append(Spawn(t0 + i * 1.2, kind, pattern, start, anchor, ctrl))
    elif pattern == "cross":
        left = rng.random() < 0.5
        y = rng.uniform(top + 70, 180)
        start, end = ((-50, y), (width + 60, y)) if left else ((width + 50, y), (-60, y))
        out.append(Spawn(t0, kind, pattern, start, end=end))
    else:
        raise ValueError(f"unknown pattern {pattern!r}")
    return out
