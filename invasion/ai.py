"""Enemy and boss behavior: how each kind moves and when it attacks.

Every attack is telegraphed: ordinary shooters glow briefly, lancers and
boss lasers draw a thin warning line first, wasps shake before diving, and
mines blink before exploding.
"""
import math

from .entities import bezier, path_length


def setup(enemy, spawn, game):
    """Place a freshly spawned enemy on its entry path."""
    rng = game.rng
    spec = enemy.spec
    enemy.start = spawn.start
    enemy.x, enemy.y = spawn.start
    enemy.phase = rng.uniform(0, math.tau)
    enemy.state = spawn.pattern if spawn.pattern in ("stream", "cross") else "enter"
    if enemy.state in ("stream", "cross"):
        enemy.end = spawn.end
        enemy.amp, enemy.freq = spawn.amp, spawn.freq
        dist = math.hypot(spawn.end[0] - spawn.start[0], spawn.end[1] - spawn.start[1])
        enemy.duration = dist / spec.speed
    else:
        enemy.anchor = spawn.anchor
        enemy.ctrl = spawn.ctrl
        enemy.duration = max(0.5, path_length(spawn.start, *spawn.ctrl, spawn.anchor) / spec.speed)
    enemy.fire_timer = rng.uniform(0.5, 1.0) * spec.fire_interval * game.fire_scale + 0.6
    enemy.action_timer = rng.uniform(3.0, 7.0)


def setup_hazard(enemy, game):
    rng = game.rng
    width = game.cfg.display.width
    enemy.x, enemy.y = rng.uniform(40, width - 40), -enemy.h
    enemy.phase = rng.uniform(0, math.tau)
    if enemy.kind == "asteroid":
        enemy.state = "fall"
        enemy.vx = rng.uniform(-50, 50)
        enemy.vy = enemy.spec.speed * rng.uniform(0.8, 1.25)
        enemy.spin = rng.uniform(-120, 120)
    else:
        enemy.state = "drift"
        enemy.vy = enemy.spec.speed * rng.uniform(0.8, 1.2)


def _enter_from_top(enemy, game):
    """Send an enemy that left the bottom of the screen back to its post."""
    enemy.state = "enter"
    enemy.t = 0.0
    ax, ay = enemy.anchor
    enemy.start = (ax, -40)
    enemy.x, enemy.y = enemy.start
    enemy.ctrl = ((ax, ay * 0.3), (ax, ay * 0.7))
    enemy.duration = max(0.5, (ay + 40) / enemy.spec.speed)


