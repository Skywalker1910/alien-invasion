"""Player weapons: the unlimited blaster plus eight collectible weapons.

A collected weapon replaces the current one. Picking up the weapon you
already hold refills it. When its ammo or time runs out you are back to the
blaster. Weapons are limited either by shots (ammo) or by time; the laser's
time only drains while the beam is firing.
"""
import math

from .entities import Shot


def damage_mult(game):
    return 2.0 if "overdrive" in game.ship.buffs else 1.0


def cooldown_mult(game):
    return 0.7 if "overdrive" in game.ship.buffs else 1.0


def _shot(game, kind, x, y, angle, speed, size, damage, pierce=0):
    rad = math.radians(angle)
    shot = Shot(kind, x, y, math.sin(rad) * speed, -math.cos(rad) * speed, size, damage, pierce)
    game.shots.append(shot)
    return shot


def blaster(game, x, y):
    pc = game.cfg.player
    _shot(game, "bullet", x, y, 0.0, pc.blaster_speed, pc.blaster_size,
          pc.blaster_damage * damage_mult(game))


def fire(game):
    """Fire the current weapon once. Returns True if something was fired."""
    ship = game.ship
    top = ship.y - ship.h / 2
    if ship.weapon is None:
        blaster(game, ship.x, top)
        ship.fire_timer = game.cfg.player.blaster_cooldown * cooldown_mult(game)
        return True
    spec = game.cfg.weapons[ship.weapon]
    fired = FIRE[ship.weapon](game, spec, ship, top)
    if not fired:
        ship.fire_timer = 0.08
        return False
    ship.fire_timer = spec.cooldown * cooldown_mult(game)
    if spec.ammo:
        ship.ammo -= 1
        if ship.ammo <= 0:
            game.weapon_empty()
    return True


def _spread(game, spec, ship, top):
    dmg = spec.damage * damage_mult(game)
    for i in range(spec.count):
        angle = (i - (spec.count - 1) / 2) * spec.angle
        _shot(game, "bullet", ship.x, top, angle, spec.speed, spec.size, dmg)
    return True


def _rapid(game, spec, ship, top):
    angle = game.rng.uniform(-spec.angle, spec.angle)
    _shot(game, "bullet", ship.x + game.rng.uniform(-6, 6), top, angle, spec.speed, spec.size,
          spec.damage * damage_mult(game))
    return True


def _rail(game, spec, ship, top):
    _shot(game, "rail", ship.x, top - spec.size[1] / 2, 0.0, spec.speed, spec.size,
          spec.damage * damage_mult(game), pierce=spec.pierce)
    return True


def _homing(game, spec, ship, top):
    dmg = spec.damage * damage_mult(game)
    for side in (-1, 1)[:spec.count]:
        shot = _shot(game, "homing", ship.x + side * 14, top + 10, side * 35.0, spec.speed,
                     spec.size, dmg)
        shot.turn_rate = spec.turn_rate
        shot.life = 3.0
    return True


def _plasma(game, spec, ship, top):
    shot = _shot(game, "plasma", ship.x, top, 0.0, spec.speed, spec.size,
                 spec.damage * damage_mult(game))
    shot.splash_radius = spec.splash_radius
    shot.splash_damage = spec.splash_damage * damage_mult(game)
    return True


def _flak(game, spec, ship, top):
    shot = _shot(game, "flak", ship.x, top, 0.0, spec.speed, spec.size,
                 spec.damage * damage_mult(game))
    shot.fuse = spec.fuse
    shot.shrapnel = spec.shrapnel
    return True


def _chain(game, spec, ship, top):
    """Instant lightning to the nearest target ahead, arcing onward."""
    targets = [t for t in game.targets() if t[2] < ship.y]
    if not targets:
        return False
    first = min(targets, key=lambda t: math.hypot(t[1] - ship.x, t[2] - ship.y))
    if math.hypot(first[1] - ship.x, first[2] - ship.y) > 600:
        return False
    dmg = spec.damage * damage_mult(game)
    chain = [first]
    while len(chain) <= spec.chain:
        last = chain[-1]
        rest = [t for t in targets if t[0] not in [c[0] for c in chain]
                and math.hypot(t[1] - last[1], t[2] - last[2]) <= spec.chain_range]
        if not rest:
            break
        chain.append(min(rest, key=lambda t: math.hypot(t[1] - last[1], t[2] - last[2])))
    points = [(ship.x, top)] + [(t[1], t[2]) for t in chain]
    for target, _, _ in chain:
        game.damage_target(target, dmg)
    game.emit("chain", points=[(round(x), round(y)) for x, y in points])
    return True


def update_laser(game, dt):
    """Continuous beam while fire is held: damages the first thing above."""
    ship = game.ship
    spec = game.cfg.weapons["laser"]
    ship.laser_on = True
    ship.weapon_time -= dt
    top = ship.y - ship.h / 2
    half = spec.size[0] / 2
    best, best_bottom = None, 0.0
    for target, rect in game.target_rects():
        if rect.right >= ship.x - half and rect.left <= ship.x + half and rect.bottom < top:
            if rect.bottom > best_bottom:
                best, best_bottom = target, rect.bottom
    blocker = game.boss_hull_rect()
    if blocker and blocker.left <= ship.x <= blocker.right and blocker.bottom > best_bottom:
        # The beam is stopped by the armored hull unless a weapon is in the way.
        if best is None:
            best_bottom = blocker.bottom
    ship.laser_top = best_bottom
    if best is not None:
        game.damage_target(best, spec.damage * damage_mult(game) * dt)
    if ship.weapon_time <= 0:
        game.weapon_empty()


FIRE = {
    "spread": _spread,
    "rapid": _rapid,
    "rail": _rail,
    "homing": _homing,
    "plasma": _plasma,
    "flak": _flak,
    "chain": _chain,
}
