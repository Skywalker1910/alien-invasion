"""Help text for every entity and power-up, shown on the Help pages.

Numbers (HP, ammo, durations, boss weapons) are read from the config so
the help always matches the game.
"""

BASICS = [
    "Enemy squadrons swoop, stream and dive in. Shoot them before they shoot you.",
    "Your ship has a HEALTH bar. ARMOR soaks damage first; each SHIELD charge blocks one hit.",
    "After a hit you flash briefly and can't be hurt again, so one burst can't wipe you out.",
    "You have 3 ships. Health at zero costs a ship; you lose the equipped weapon and active upgrades.",
    "Wrecks drop capsules. Hexagons are weapons, circles are upgrades. Missed capsules are gone.",
    "Weapons go into your 10-slot inventory - switch any time. Upgrades work the moment you grab them.",
    "Levels 3, 6 and 10 are bosses. Hit their glowing weapons - the hull is armored.",
    "Chain kills quickly for a combo multiplier up to x5. Taking damage resets it.",
]

CONTROLS = [
    ("Arrows / WASD", "Fly"),
    ("Space (hold)", "Shoot"),
    ("Shift", "Shockwave (recharges)"),
    ("Q / E  or  mouse wheel", "Previous / next weapon"),
    ("1 ... 0", "Equip the weapon in that inventory slot"),
    ("P / Esc", "Pause menu"),
    ("H", "Help (from a menu)"),
    ("R", "Play again after game over"),
]

ENEMIES = {
    "drone": "Small and quick. Single shots straight down; from level 2 it sometimes dives at you.",
    "wasp": "Drops in, shakes for a moment, then dives straight at you. Rams hard.",
    "striker": "Strafes side to side and fires twin shots aimed at you.",
    "lancer": "Moves above you, draws a thin red line, then fires a beam down it. Move!",
    "guardian": "Heavily armored. Fires a spread of glowing orbs.",
    "dreadnought": "A battleship. Homing missiles (shoot them down) plus side guns. Always drops a capsule.",
    "cargo": "Supply pod. Harmless; crosses once per level. Shoot it for two capsules.",
    "asteroid": "Hazard. Tumbles through asteroid fields. Don't fly into it.",
    "mine": "Hazard. Blinks then explodes when you get close. Shooting it is safe.",
}

PART_NAMES = {
    "cannon": "cannons (aimed bursts)",
    "spread": "spread turrets (orb fans)",
    "missile": "missile pods (homing missiles)",
    "laser": "lasers (warning line, then beam)",
    "hangar": "drone hangar (launches fighters)",
    "core": "the core (orb rings and bursts)",
}

WEAPONS = {
    "spread": "Five bullets in a fan. Great against swarms.",
    "rapid": "A very fast stream of bullets.",
    "rail": "Heavy slug that pierces everything in a line.",
    "laser": "Continuous beam that melts the first thing it touches. Time only drains while firing.",
    "homing": "Pairs of missiles that chase the nearest target.",
    "plasma": "Big orb that explodes and damages everything nearby.",
    "chain": "Instantly zaps the nearest enemy and jumps to four more.",
    "flak": "Shell that bursts into a ring of shrapnel.",
}

UPGRADES = {
    "repair": "Restores health instantly.",
    "shield": "Blocks the next hits completely.",
    "armor": "Extra plating that soaks damage before your health.",
    "shock": "Instantly recharges your shockwave.",
    "wingmen": "Two drones fly beside you and shoot.",
    "overdrive": "Double damage and faster fire.",
    "magnet": "Pulls nearby capsules to you.",
    "life": "One more ship (rare).",
}


def weapon_limit(spec):
    if spec.ammo:
        return f"{spec.ammo} shots"
    return f"{spec.duration:g} s of firing" if spec.size[1] == 0 else f"{spec.duration:g} s equipped"


def upgrade_detail(kind, spec, cfg):
    pc = cfg.player
    if kind == "repair":
        return f"+{spec.value:g} health"
    if kind == "shield":
        return f"{spec.value:g} hits (max {pc.max_shield})"
    if kind == "armor":
        return f"+{spec.value:g} (max {pc.max_armor:g})"
    if kind == "life":
        return f"max {pc.max_lives} ships"
    if spec.duration:
        return f"{spec.duration:g} s"
    return "instant"


def boss_stages(spec):
    """['Stage 1: cannons (aimed bursts) x2', ...] built from the hardpoints."""
    lines = []
    for stage in sorted({hp.stage for hp in spec.hardpoints}):
        counts = {}
        for hp in spec.hardpoints:
            if hp.stage == stage:
                counts[hp.kind] = counts.get(hp.kind, 0) + 1
        parts = [PART_NAMES[k] + (f" x{n}" if n > 1 else "") for k, n in counts.items()]
        lines.append(f"Stage {stage}: " + ", ".join(parts))
    return lines