def update(enemy, game, dt):
    cfg, rng, ship = game.cfg, game.rng, game.ship
    width, height = cfg.display.width, cfg.display.height
    er = cfg.enemy
    spec = enemy.spec
    enemy.age += dt
    enemy.t += dt
    enemy.flash = max(0.0, enemy.flash - dt)
    state = enemy.state

    if state == "enter":
        p = min(1.0, enemy.t / enemy.duration)
        enemy.x, enemy.y = bezier(enemy.start, enemy.ctrl[0], enemy.ctrl[1], enemy.anchor, p)
        if p >= 1.0:
            enemy.state = "aim" if enemy.kind == "wasp" else "hold"
            enemy.t = 0.0
    elif state in ("stream", "cross"):
        p = enemy.t / enemy.duration
        x0, y0 = enemy.start
        x1, y1 = enemy.end
        enemy.x = x0 + (x1 - x0) * p
        enemy.y = y0 + (y1 - y0) * p
        if state == "stream":
            enemy.x += enemy.amp * math.sin(p * enemy.freq * math.tau)
        else:
            enemy.y += 10 * math.sin(enemy.age * 3)
        if p >= 1.0:
            enemy.alive = False
            enemy.escaped = True
    elif state == "hold":
        _hold(enemy, game, dt)
    elif state == "dive":
        enemy.x += enemy.vx * dt
        enemy.y += enemy.vy * dt
        if enemy.y > height + enemy.h:
            _enter_from_top(enemy, game)
    elif state == "aim":
        if enemy.t >= er.wasp_aim:
            enemy.state = "strike"
            enemy.t = 0.0
            enemy.vx, enemy.vy = 0.0, spec.speed
    elif state == "strike":
        if ship.alive:
            want = max(-260.0, min(260.0, (ship.x - enemy.x) * 2.5))
            enemy.vx += (want - enemy.vx) * min(1.0, dt * 3)
        enemy.x += enemy.vx * dt
        enemy.y += enemy.vy * dt
        if enemy.y > height + enemy.h:
            enemy.alive = False
            enemy.escaped = True
    elif state == "reposition":
        dx = enemy.beam_x - enemy.x
        step = spec.speed * dt
        if abs(dx) <= step:
            enemy.x = enemy.beam_x
            enemy.state = "beam_charge"
            enemy.t = 0.0
        else:
            enemy.x += math.copysign(step, dx)
    elif state == "beam_charge":
        if enemy.t >= er.beam_telegraph:
            enemy.state = "beam"
            enemy.t = 0.0
            enemy.beam_hit = False
    elif state == "beam":
        if enemy.t >= er.beam_time:
            enemy.state = "hold"
            enemy.t = 0.0
            enemy.action_timer = spec.fire_interval * game.fire_scale * rng.uniform(0.8, 1.2)
    elif state == "fall":
        enemy.x += enemy.vx * dt
        enemy.y += enemy.vy * dt
        if enemy.y > height + enemy.h or enemy.x < -enemy.w or enemy.x > width + enemy.w:
            enemy.alive = False
    elif state == "drift":
        enemy.y += enemy.vy * dt
        enemy.x += 30 * math.cos(enemy.age * 1.3 + enemy.phase) * dt
        if enemy.armed >= 0:
            enemy.armed -= dt
            if enemy.armed <= 0:
                game.explode_mine(enemy, harmless=False)
        elif ship.alive and math.hypot(ship.x - enemy.x, ship.y - enemy.y) < er.mine_trigger:
            enemy.armed = er.mine_fuse
            game.emit("mine_armed", x=enemy.x, y=enemy.y)
        if enemy.y > height + enemy.h:
            enemy.alive = False

    # Ordinary shooting: wind up (glow), then fire.
    if spec.fire in ("single", "twin", "spread", "missile") and enemy.state in ("hold", "stream"):
        if enemy.charge_timer > 0:
            enemy.charge_timer -= dt
            if enemy.charge_timer <= 0:
                game.enemy_fire(enemy)
        else:
            enemy.fire_timer -= dt
            if enemy.fire_timer <= 0:
                enemy.fire_timer = spec.fire_interval * game.fire_scale * rng.uniform(0.8, 1.2)
                if game.can_enemy_fire(enemy):
                    enemy.charge_timer = er.charge_time


def _hold(enemy, game, dt):
    rng, ship, cfg = game.rng, game.ship, game.cfg
    width = cfg.display.width
    ease = min(1.0, enemy.t / 0.6)       # blend into the idle motion
    ax, ay = enemy.anchor
    kind = enemy.kind
    enemy.action_timer -= dt

    if kind == "drone":
        enemy.x = ax + ease * 34 * math.sin(enemy.age * 1.6 + enemy.phase)
        enemy.y = ay + ease * 12 * math.sin(enemy.age * 2.2 + enemy.phase)
        if enemy.action_timer <= 0 and ship.alive and game.level >= 2:
            enemy.action_timer = rng.uniform(5.0, 9.0)
            dx, dy = ship.x - enemy.x, ship.y - enemy.y
            dist = max(1.0, math.hypot(dx, dy))
            speed = enemy.spec.speed * 1.15
            enemy.vx, enemy.vy = dx / dist * speed, dy / dist * speed
            enemy.state = "dive"
            enemy.t = 0.0
            game.emit("dive_warning", x=enemy.x, y=enemy.y)
    elif kind == "striker":
        if enemy.vx == 0:
            enemy.vx = enemy.spec.speed * 0.45 * (1 if rng.random() < 0.5 else -1)
        enemy.x += enemy.vx * dt * ease
        if enemy.x < 50 or enemy.x > width - 50:
            enemy.x = max(50.0, min(width - 50.0, enemy.x))
            enemy.vx = -enemy.vx
        enemy.y = ay + ease * 10 * math.sin(enemy.age * 2.0 + enemy.phase)
    elif kind == "lancer":
        enemy.y = ay + ease * 8 * math.sin(enemy.age * 1.8 + enemy.phase)
        if enemy.action_timer <= 0 and ship.alive and game.can_beam(enemy):
            enemy.beam_x = max(40.0, min(width - 40.0, ship.x + rng.uniform(-70, 70)))
            enemy.state = "reposition"
            enemy.t = 0.0
    else:  # guardian, dreadnought: drift between positions
        enemy.x += (ax - enemy.x) * min(1.0, dt * 0.8)
        enemy.y += (ay - enemy.y) * min(1.0, dt * 0.8)
        enemy.x += ease * 6 * math.sin(enemy.age * 1.1 + enemy.phase) * dt
        if enemy.action_timer <= 0:
            enemy.action_timer = rng.uniform(4.0, 6.5)
            low, high = game.hold_zone()
            enemy.anchor = (rng.uniform(90, width - 90), rng.uniform(low, high))


