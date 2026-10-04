"""The game simulation: state machine, rules and collisions. No drawing.

The simulation advances in fixed steps (1 / sim_hz seconds) and takes all
of its randomness from one seeded random.Random, so the same seed plus the
same inputs per step always produce the same run.

Damage rules:
  * the ship has a hull bar (100). Armor (up to 100) soaks damage first.
    Shield charges block one hit each, completely.
  * after any hull/armor damage the ship ignores damage for hurt_iframes
    seconds, so one collision or one burst can never chain into a wipe.
  * hull at 0 costs a ship. 3 ships = 3 hull bars. After respawning the
    ship blinks and is invulnerable for invulnerable_time.
  * losing a ship clears the weapon, buffs, shield and armor. The
    shockwave keeps its charge.

Pickup rules:
  * weapons: one at a time, replace the current one, picking up the same
    weapon refills it; limited by ammo or time, then back to the blaster.
  * repair / armor / shield stack up to their caps. Wingmen, overdrive and
    magnet are timed; picking one up again refreshes it to full.
  * pickups fall and are lost if they leave the bottom of the screen.
  * a new run starts with nothing but the blaster and a charged shockwave.
"""
import math
import random
from dataclasses import dataclass, replace

from . import ai, weapons
from .config import Config
from .entities import Boss, Enemy, EnemyShot, Hardpoint, Pickup, Ship, Shockwave, Shot
from .levels import Spawn, build_wave, level_spec

GAME_VERSION = "3.0.0"

TITLE = "title"
PLAYING = "playing"
GAME_OVER = "game_over"


@dataclass
class InputState:
    left: bool = False
    right: bool = False
    up: bool = False
    down: bool = False
    fire: bool = False
    special: bool = False      # edge-triggered: true for one step only


