"""Wave planning: which formation, which enemies, and how hard they push.

Difficulty comes from several dials, not only speed: enemy mix (armored,
agile divers), aimed shots, how many enemy bullets can be in the air, how
often shots and dives happen, and a boss every few waves. Every dial has a
cap so late waves stay readable.
"""
from dataclasses import dataclass, field

# Non-boss formations, used in this order and then repeated.
FORMATION_CYCLE = ["grid", "chevron", "pincer", "columns", "diamond", "wall"]


def formation_cells(name):
    """Return the (col, row) cells of a formation on a 10 x 5 grid."""
    cells = []
    for row in range(5):
        for col in range(10):
            off = abs(col - 4.5)
            if name == "starter":
                keep = 1 <= col <= 8 and row <= 2
            elif name == "grid":
                keep = 1 <= col <= 8 and row <= 3
            elif name == "chevron":
                keep = abs(off - (4.5 - row)) <= 1.0
            elif name == "pincer":
                keep = (col <= 3 or col >= 6) and row <= 3
            elif name == "columns":
                keep = col % 2 == 1
            elif name == "diamond":
                keep = off + abs(row - 2) * 1.5 <= 4.0
            elif name == "wall":
                keep = row <= 1 or (row == 2 and col % 3 == 0)
            else:
                raise ValueError(f"unknown formation {name!r}")
            if keep:
                cells.append((col, row))
    return cells


@dataclass
class WavePlan:
    number: int
    formation: str
    enemies: list = field(default_factory=list)   # (kind, dx, dy) slot offsets
    boss_index: int = 0                            # 0 means no boss
    hint: str = ""
    march_speed: float = 0.0
    fire_interval: float = 0.0
    max_enemy_bullets: int = 0
    enemy_bullet_speed: float = 0.0
    aimed_shots: bool = False
    dive_interval: float = 0.0
    dive_speed: float = 0.0
    max_divers: int = 0

    @property
    def is_boss(self):
        return self.boss_index > 0


def _cells_to_offsets(cells, cfg):
    sx, sy = cfg.enemy.slot_spacing
    cols = [c for c, _ in cells]
    mid = (min(cols) + max(cols)) / 2
    return {(c, r): ((c - mid) * sx, r * sy) for c, r in cells}


def _hint(n, cfg, boss_index):
    if boss_index == 1:
        return "Boss incoming! Watch it glow before it fires"
    if boss_index:
        return f"Boss #{boss_index}, now with escorts"
    if n == 2:
        return "Armored aliens (blue) take 3 hits"
    if n == cfg.enemy.dive_first_wave:
        return "Agile aliens (orange) shake, then dive"
    if n == cfg.enemy_fire.aimed_from_wave:
        return "Armored aliens now aim at you"
    return ""


def plan_wave(n, cfg, rng):
    """Build the plan for wave n (1-based) using the game's seeded rng."""
    d = n - 1
    e, f = cfg.enemy, cfg.enemy_fire
    boss_index = n // cfg.boss.every if n % cfg.boss.every == 0 else 0
    plan = WavePlan(
        number=n,
        formation="boss" if boss_index else "",
        boss_index=boss_index,
        march_speed=min(e.march_speed_max, e.march_speed + e.march_speed_per_wave * d),
        fire_interval=max(f.interval_min, f.interval + f.interval_per_wave * d),
        max_enemy_bullets=min(f.max_bullets_cap, int(f.max_bullets + f.max_bullets_per_wave * d)),
        enemy_bullet_speed=min(f.bullet_speed_max, f.bullet_speed + f.bullet_speed_per_wave * d),
        aimed_shots=n >= f.aimed_from_wave,
        dive_interval=max(e.dive_interval_min, e.dive_interval + e.dive_interval_per_wave * d),
        dive_speed=min(e.dive_speed_max, e.dive_speed + e.dive_speed_per_wave * d),
        max_divers=0 if n < e.dive_first_wave else min(e.max_divers, 1 + (n - e.dive_first_wave) // 3),
    )
    plan.hint = _hint(n, cfg, boss_index)

    if boss_index:
        if boss_index >= cfg.boss.escort_from_boss:
            count = cfg.boss.escort_count
            cells = [(col, 4) for col in range(5 - count // 2, 5 - count // 2 + count)]
            offsets = _cells_to_offsets(cells, cfg)
            plan.enemies = [("standard",) + offsets[c] for c in cells]
        return plan

    if n == 1:
        plan.formation = "starter"
    else:
        bosses_before = (n - 1) // cfg.boss.every
        plan.formation = FORMATION_CYCLE[(n - 2 - bosses_before) % len(FORMATION_CYCLE)]

    cells = formation_cells(plan.formation)
    offsets = _cells_to_offsets(cells, cfg)
    kinds = {cell: "standard" for cell in cells}

    # Agile divers sit in the back rows, armored aliens shield the front.
    pool = list(cells)
    rng.shuffle(pool)
    agile_count = 0
    if n >= e.dive_first_wave:
        agile_count = min(8, 2 + (n - e.dive_first_wave))
    for cell in sorted(pool, key=lambda c: c[1])[:agile_count]:
        kinds[cell] = "agile"
    armored_count = round(len(cells) * min(0.4, 0.12 * d))
    front = [c for c in sorted(pool, key=lambda c: -c[1]) if kinds[c] == "standard"]
    for cell in front[:armored_count]:
        kinds[cell] = "armored"

    plan.enemies = [(kinds[c],) + offsets[c] for c in cells]
    return plan