# ----------------------------------------------------------------------
# Boss
# ----------------------------------------------------------------------
def update_boss(boss, game, dt):
    cfg = game.cfg
    br = cfg.boss
    boss.move(dt, br.enter_speed, cfg.display.width)
    for part in boss.parts:
        part.flash = max(0.0, part.flash - dt)
    if boss.entering or game.banner_timer > 0:
        return
    if boss.stage_timer > 0:
        boss.stage_timer -= dt
        return
    rage = br.stage_rage[min(boss.stage, len(br.stage_rage)) - 1]
    for part in boss.active_parts():
        _update_part(boss, part, game, dt, rage)


def _update_part(boss, part, game, dt, rage):
    cfg, ship, rng = game.cfg, game.ship, game.rng
    br, er = cfg.boss, cfg.enemy
    interval = part.spec.interval * rage

    if part.kind == "laser":
        if part.beam_state == "charge":
            part.beam_timer -= dt
            if part.beam_timer <= 0:
                part.beam_state, part.beam_timer, part.beam_hit = "beam", er.beam_time * 1.4, False
        elif part.beam_state == "beam":
            part.beam_timer -= dt
            if part.beam_timer <= 0:
                part.beam_state = None
                part.fire_timer = interval * rng.uniform(0.85, 1.15)
        else:
            part.fire_timer -= dt
            if part.fire_timer <= 0 and ship.alive:
                part.beam_state, part.beam_timer = "charge", er.beam_telegraph * 1.1
        return

    if part.burst_left > 0:
        part.burst_timer -= dt
        if part.burst_timer <= 0:
            game.boss_aimed_shot(part, *br.cannon_bullet)
            part.burst_left -= 1
            part.burst_timer = br.burst_gap
        return

    if part.charge_timer > 0:
        part.charge_timer -= dt
        if part.charge_timer <= 0:
            _part_attack(boss, part, game)
        return

    part.fire_timer -= dt
    if part.fire_timer <= 0:
        part.fire_timer = interval * rng.uniform(0.85, 1.15)
        if ship.alive:
            part.charge_timer = 0.45 if part.kind != "hangar" else 0.6


def _part_attack(boss, part, game):
    br = game.cfg.boss
    kind = part.kind
    if kind == "cannon":
        part.burst_left, part.burst_timer = br.burst_count, 0.0
    elif kind == "spread":
        game.boss_fan(part, br.spread_count, br.spread_step, *br.spread_bullet)
    elif kind == "missile":
        game.spawn_missile(part.x, part.y + part.h / 2, *br.missile)
        if boss.stage >= 2:
            game.spawn_missile(part.x + 14, part.y + part.h / 2, *br.missile)
    elif kind == "hangar":
        game.launch_minions(part, br.hangar_minions)
    elif kind == "core":
        part.ring_turn += 1
        if part.ring_turn % 2:
            game.boss_ring(part, br.core_ring, *br.core_bullet)
        else:
            part.burst_left, part.burst_timer = br.burst_count + 2, 0.0