class Game:
    def __init__(self, cfg=None, seed=None):
        self.cfg = cfg or Config()
        self.dt = 1.0 / self.cfg.display.sim_hz
        self.fixed_seed = seed
        self.high_score = 0
        self.run_count = 0
        self.events = []
        self._accumulator = 0.0
        self._reset_run(seed or 0)
        self.state = TITLE

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------
    def start_run(self, seed=None):
        if seed is None:
            seed = self.fixed_seed if self.fixed_seed is not None else random.randrange(1, 2**31)
        self.run_count += 1
        self._reset_run(seed)
        self.state = PLAYING
        self.emit("run_started", run_id=self.run_id, seed=self.seed, version=GAME_VERSION)
        self._start_level(1)

    def restart(self, seed=None):
        """R after game over. Ignored while a run is in progress."""
        if self.state == GAME_OVER:
            self.start_run(seed)
            return True
        return False

    def _reset_run(self, seed):
        cfg = self.cfg
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.run_id = f"{self.seed}-{self.run_count}"
        self.state = PLAYING
        self.paused = False
        self.ticks = 0
        self.time = 0.0
        self.score = 0
        self.kills = 0
        self.lives = cfg.player.start_lives
        self.combo = 0
        self.combo_timer = 0.0
        self.multiplier = 1
        self.ship = Ship(cfg)
        self.shock_charge = 1.0
        self.shots = []
        self.enemy_shots = []
        self.enemies = []
        self.boss = None
        self.pickups = []
        self.shockwaves = []
        self.level = 0
        self.spec = None
        self.phase = "intro"
        self.wave = 0
        self.wave_clock = 0.0
        self.wave_queue = []
        self.cargo_wave = 0
        self.banner_timer = 0.0
        self.clear_timer = 0.0
        self.pity_timer = 0.0
        self.fire_scale = 1.0
        self.bullet_scale = 1.0
        self.hp_scale = 1.0
        self.shots_cap = cfg.enemy.shots_cap
        self.game_over_timer = 0.0
        self.game_over_emitted = False
        self.new_high_score = False
        self.next_uid = 1
        self._accumulator = 0.0

    def _end_run(self):
        self.state = GAME_OVER
        self.paused = False
        self.new_high_score = self.score > self.high_score
        self.high_score = max(self.high_score, self.score)
        if not self.game_over_emitted:
            self.game_over_emitted = True
            self.emit("game_over", run_id=self.run_id, seed=self.seed, score=self.score,
                      level=self.level, wave=self.wave, kills=self.kills, ticks=self.ticks,
                      duration=round(self.ticks * self.dt, 2), version=GAME_VERSION)

    # ------------------------------------------------------------------
    # Pause and time
    # ------------------------------------------------------------------
    def set_paused(self, paused):
        if self.state != PLAYING or paused == self.paused:
            return False
        self.paused = paused
        self.emit("paused" if paused else "resumed")
        return True

    def toggle_pause(self):
        return self.set_paused(not self.paused)

    def advance(self, frame_dt, inp):
        """Feed real elapsed time; runs as many fixed steps as it covers.

        Returns the number of steps run. Edge-triggered input (special) is
        only applied to the first step, so callers should clear it when
        this returns more than zero.
        """
        self._accumulator += min(frame_dt, 0.25)
        steps = 0
        limit = self.cfg.display.max_steps_per_frame
        while self._accumulator >= self.dt - 1e-9 and steps < limit:
            self.step(inp if steps == 0 else replace(inp, special=False))
            self._accumulator -= self.dt
            steps += 1
        if steps == limit:
            self._accumulator = 0.0
        return steps

    def step(self, inp):
        """Advance the simulation by exactly one fixed step."""
        if self.state != PLAYING or self.paused:
            return
        dt = self.dt
        self.ticks += 1
        self.time += dt
        self._update_timers(dt)
        self._update_ship(dt, inp)
        self._update_shots(dt)
        self._update_level(dt)
        for enemy in self.enemies:
            if enemy.alive:
                ai.update(enemy, self, dt)
        if self.boss:
            ai.update_boss(self.boss, self, dt)
        self._update_shockwaves(dt)
        self._update_pickups(dt)
        self._collisions()
        self._cleanup()
        if self.game_over_timer > 0:
            self.game_over_timer -= dt
            if self.game_over_timer <= 0:
                self._end_run()

    def _update_timers(self, dt):
        self.banner_timer = max(0.0, self.banner_timer - dt)
        self.pity_timer += dt
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 0
                self.multiplier = 1
        if self.shock_charge < 1.0:
            self.shock_charge = min(1.0, self.shock_charge + dt / self.cfg.player.shock_recharge)
            if self.shock_charge >= 1.0:
                self.emit("shock_ready")

    # ------------------------------------------------------------------
    # Levels and waves
    # ------------------------------------------------------------------
    def _start_level(self, number):
        cfg, er = self.cfg, self.cfg.enemy
        self.level = number
        self.spec = spec = level_spec(number, cfg)
        k = number - 1
        self.hp_scale = 1 + er.hp_per_level * k
        self.fire_scale = 1 / min(er.fire_rate_max, 1 + er.fire_rate_per_level * k)
        self.bullet_scale = min(er.bullet_speed_max, 1 + er.bullet_speed_per_level * k)
        self.shots_cap = min(er.shots_cap_max, er.shots_cap + er.shots_cap_per_level * k)
        self.wave = 0
        self.wave_queue = []
        self.wave_clock = 0.0
        self.phase = "intro"
        self.banner_timer = cfg.flow.boss_banner if spec.is_boss else cfg.flow.level_banner
        self.cargo_wave = 0 if spec.is_boss else self.rng.randint(1, max(1, spec.waves - 1))
        self.emit("level_started", level=number, name=spec.name, boss=spec.is_boss, hint=spec.hint,
                  theme=spec.theme)
        if spec.is_boss:
            self.boss = Boss(cfg, spec.boss, spec.boss_cycle, self.next_uid)
            self.next_uid += len(self.boss.parts)
            self.emit("boss_spawned", name=self.boss.label, stages=self.boss.stages)

    def _update_level(self, dt):
        spec = self.spec
        if self.phase == "intro":
            if self.banner_timer <= 0:
                self.phase = "boss" if spec.is_boss else "waves"
                if not spec.is_boss:
                    self._next_wave()
        elif self.phase == "waves":
            self.wave_clock += dt
            while self.wave_queue and self.wave_queue[0].time <= self.wave_clock:
                self._spawn(self.wave_queue.pop(0))
            self._spawn_hazards(dt)
            if not self.wave_queue:
                fighters = sum(1 for e in self.enemies if e.alive and not e.spec.hazard)
                if self.wave < spec.waves:
                    if fighters <= self.cfg.flow.wave_trickle or self.wave_clock >= self.cfg.flow.wave_max_time:
                        self._next_wave()
                elif fighters == 0 and self.lives > 0:
                    self._level_clear()
        elif self.phase == "clear":
            self.clear_timer -= dt
            if self.clear_timer <= 0 and self.lives > 0:
                self._start_level(self.level + 1)

    def _next_wave(self):
        self.wave += 1
        self.wave_clock = 0.0
        spawns = build_wave(self.spec, self.wave, self.cfg, self.rng,
                            with_cargo=self.wave == self.cargo_wave)
        self.wave_queue = sorted(spawns, key=lambda s: s.time)
        self.emit("wave_started", level=self.level, wave=self.wave, waves=self.spec.waves)

    def _level_clear(self):
        self.phase = "clear"
        self.clear_timer = self.cfg.flow.level_clear_delay
        bonus = 500 * self.level
        self.score += bonus
        self.enemy_shots.clear()
        self.emit("level_cleared", level=self.level, bonus=bonus)

    def _new_enemy(self, kind):
        spec = self.cfg.enemies[kind]
        hp = spec.hp if spec.hazard else math.ceil(spec.hp * self.hp_scale)
        enemy = Enemy(self.next_uid, kind, spec, hp)
        self.next_uid += 1
        self.enemies.append(enemy)
        return enemy

    def _spawn(self, spawn):
        enemy = self._new_enemy(spawn.kind)
        ai.setup(enemy, spawn, self)
        if spawn.kind == "cargo":
            self.emit("cargo_spotted")
        return enemy

    def _spawn_hazards(self, dt):
        for kind, rate in self.spec.hazards.items():
            if self.rng.random() < rate * dt:
                ai.setup_hazard(self._new_enemy(kind), self)

    def hold_zone(self):
        top = self.cfg.display.hud_height + 60
        if self.boss:
            top = max(top, self.boss.y + self.boss.h / 2 + 40)
        return top, max(top + 40, self.cfg.display.height * 0.42)

    def launch_minions(self, part, count):
        alive = sum(1 for e in self.enemies if e.alive and e.minion)
        low, high = self.hold_zone()
        for _ in range(min(count, self.cfg.boss.minion_cap - alive)):
            kind = "wasp" if self.rng.random() < 0.4 else "drone"
            anchor = (self.rng.uniform(80, self.cfg.display.width - 80), self.rng.uniform(low, high))
            start = (part.x, part.y + part.h / 2)
            ctrl = ((part.x, start[1] + 120), (anchor[0], anchor[1] + 80))
            enemy = self._spawn(Spawn(0, kind, "swoop", start, anchor, ctrl))
            enemy.minion = True
        self.emit("minions_launched", x=part.x, y=part.y)

    # ------------------------------------------------------------------
    # Player
    # ------------------------------------------------------------------
    def _update_ship(self, dt, inp):
        ship, pc = self.ship, self.cfg.player
        if not ship.alive:
            if self.lives > 0:
                ship.respawn_timer -= dt
                if ship.respawn_timer <= 0:
                    ship.alive = True
                    ship.hull = pc.max_hull
                    ship.x, ship.y = self.cfg.display.width / 2, Ship.home_y(self.cfg)
                    ship.invulnerable_timer = pc.invulnerable_time
                    ship.fire_timer = 0.0
                    self.emit("respawned")
            return
        ship.invulnerable_timer = max(0.0, ship.invulnerable_timer - dt)
        ship.hurt_timer = max(0.0, ship.hurt_timer - dt)
        ship.move(int(inp.right) - int(inp.left), int(inp.down) - int(inp.up), dt)

        for name in list(ship.buffs):
            ship.buffs[name] -= dt
            if ship.buffs[name] <= 0:
                del ship.buffs[name]
                self.emit("buff_expired", kind=name)
        if ship.weapon and ship.weapon != "laser" and self.cfg.weapons[ship.weapon].duration:
            ship.weapon_time -= dt
            if ship.weapon_time <= 0:
                self.weapon_empty()

        ship.fire_timer = max(0.0, ship.fire_timer - dt)
        ship.wing_timer = max(0.0, ship.wing_timer - dt)
        ship.laser_on = False
        if inp.fire:
            if ship.weapon == "laser":
                weapons.update_laser(self, dt)
            elif ship.fire_timer <= 0:
                weapons.fire(self)
            if "wingmen" in ship.buffs and ship.wing_timer <= 0:
                ship.wing_timer = 0.2 * weapons.cooldown_mult(self)
                for side in (-1, 1):
                    weapons.blaster(self, ship.x + side * 44, ship.y)
        if inp.special:
            self._use_shockwave()

    def weapon_empty(self):
        ship = self.ship
        if ship.weapon:
            self.emit("weapon_empty", weapon=ship.weapon)
        ship.weapon = None
        ship.ammo = 0
        ship.weapon_time = 0.0
        ship.laser_on = False

    def _use_shockwave(self):
        if self.shock_charge < 1.0 or not self.ship.alive:
            return
        pc = self.cfg.player
        self.shock_charge = 0.0
        self.shockwaves.append(Shockwave(self.ship.x, self.ship.y, pc.shock_radius, pc.shock_speed))
        self.emit("shockwave", x=self.ship.x, y=self.ship.y)

    def _damage_player(self, amount, cause):
        """Returns 'blocked' (shield), 'hit' (damage taken) or None (immune)."""
        ship, pc = self.ship, self.cfg.player
        if not ship.alive or ship.invulnerable_timer > 0:
            return None
        if ship.shield > 0:
            ship.shield -= 1
            self.emit("shield_block", x=ship.x, y=ship.y, left=ship.shield)
            return "blocked"
        if ship.hurt_timer > 0:
            return None
        soaked = min(ship.armor, amount)
        ship.armor -= soaked
        ship.hull -= amount - soaked
        ship.hurt_timer = pc.hurt_iframes
        self.combo = 0
        self.multiplier = 1
        self.combo_timer = 0.0
        self.emit("player_damaged", x=ship.x, y=ship.y, amount=amount, hull=max(0.0, ship.hull),
                  armor=ship.armor, cause=cause)
        if ship.hull <= 0:
            self._lose_life(cause)
        return "hit"

    def _lose_life(self, cause):
        ship = self.ship
        ship.alive = False
        ship.hull = 0.0
        ship.reset_loadout()
        self.lives -= 1
        self.enemy_shots.clear()
        for enemy in self.enemies:
            enemy.charge_timer = 0.0
            if enemy.state in ("reposition", "beam_charge", "beam"):
                enemy.state, enemy.t = "hold", 0.0
                enemy.action_timer = 2.0
        if self.boss:
            for part in self.boss.parts:
                part.charge_timer = 0.0
                part.burst_left = 0
                part.beam_state = None
                part.fire_timer = max(part.fire_timer, 1.5)
        self.emit("player_destroyed", x=ship.x, y=ship.y, lives=self.lives, cause=cause)
        if self.lives <= 0:
            self.game_over_timer = self.cfg.player.game_over_delay
        else:
            ship.respawn_timer = self.cfg.player.respawn_delay

    # ------------------------------------------------------------------
    # Enemy attacks (called from ai.py)
    # ------------------------------------------------------------------
    def can_enemy_fire(self, enemy):
        ship = self.ship
        return (ship.alive and len(self.enemy_shots) < self.shots_cap
                and enemy.y > self.cfg.display.hud_height
                and ship.y - enemy.y >= self.cfg.enemy.safe_distance)

    def can_beam(self, enemy):
        beams = sum(1 for e in self.enemies if e.state in ("reposition", "beam_charge", "beam"))
        return beams < 2 and self.ship.y - enemy.y >= self.cfg.enemy.safe_distance

    def _aim(self, x, y, limit):
        angle = math.degrees(math.atan2(self.ship.x - x, max(1.0, self.ship.y - y)))
        return max(-limit, min(limit, angle))

    def _enemy_bullet(self, x, y, angle, speed, damage, kind="bullet", size=(8, 14)):
        rad = math.radians(angle)
        self.enemy_shots.append(EnemyShot(kind, x, y, math.sin(rad) * speed, math.cos(rad) * speed,
                                          size, damage))

    def enemy_fire(self, enemy):
        if not self.ship.alive:
            return
        spec = enemy.spec
        speed = spec.bullet_speed * self.bullet_scale
        x, y = enemy.x, enemy.y + enemy.h / 2
        if spec.fire == "single":
            self._enemy_bullet(x, y, 0.0, speed, spec.bullet_damage)
        elif spec.fire == "twin":
            angle = self._aim(x, y, 30)
            for dx in (-11, 11):
                self._enemy_bullet(x + dx, y, angle, speed, spec.bullet_damage)
        elif spec.fire == "spread":
            center = self._aim(x, y, 25)
            for i in range(5):
                self._enemy_bullet(x, y, center + (i - 2) * 14, speed, spec.bullet_damage,
                                   "orb", (12, 12))
        elif spec.fire == "missile":
            self.spawn_missile(x, y, spec.bullet_speed, spec.bullet_damage)
            for side in (-1, 1):
                self._enemy_bullet(x + side * 30, y, side * 12.0, speed, 8)

    def spawn_missile(self, x, y, speed, damage):
        er = self.cfg.enemy
        shot = EnemyShot("missile", x, y, 0.0, speed * 0.6, (8, 18), damage)
        shot.turn_rate = er.missile_turn
        shot.life = er.missile_life
        shot.speed = speed
        self.enemy_shots.append(shot)

    def boss_aimed_shot(self, part, speed, damage):
        y = part.y + part.h / 2
        self._enemy_bullet(part.x, y, self._aim(part.x, y, 40), speed * self.bullet_scale, damage,
                           "bolt", (8, 18))

    def boss_fan(self, part, count, step, speed, damage):
        y = part.y + part.h / 2
        center = self._aim(part.x, y, 30)
        for i in range(count):
            self._enemy_bullet(part.x, y, center + (i - (count - 1) / 2) * step,
                               speed * self.bullet_scale, damage, "orb", (12, 12))

    def boss_ring(self, part, count, speed, damage):
        offset = (part.ring_turn * 13) % 360
        for i in range(count):
            self._enemy_bullet(part.x, part.y, offset + i * 360 / count, speed * self.bullet_scale,
                               damage, "orb", (12, 12))

    def explode_mine(self, mine, harmless):
        if not mine.alive and mine.armed < -1:
            return
        er = self.cfg.enemy
        mine.alive = False
        mine.armed = -2.0
        self.emit("explosion", x=mine.x, y=mine.y, radius=er.mine_radius)
        ship = self.ship
        if not harmless and ship.alive and math.hypot(ship.x - mine.x, ship.y - mine.y) <= er.mine_radius:
            self._damage_player(er.mine_damage, "mine")
        for other in self.enemies:
            if other.alive and other is not mine and \
                    math.hypot(other.x - mine.x, other.y - mine.y) <= er.mine_radius:
                self._damage_enemy(other, 6)

    # ------------------------------------------------------------------
    # Damage to enemies and the boss
    # ------------------------------------------------------------------
    def targets(self):
        """Everything the player can damage right now: (object, x, y)."""
        top = self.cfg.display.hud_height
        out = [(e, e.x, e.y) for e in self.enemies if e.alive and e.y > top - 10]
        if self.boss and self._boss_vulnerable():
            out += [(p, p.x, p.y) for p in self.boss.active_parts()]
        return out

    def target_rects(self):
        out = [(e, e.rect) for e in self.enemies if e.alive]
        if self.boss and self._boss_vulnerable():
            out += [(p, p.rect) for p in self.boss.active_parts()]
        return out

    def boss_hull_rect(self):
        if not self.boss:
            return None
        r = self.boss.rect
        return r.inflate(-r.w * 0.1, -r.h * 0.25)

    def _boss_vulnerable(self):
        boss = self.boss
        return boss is not None and not boss.entering and boss.stage_timer <= 0 and self.banner_timer <= 0

    def damage_target(self, target, damage):
        if isinstance(target, Hardpoint):
            self._damage_part(target, damage)
        else:
            self._damage_enemy(target, damage)

    def _damage_enemy(self, enemy, damage):
        if not enemy.alive:
            return
        if enemy.flash <= 0:
            self.emit("enemy_hit", kind=enemy.kind, x=enemy.x, y=enemy.y)
        enemy.hp -= damage
        enemy.flash = self.cfg.enemy.hit_flash
        if enemy.hp <= 0:
            self._kill_enemy(enemy)

    def _add_combo(self):
        pc = self.cfg.player
        self.combo += 1
        self.combo_timer = pc.combo_window
        new = min(pc.combo_max, 1 + self.combo // pc.combo_step)
        if new > self.multiplier:
            self.emit("multiplier", value=new)
        self.multiplier = new

    def _kill_enemy(self, enemy):
        enemy.alive = False
        if not enemy.spec.hazard:
            self.kills += 1
            self._add_combo()
        points = enemy.points * self.multiplier
        self.score += points
        self.emit("enemy_killed", kind=enemy.kind, x=enemy.x, y=enemy.y, points=points,
                  big=enemy.spec.threat >= 5)
        if enemy.kind == "mine":
            self.explode_mine(enemy, harmless=True)
        if enemy.kind == "cargo":
            for dx in (-26, 26):
                self._drop_pickup(enemy.x + dx, enemy.y)
        else:
            self._maybe_drop(enemy)

    def _damage_part(self, part, damage):
        boss = self.boss
        if not boss or not part.alive or part.stage != boss.stage or not self._boss_vulnerable():
            return False
        if part.flash <= 0:
            self.emit("part_hit", x=part.x, y=part.y)
        part.hp -= damage
        part.flash = self.cfg.enemy.hit_flash
        if part.hp > 0:
            return True
        part.alive = False
        part.beam_state = None
        points = self.cfg.boss.part_points * self.multiplier
        self.score += points
        self.emit("part_destroyed", kind=part.kind, x=part.x, y=part.y, points=points)
        if boss.active_parts():
            return True
        if boss.stage >= boss.stages:
            self._boss_defeated()
        else:
            boss.stage += 1
            boss.stage_timer = self.cfg.boss.stage_pause
            self.enemy_shots.clear()
            self.emit("boss_stage", stage=boss.stage, stages=boss.stages, name=boss.label)
        return True

    def _boss_defeated(self):
        boss = self.boss
        self.score += boss.points
        self.kills += 1
        self.enemy_shots.clear()
        self.emit("boss_defeated", name=boss.label, x=boss.x, y=boss.y, w=boss.w, h=boss.h,
                  points=boss.points, level=self.level)
        for dx in (-60, 0, 60):
            self._drop_pickup(boss.x + dx, boss.y + boss.h / 2)
        for enemy in self.enemies:
            if enemy.minion and enemy.alive:
                self._kill_enemy(enemy)
        self.boss = None
        self._level_clear()

    # ------------------------------------------------------------------
    # Pickups
    # ------------------------------------------------------------------
    def _maybe_drop(self, enemy):
        dc = self.cfg.drops
        guaranteed = self.pity_timer >= dc.pity_time and not enemy.spec.hazard
        if not guaranteed:
            if len(self.pickups) >= dc.max_on_screen or self.rng.random() >= enemy.spec.drop_chance:
                return
        self._drop_pickup(enemy.x, enemy.y)

    def _drop_pickup(self, x, y):
        cfg, ship = self.cfg, self.ship
        dc, pc = cfg.drops, cfg.player
        weights = {}
        for kind, spec in cfg.pickups.items():
            weight = spec.weight
            if kind == "life" and self.lives >= pc.max_lives:
                continue
            if kind == "shield" and ship.shield >= pc.max_shield:
                continue
            if kind == "repair" and ship.hull < pc.max_hull / 2:
                weight *= dc.low_hull_repair_boost
            weights[kind] = weight
        for kind in cfg.weapons:
            weights[kind] = dc.weapon_weight
        kinds = list(weights)
        kind = self.rng.choices(kinds, weights=[weights[k] for k in kinds])[0]
        category = "weapon" if kind in cfg.weapons else "utility"
        x = max(20.0, min(cfg.display.width - 20.0, x))
        self.pickups.append(Pickup(kind, category, x, y, self.rng.uniform(0, math.tau)))
        self.pity_timer = 0.0
        self.emit("pickup_dropped", kind=kind, x=x, y=y)

    def _update_pickups(self, dt):
        dc = self.cfg.drops
        ship = self.ship
        magnet = "magnet" in ship.buffs and ship.alive
        for p in self.pickups:
            p.age += dt
            p.y += dc.fall_speed * dt
            if magnet and math.hypot(ship.x - p.x, ship.y - p.y) < dc.magnet_radius:
                dist = max(1.0, math.hypot(ship.x - p.x, ship.y - p.y))
                step = min(dist, dc.magnet_speed * dt)
                p.base_x += (ship.x - p.x) / dist * step
                p.y += (ship.y - p.y) / dist * step
                p.x = p.base_x
            else:
                p.x = p.base_x + dc.sway * math.sin(p.age * 2.2 + p.phase)
            if p.y - p.h / 2 > self.cfg.display.height:
                p.alive = False
                self.emit("pickup_missed", kind=p.kind)

    def _collect(self, pickup):
        cfg, ship = self.cfg, self.ship
        pc, kind = cfg.player, pickup.kind
        bonus = 0
        if pickup.category == "weapon":
            spec = cfg.weapons[kind]
            ship.weapon = kind
            ship.ammo = spec.ammo
            ship.weapon_time = spec.duration
            label = spec.label
        else:
            spec = cfg.pickups[kind]
            label = spec.label
            if kind == "repair":
                if ship.hull >= pc.max_hull:
                    bonus = cfg.drops.bonus_points
                ship.hull = min(pc.max_hull, ship.hull + spec.value)
            elif kind == "shield":
                ship.shield = min(pc.max_shield, ship.shield + int(spec.value))
            elif kind == "armor":
                ship.armor = min(pc.max_armor, ship.armor + spec.value)
            elif kind == "shock":
                self.shock_charge = 1.0
            elif kind == "life":
                if self.lives < pc.max_lives:
                    self.lives += 1
                else:
                    bonus = cfg.drops.bonus_points * 4
            else:
                ship.buffs[kind] = spec.duration
        self.score += bonus
        self.emit("pickup", kind=kind, category=pickup.category, label=label, x=pickup.x,
                  y=pickup.y, bonus=bonus)

    # ------------------------------------------------------------------
    # Projectiles and shockwaves
    # ------------------------------------------------------------------
    def _update_shots(self, dt):
        width, height = self.cfg.display.width, self.cfg.display.height
        targets = None
        for shot in self.shots:
            if shot.kind == "homing":
                if targets is None:
                    targets = self.targets()
                if targets:
                    tx, ty = min(((t[1], t[2]) for t in targets),
                                 key=lambda p: math.hypot(p[0] - shot.x, p[1] - shot.y))
                    shot.steer(tx, ty, dt)
            shot.update(dt)
            if shot.kind == "flak":
                shot.fuse -= dt
                if shot.fuse <= 0:
                    self._burst_flak(shot)
            if shot.life <= 0 or shot.off_screen(width, height):
                shot.alive = False

        ship = self.ship
        for shot in self.enemy_shots:
            if shot.kind == "missile" and ship.alive:
                shot.steer(ship.x, ship.y, dt)
            shot.update(dt)
            if shot.life <= 0 or shot.off_screen(width, height):
                shot.alive = False

    def _burst_flak(self, shell):
        if not shell.alive:
            return
        shell.alive = False
        n = max(1, shell.shrapnel)
        for i in range(n):
            angle = i * math.tau / n
            piece = Shot("shrapnel", shell.x, shell.y, math.cos(angle) * 520,
                                 math.sin(angle) * 520, (5, 5), shell.damage)
            piece.life = 0.32
            self.shots.append(piece)
        self.emit("flak_burst", x=shell.x, y=shell.y)

    def _update_shockwaves(self, dt):
        pc = self.cfg.player
        for wave in self.shockwaves:
            wave.update(dt)
            r = wave.radius
            for enemy in self.enemies:
                if enemy.alive and enemy.uid not in wave.hit and \
                        math.hypot(enemy.x - wave.x, enemy.y - wave.y) <= r:
                    wave.hit.add(enemy.uid)
                    self._damage_enemy(enemy, pc.shock_damage)
            for shot in self.enemy_shots:
                if shot.alive and math.hypot(shot.x - wave.x, shot.y - wave.y) <= r:
                    shot.alive = False
            if self.boss:
                for part in self.boss.active_parts():
                    if part.uid not in wave.hit and math.hypot(part.x - wave.x, part.y - wave.y) <= r:
                        wave.hit.add(part.uid)
                        self._damage_part(part, pc.shock_part_damage)
        self.shockwaves = [w for w in self.shockwaves if w.alive]

    # ------------------------------------------------------------------
    # Collisions
    # ------------------------------------------------------------------
    def _spend(self, shot):
        if shot.pierce > 0:
            shot.pierce -= 1
        else:
            shot.alive = False

    def _shot_hits(self, shot, target):
        self.damage_target(target, shot.damage)
        if shot.kind == "plasma":
            shot.alive = False
            self.emit("explosion", x=shot.x, y=shot.y, radius=shot.splash_radius)
            for other, ox, oy in self.targets():
                if other is not target and math.hypot(ox - shot.x, oy - shot.y) <= shot.splash_radius:
                    self.damage_target(other, shot.splash_damage)
        elif shot.kind == "flak":
            self._burst_flak(shot)
        else:
            self._spend(shot)

    def _collisions(self):
        missiles = [s for s in self.enemy_shots if s.kind == "missile"]
        enemy_rects = [(e, e.rect) for e in self.enemies if e.alive]
        boss = self.boss
        parts = []
        hull = None
        if boss:
            hull = self.boss_hull_rect()
            if self._boss_vulnerable():
                parts = [(p, p.rect) for p in boss.active_parts()]

        for shot in self.shots:
            if not shot.alive:
                continue
            rect = shot.rect
            for missile in missiles:
                if missile.alive and rect.colliderect(missile.rect):
                    missile.alive = False
                    self.score += 10
                    self.emit("missile_down", x=missile.x, y=missile.y)
                    self._spend(shot)
                    break
            if not shot.alive:
                continue
            for enemy, erect in enemy_rects:
                if enemy.alive and enemy.uid not in shot.hit_ids and rect.colliderect(erect):
                    shot.hit_ids.add(enemy.uid)
                    self._shot_hits(shot, enemy)
                    if not shot.alive:
                        break
            if not shot.alive or not boss or self.boss is not boss:
                continue
            for part, prect in parts:
                if part.alive and part.uid not in shot.hit_ids and rect.colliderect(prect):
                    shot.hit_ids.add(part.uid)
                    self._shot_hits(shot, part)
                    if not shot.alive or self.boss is not boss:
                        break
            # The hull is armored: shots that aren't lined up under an
            # active weapon bounce off it.
            if shot.alive and self.boss is boss and hull and shot.kind != "rail" \
                    and shot.vy < 0 and rect.colliderect(hull) \
                    and not any(pr.left <= shot.x <= pr.right for _, pr in parts):
                shot.alive = False
                self.emit("deflect", x=shot.x, y=rect.top)

        ship = self.ship
        if not ship.alive:
            return
        hitbox = ship.hitbox
        for shot in self.enemy_shots:
            if shot.alive and hitbox.colliderect(shot.rect):
                if self._damage_player(shot.damage, shot.kind) is not None:
                    shot.alive = False
                if not ship.alive:
                    return

        er = self.cfg.enemy
        height = self.cfg.display.height
        beams = [(e.beam_x, e.y + e.h / 2, e) for e in self.enemies
                 if e.alive and e.state == "beam" and not e.beam_hit]
        if self.boss:
            beams += [(p.x, p.y + p.h / 2, p) for p in self.boss.parts
                      if p.alive and p.beam_state == "beam" and not p.beam_hit]
        for bx, by, source in beams:
            width = er.beam_width * (1.6 if isinstance(source, Hardpoint) else 1.0)
            if hitbox.right >= bx - width / 2 and hitbox.left <= bx + width / 2 and hitbox.bottom >= by:
                damage = self.cfg.boss.laser_damage if isinstance(source, Hardpoint) else source.spec.bullet_damage
                source.beam_hit = True          # one beam can only ever hit once
                self._damage_player(damage, "beam")
                if not ship.alive:
                    return

        for enemy, erect in enemy_rects:
            if not enemy.alive or not hitbox.colliderect(erect):
                continue
            if enemy.kind == "mine":
                self.explode_mine(enemy, harmless=False)
            elif enemy.kind == "cargo":
                continue
            elif self._damage_player(enemy.spec.ram_damage, "ram") is not None:
                self._damage_enemy(enemy, enemy.hp if enemy.spec.threat <= 2 or enemy.spec.hazard else 4)
            if not ship.alive:
                return

        rect = ship.rect
        for pickup in self.pickups:
            if pickup.alive and rect.colliderect(pickup.rect):
                pickup.alive = False
                self._collect(pickup)

    def _cleanup(self):
        self.shots = [s for s in self.shots if s.alive]
        self.enemy_shots = [s for s in self.enemy_shots if s.alive]
        self.enemies = [e for e in self.enemies if e.alive]
        self.pickups = [p for p in self.pickups if p.alive]

    # ------------------------------------------------------------------
    # Events and snapshots
    # ------------------------------------------------------------------
    def emit(self, event_type, /, **data):
        data["type"] = event_type
        self.events.append(data)

    def drain_events(self):
        events, self.events = self.events, []
        return events

    def snapshot(self):
        """Small summary for the HUD and the browser host."""
        ship, boss = self.ship, self.boss
        weapon = None
        if ship.weapon:
            spec = self.cfg.weapons[ship.weapon]
            weapon = {"name": ship.weapon, "ammo": ship.ammo if spec.ammo else None,
                      "time": round(ship.weapon_time, 1) if spec.duration else None}
        boss_info = None
        if boss:
            left, total = boss.stage_hp()
            boss_info = {"name": boss.label, "stage": boss.stage, "stages": boss.stages,
                         "stage_hp": round(left / total, 3) if total else 0}
        return {
            "state": self.state,
            "paused": self.paused,
            "score": self.score,
            "high_score": max(self.high_score, self.score),
            "level": self.level,
            "wave": self.wave,
            "lives": self.lives,
            "hull": round(max(0.0, ship.hull)),
            "armor": round(ship.armor),
            "shield": ship.shield,
            "weapon": weapon,
            "buffs": {k: round(v, 1) for k, v in sorted(ship.buffs.items())},
            "shock": round(self.shock_charge, 2),
            "multiplier": self.multiplier,
            "boss": boss_info,
            "run_id": self.run_id,
            "seed": self.seed,
        }
