"""A simple bot used by smoke tests and balance checks (--autoplay).

It dodges by predicting where each enemy bullet will cross the ship's row,
then chases the nearest target. Not part of normal play.
"""
from .game import InputState


def _threat(game, x):
    """Earliest time an enemy bullet would hit a ship standing at x."""
    ship = game.ship
    soonest = None
    for shot in game.enemy_bullets:
        if shot.vy <= 0:
            continue
        # Window from the bullet touching the ship's top to leaving its bottom.
        t_in = (ship.y - ship.h / 2 - shot.y - shot.h / 2) / shot.vy
        t_out = (ship.y + ship.h / 2 - shot.y + shot.h / 2) / shot.vy
        if t_out < 0 or t_in > 1.1:
            continue
        t = max(0.0, t_in)
        if abs(shot.x + shot.vx * t - x) < ship.w * 0.6:
            soonest = t if soonest is None else min(soonest, t)
    for enemy in game.enemies:
        if enemy.mode == "diving" and abs(enemy.x - x) < ship.w and ship.y - enemy.y < 220:
            soonest = 0.0
    return soonest


def autopilot(game):
    ship = game.ship
    if not ship.alive:
        return InputState()
    width = game.cfg.display.width
    if _threat(game, ship.x) is not None:
        # Step to whichever nearby spot is safe, preferring the closer one.
        for offset in (60, 120, 180, 260, 340):
            for direction in (1, -1):
                x = ship.x + direction * offset
                if ship.w / 2 <= x <= width - ship.w / 2 and _threat(game, x) is None:
                    return InputState(left=direction < 0, right=direction > 0, fire=True)
        return InputState(fire=True, special=True)

    target = None
    if game.boss and game.boss.alive:
        target = game.boss.x
    elif game.pickups:
        target = game.pickups[0].x
    elif game.enemies:
        target = min(game.enemies, key=lambda e: abs(e.x - ship.x)).x
    left = target is not None and target < ship.x - 6 and _threat(game, ship.x - 40) is None
    right = target is not None and target > ship.x + 6 and _threat(game, ship.x + 40) is None
    return InputState(left=left, right=right, fire=True)
