"""A simple bot used by smoke tests and balance checks (--autoplay).

It avoids beams and predicted bullet paths, grabs nearby pickups, lines up
under targets and fires the shockwave when things get crowded. Not part of
normal play.
"""
import math

from .game import InputState


def _danger(game, x, y, horizon=0.9):
    """Rough danger score for the ship standing at (x, y)."""
    ship = game.ship
    half_w, half_h = ship.w * 0.45, ship.h * 0.45
    score = 0.0
    for shot in game.enemy_shots:
        for t in (0.0, 0.15, 0.3, 0.5, horizon):
            sx, sy = shot.x + shot.vx * t, shot.y + shot.vy * t
            if abs(sx - x) < half_w + shot.w and abs(sy - y) < half_h + shot.h:
                score += 2.0 - t
                break
    beam_w = game.cfg.enemy.beam_width * 2.2
    for enemy in game.enemies:
        if enemy.state in ("beam_charge", "beam") and abs(enemy.beam_x - x) < beam_w + half_w:
            score += 3.0
        if enemy.state in ("dive", "strike", "fall", "drift") and \
                math.hypot(enemy.x - x, enemy.y - y) < 110:
            score += 2.0
    if game.boss:
        for part in game.boss.parts:
            if part.beam_state and abs(part.x - x) < beam_w * 1.6 + half_w:
                score += 3.0
    return score


def autopilot(game):
    ship = game.ship
    if not ship.alive:
        return InputState()
    width = game.cfg.display.width
    home = ship.home_y(game.cfg)

    target_x, target_y = ship.x, home
    if game.pickups:
        p = min(game.pickups, key=lambda p: abs(p.x - ship.x) + abs(p.y - ship.y))
        target_x, target_y = p.x, max(p.y, game.cfg.display.height * 0.6)
    else:
        targets = game.targets()
        if targets:
            target_x = min(targets, key=lambda t: abs(t[1] - ship.x))[1]

    best, best_cost = (0, 0), None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x = min(width - 30, max(30, ship.x + dx * 60))
            y = ship.y + dy * 40
            cost = _danger(game, x, y) * 10 + abs(target_x - x) / 100 + abs(target_y - y) / 200
            if best_cost is None or cost < best_cost:
                best, best_cost = (dx, dy), cost
    dx, dy = best
    crowded = len(game.enemy_shots) >= 10 or (ship.health < 40 and game.enemy_shots)
    return InputState(left=dx < 0, right=dx > 0, up=dy < 0, down=dy > 0, fire=True,
                      special=crowded and game.shock_charge >= 1.0)
