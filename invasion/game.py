"""The game simulation: state machine, rules and collisions. No drawing.

The simulation advances in fixed steps (1 / sim_hz seconds) and takes all
of its randomness from one seeded random.Random, so the same seed plus the
same inputs per step always produce the same run.

Power-up rules (all numbers in config.PowerUpConfig):
  * shield, spread and pierce are timed. Different kinds stack (spread
    bullets also pierce while both are active).
  * picking up a kind that is already active refreshes it to its full
    duration; durations never add up beyond that.
  * a timed power-up ends when its timer reaches zero.
  * losing a life removes every timed power-up. Special charges are kept.
  * extra life adds one life up to max_lives. At the cap it is not offered
    as a drop; if one is collected anyway it gives life_cap_bonus points.
  * a new run starts with no power-ups and clears any falling pickups.

Damage rules:
  * the ship can only be hit while alive and not invulnerable; the hit
    removes it immediately, so one collision can never cost two lives.
  * start_lives = 3 means the third hit ends the run.
  * after a hit the ship respawns after respawn_delay and blinks for
    invulnerable_time, during which nothing can damage it.
  * the shield blocks enemy bullets and rams while active.
  * aliens reaching the ship's row (an invasion) always cost a life,
    shield or not, unless the ship is already down; the formation is then
    pushed back to the top.
"""
import math
import random
from dataclasses import dataclass, replace

from .config import Config
from .entities import Boss, Bullet, Enemy, PowerUp, Ship
from .waves import plan_wave

GAME_VERSION = "2.0.0"

TITLE = "title"
PLAYING = "playing"
GAME_OVER = "game_over"

TIMED_POWERUPS = ("shield", "spread", "pierce")


@dataclass
class InputState:
    left: bool = False
    right: bool = False
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
        """Start a new run. Uses the given seed, the fixed seed, or a fresh one."""
        if seed is None:
            seed = self.fixed_seed if self.fixed_seed is not None else random.randrange(1, 2**31)
        self.run_count += 1
        self._reset_run(seed)
        self.state = PLAYING
        self.emit("run_started", run_id=self.run_id, seed=self.seed, version=GAME_VERSION)
        self._start_wave(1)

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
        self.score = 0
        self.kills = 0
        self.lives = cfg.player.start_lives
        self.specials = cfg.player.special_start
        self.special_timer = 0.0
        self.powerups = {}
        self.ship = Ship(cfg)
        self.bullets = []
        self.enemy_bullets = []
        self.enemies = []
        self.boss = None
        self.pickups = []
        self.wave = 0
        self.plan = None
        self.origin = [cfg.display.width / 2, cfg.display.hud_height + cfg.enemy.top_margin]
        self.fleet_dir = 1
        self.fleet_size = 0
        self.banner_timer = 0.0
        self.clear_timer = 0.0
        self.fire_timer = 0.0
        self.dive_timer = 0.0
        self.drop_gap_timer = 0.0
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
                      wave=self.wave, kills=self.kills, ticks=self.ticks,
                      duration=round(self.ticks * self.dt, 2), version=GAME_VERSION)

    # ------------------------------------------------------------------
    # Pause
    # ------------------------------------------------------------------
    def set_paused(self, paused):
        if self.state != PLAYING or paused == self.paused:
            return False
        self.paused = paused
        self.emit("paused" if paused else "resumed")
        return True

    def toggle_pause(self):
        return self.set_paused(not self.paused)

    # ------------------------------------------------------------------
    # Time
    # ------------------------------------------------------------------
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
        self._update_timers(dt)
        self._update_ship(dt, inp)
        self._update_bullets(dt)
        if self.clear_timer > 0:
            self.clear_timer -= dt
            if self.clear_timer <= 0 and self.lives > 0:
                self._start_wave(self.wave + 1)
        else:
            self._update_enemies(dt)
            self._update_boss(dt)
            self._update_enemy_fire(dt)
        self._update_pickups(dt)
        self._collisions()
        self._check_wave_clear()
        if self.game_over_timer > 0:
            self.game_over_timer -= dt
            if self.game_over_timer <= 0:
                self._end_run()

    def _update_timers(self, dt):
        for kind in list(self.powerups):
            self.powerups[kind] -= dt
            if self.powerups[kind] <= 0:
                del self.powerups[kind]
                self.emit("powerup_expired", kind=kind)
        self.special_timer = max(0.0, self.special_timer - dt)
        self.drop_gap_timer = max(0.0, self.drop_gap_timer - dt)
        self.banner_timer = max(0.0, self.banner_timer - dt)

    # ------------------------------------------------------------------
    # Waves
    # ------------------------------------------------------------------
    def _start_wave(self, number):
        cfg = self.cfg
        self.wave = number
        self.plan = plan = plan_wave(number, cfg, self.rng)
        self.origin = [cfg.display.width / 2, cfg.display.hud_height + cfg.enemy.top_margin]
        self.fleet_dir = 1
        self.enemies = []
        for kind, dx, dy in plan.enemies:
            enemy = Enemy(self.next_uid, kind, cfg.enemy_type(kind), (dx, dy))
            self.next_uid += 1
            enemy.x, enemy.y = enemy.slot_position(self.origin)
            self.enemies.append(enemy)
        self.fleet_size = len(self.enemies)
        self.boss = Boss(cfg, plan.boss_index) if plan.is_boss else None
        self.bullets.clear()
        self.enemy_bullets.clear()
        self.banner_timer = cfg.flow.boss_banner if plan.is_boss else cfg.flow.wave_banner
        self.fire_timer = plan.fire_interval + cfg.enemy_fire.wave_start_grace
        self.dive_timer = plan.dive_interval
        self.emit("wave_started", wave=number, boss=plan.is_boss,
                  formation=plan.formation, hint=plan.hint)
        if plan.is_boss:
            self.emit("boss_spawned", index=plan.boss_index, hp=self.boss.max_hp)

    def _check_wave_clear(self):
        if self.clear_timer > 0 or self.wave == 0 or self.lives <= 0:
            return
        if self.enemies or (self.boss and self.boss.alive):
            return
        bonus = self.cfg.score.wave_clear_bonus * self.wave
        self.score += bonus
        self.enemy_bullets.clear()
        self.clear_timer = self.cfg.flow.wave_clear_delay
        self.emit("wave_cleared", wave=self.wave, bonus=bonus)

    # ------------------------------------------------------------------
    # Player
    # ------------------------------------------------------------------
    def _update_ship(self, dt, inp):
        ship = self.ship
        if not ship.alive:
            if self.lives > 0:
                ship.respawn_timer -= dt
                if ship.respawn_timer <= 0:
                    ship.alive = True
                    ship.center()
                    ship.invulnerable_timer = self.cfg.player.invulnerable_time
                    ship.fire_timer = 0.0
                    self.emit("respawned")
            return
        ship.invulnerable_timer = max(0.0, ship.invulnerable_timer - dt)
        ship.fire_timer = max(0.0, ship.fire_timer - dt)
        ship.move(int(inp.right) - int(inp.left), dt)
        if inp.fire and ship.fire_timer <= 0:
            self._fire_player()
        if inp.special:
            self._use_special()

    def _fire_player(self):
        pc, pu = self.cfg.player, self.cfg.powerups
        spread = "spread" in self.powerups
        pierce = pu.pierce_hits if "pierce" in self.powerups else 0
        angles = (-pu.spread_angle, 0.0, pu.spread_angle) if spread else (0.0,)
        limit = pu.spread_max_bullets if spread else pc.max_bullets
        if len(self.bullets) + len(angles) > limit:
            return
        top = self.ship.rect.top
        for angle in angles:
            rad = math.radians(angle)
            self.bullets.append(Bullet(self.ship.x, top, math.sin(rad) * pc.bullet_speed,
                                       -math.cos(rad) * pc.bullet_speed, pc.bullet_size, pierce))
        self.ship.fire_timer = pc.fire_cooldown

    def _use_special(self):
        pc = self.cfg.player
        if self.specials <= 0 or self.special_timer > 0 or not self.ship.alive:
            return
        self.specials -= 1
        self.special_timer = pc.special_cooldown
        self.enemy_bullets.clear()
        self.emit("special", x=self.ship.x, y=self.ship.y, radius=pc.special_radius,
                  charges=self.specials)
        ship = self.ship
        for enemy in list(self.enemies):
            enemy.charge_timer = 0.0
            if math.hypot(enemy.x - ship.x, enemy.y - ship.y) <= pc.special_radius:
                self._damage_enemy(enemy, pc.special_damage)
        boss = self.boss
        if boss and boss.alive and not boss.entering:
            self._damage_boss(max(1, round(boss.max_hp * pc.special_boss_fraction)))
        self.enemies = [e for e in self.enemies if e.alive]

    def _hit_player(self, cause):
        """Damage from a bullet or a ram. Returns True if a life was lost."""
        ship = self.ship
        if not ship.alive:
            return False
        if "shield" in self.powerups:
            self.emit("shield_block", x=ship.x, y=ship.y)
            return False
        if ship.invulnerable_timer > 0:
            return False
        self._lose_life(cause)
        return True

    def _lose_life(self, cause):
        cfg = self.cfg
        ship = self.ship
        ship.alive = False
        self.lives -= 1
        self.powerups.clear()
        self.enemy_bullets.clear()
        for enemy in self.enemies:
            enemy.charge_timer = 0.0
            if enemy.mode in ("telegraph", "diving"):
                enemy.mode = "returning"
                enemy.y = -enemy.h
        if self.boss:
            self.boss.charge_timer = 0.0
            self.boss.burst_left = 0
            self.boss.second_fan_timer = 0.0
            self.boss.pattern_timer = cfg.boss.pattern_cooldown
        self.emit("player_hit", x=ship.x, y=ship.y, lives=self.lives, cause=cause)
        if self.lives <= 0:
            self.game_over_timer = cfg.player.game_over_delay
        else:
            ship.respawn_timer = cfg.player.respawn_delay

    # ------------------------------------------------------------------
    # Enemies
    # ------------------------------------------------------------------
    def _update_enemies(self, dt):
        cfg, plan = self.cfg, self.plan
        ec = cfg.enemy
        for enemy in self.enemies:
            enemy.flash_timer = max(0.0, enemy.flash_timer - dt)
        if not self.enemies or self.banner_timer > 0:
            return

        # March the formation, bouncing off the side margins.
        thinned = 1 - len(self.enemies) / max(1, self.fleet_size)
        speed = plan.march_speed + ec.march_thin_bonus * thinned
        self.origin[0] += self.fleet_dir * speed * dt
        left = min(e.slot[0] - e.w / 2 for e in self.enemies) + self.origin[0]
        right = max(e.slot[0] + e.w / 2 for e in self.enemies) + self.origin[0]
        width = cfg.display.width
        if self.fleet_dir > 0 and right >= width - ec.side_margin:
            self.origin[0] -= right - (width - ec.side_margin)
            self.fleet_dir = -1
            self.origin[1] += ec.drop_distance
        elif self.fleet_dir < 0 and left <= ec.side_margin:
            self.origin[0] += ec.side_margin - left
            self.fleet_dir = 1
            self.origin[1] += ec.drop_distance

        for enemy in self.enemies:
            target = enemy.slot_position(self.origin)
            if enemy.mode == "formation":
                enemy.x, enemy.y = target
            elif enemy.mode == "telegraph":
                enemy.x, enemy.y = target
                enemy.mode_timer -= dt
                if enemy.mode_timer <= 0:
                    enemy.start_dive(self.ship.x)
            elif enemy.mode == "diving":
                enemy.update_dive(dt, plan.dive_speed, ec.dive_sway, ec.dive_sway_hz)
                if enemy.rect.top > cfg.display.height:
                    enemy.mode = "returning"
                    enemy.x, enemy.y = target[0], -enemy.h
            elif enemy.mode == "returning":
                enemy.update_return(dt, target, ec.return_speed)

            if enemy.charge_timer > 0:
                enemy.charge_timer -= dt
                if enemy.charge_timer <= 0:
                    self._release_enemy_shot(enemy)

        # Invasion: a marching alien reached the ship's row.
        line = self.ship.y - self.ship.h / 2
        if any(e.mode == "formation" and e.rect.bottom >= line for e in self.enemies):
            self._invasion()
            return

        # Agile dives, one telegraphed launch at a time.
        if plan.max_divers and self.ship.alive:
            self.dive_timer -= dt
            if self.dive_timer <= 0:
                self.dive_timer = plan.dive_interval
                active = sum(1 for e in self.enemies if e.mode in ("telegraph", "diving"))
                ready = [e for e in self.enemies
                         if e.kind == "agile" and e.mode == "formation" and e.charge_timer <= 0]
                if active < plan.max_divers and ready:
                    diver = self.rng.choice(ready)
                    diver.mode = "telegraph"
                    diver.mode_timer = ec.dive_telegraph
                    self.emit("dive_warning", x=diver.x, y=diver.y)

    def _invasion(self):
        if self.ship.alive:
            self._lose_life("invasion")
        self.origin[1] = self.cfg.display.hud_height + self.cfg.enemy.top_margin
        for enemy in self.enemies:
            enemy.charge_timer = 0.0
            enemy.mode = "formation"
            enemy.x, enemy.y = enemy.slot_position(self.origin)
        self.emit("invasion")

    def _front_row(self):
        front = {}
        for enemy in self.enemies:
            if enemy.mode != "formation":
                continue
            column = enemy.slot[0]
            if column not in front or enemy.slot[1] > front[column].slot[1]:
                front[column] = enemy
        return list(front.values())

    def _update_enemy_fire(self, dt):
        if self.banner_timer > 0 or not self.ship.alive or not self.enemies:
            return
        self.fire_timer -= dt
        if self.fire_timer > 0:
            return
        plan, fc = self.plan, self.cfg.enemy_fire
        self.fire_timer = plan.fire_interval
        charging = sum(1 for e in self.enemies if e.charge_timer > 0)
        if len(self.enemy_bullets) + charging >= plan.max_enemy_bullets:
            return
        shooters = [e for e in self._front_row()
                    if e.charge_timer <= 0 and self.ship.y - e.y >= fc.safe_distance]
        if not shooters:
            return
        weights = [self.cfg.enemy_type(e.kind).fire_weight for e in shooters]
        shooter = self.rng.choices(shooters, weights=weights)[0]
        shooter.charge_timer = fc.telegraph

    def _release_enemy_shot(self, enemy):
        if not self.ship.alive or enemy.mode != "formation":
            return
        fc = self.cfg.enemy_fire
        angle = 0.0
        if self.plan.aimed_shots and enemy.kind == "armored":
            angle = math.degrees(math.atan2(self.ship.x - enemy.x, self.ship.y - enemy.y))
            angle = max(-fc.aimed_max_angle, min(fc.aimed_max_angle, angle))
        self._spawn_enemy_bullet(enemy.x, enemy.rect.bottom, angle, self.plan.enemy_bullet_speed)

    def _spawn_enemy_bullet(self, x, y, angle, speed):
        rad = math.radians(angle)
        self.enemy_bullets.append(Bullet(x, y, math.sin(rad) * speed, math.cos(rad) * speed,
                                         self.cfg.enemy_fire.bullet_size))

    def _damage_enemy(self, enemy, damage):
        if not enemy.alive:
            return
        if enemy.hit(damage, self.cfg.enemy.hit_flash):
            self.score += enemy.points
            self.kills += 1
            self.emit("enemy_killed", kind=enemy.kind, x=enemy.x, y=enemy.y, points=enemy.points)
            self._maybe_drop(enemy.x, enemy.y, self.cfg.enemy_type(enemy.kind).drop_chance)
        else:
            self.emit("enemy_hit", kind=enemy.kind, x=enemy.x, y=enemy.y)

    # ------------------------------------------------------------------
    # Boss
    # ------------------------------------------------------------------
    def _update_boss(self, dt):
        boss = self.boss
        if not boss or not boss.alive:
            return
        bc = self.cfg.boss
        boss.flash_timer = max(0.0, boss.flash_timer - dt)
        phase2 = boss.in_phase2(bc.phase2_at)
        boss.move(dt, bc.speed_phase2 if phase2 else bc.speed,
                  self.cfg.display.width, self.cfg.enemy.side_margin)
        if boss.entering or self.banner_timer > 0 or not self.ship.alive:
            return

        if boss.burst_left > 0:
            boss.burst_timer -= dt
            if boss.burst_timer <= 0:
                self._boss_aimed_shot(boss)
                boss.burst_left -= 1
                boss.burst_timer = bc.burst_gap
        elif boss.second_fan_timer > 0:
            boss.second_fan_timer -= dt
            if boss.second_fan_timer <= 0:
                self._boss_fan(boss, bc.fan_step / 2)
        elif boss.charge_timer > 0:
            boss.charge_timer -= dt
            if boss.charge_timer <= 0:
                self._boss_attack(boss, boss.pending_pattern)
        else:
            boss.pattern_timer -= dt
            if boss.pattern_timer <= 0:
                patterns = ("burst", "double_fan") if phase2 else ("burst", "fan")
                boss.pending_pattern = patterns[boss.pattern_index % len(patterns)]
                boss.pattern_index += 1
                boss.charge_timer = bc.telegraph
                boss.pattern_timer = bc.pattern_cooldown_phase2 if phase2 else bc.pattern_cooldown

    def _boss_attack(self, boss, pattern):
        if pattern == "burst":
            boss.burst_left = self.cfg.boss.burst_count
            boss.burst_timer = 0.0
        else:
            self._boss_fan(boss, 0.0)
            if pattern == "double_fan":
                boss.second_fan_timer = 0.45

    def _boss_aimed_shot(self, boss):
        angle = math.degrees(math.atan2(self.ship.x - boss.x, self.ship.y - boss.y))
        angle = max(-35.0, min(35.0, angle))
        self._spawn_enemy_bullet(boss.x, boss.rect.bottom, angle, self.cfg.boss.bullet_speed)

    def _boss_fan(self, boss, offset):
        bc = self.cfg.boss
        for i in range(bc.fan_count):
            angle = (i - (bc.fan_count - 1) / 2) * bc.fan_step + offset
            self._spawn_enemy_bullet(boss.x, boss.rect.bottom, angle, bc.bullet_speed)

    def _damage_boss(self, damage):
        boss = self.boss
        was_phase2 = boss.in_phase2(self.cfg.boss.phase2_at)
        if boss.hit(damage, self.cfg.enemy.hit_flash):
            self.score += boss.points
            self.kills += 1
            pc = self.cfg.player
            self.specials = min(pc.special_max, self.specials + pc.special_per_boss)
            self.enemy_bullets.clear()
            self.emit("boss_defeated", index=boss.index, x=boss.x, y=boss.y, points=boss.points)
            self._maybe_drop(boss.x, boss.y, 1.0, guaranteed=self.cfg.powerups.boss_drop_guaranteed)
        else:
            self.emit("boss_hit", x=boss.x, y=boss.y, hp=boss.hp, max_hp=boss.max_hp)
            if not was_phase2 and boss.in_phase2(self.cfg.boss.phase2_at):
                self.emit("boss_enraged")

    # ------------------------------------------------------------------
    # Power-ups
    # ------------------------------------------------------------------
    def _maybe_drop(self, x, y, chance, guaranteed=False):
        pu = self.cfg.powerups
        if not guaranteed:
            if self.drop_gap_timer > 0 or len(self.pickups) >= pu.max_on_screen:
                return
            if self.rng.random() >= chance:
                return
        kinds = [k for k in pu.weights if not (k == "life" and self.lives >= self.cfg.player.max_lives)]
        kind = self.rng.choices(kinds, weights=[pu.weights[k] for k in kinds])[0]
        self.pickups.append(PowerUp(kind, x, y, pu.size))
        self.drop_gap_timer = pu.min_gap
        self.emit("powerup_dropped", kind=kind, x=x, y=y)

    def _update_pickups(self, dt):
        height = self.cfg.display.height
        for pickup in self.pickups:
            pickup.update(dt, self.cfg.powerups.fall_speed)
        self.pickups = [p for p in self.pickups if p.rect.top <= height]

    def _collect(self, pickup):
        pu = self.cfg.powerups
        bonus = 0
        if pickup.kind == "life":
            if self.lives < self.cfg.player.max_lives:
                self.lives += 1
            else:
                bonus = pu.life_cap_bonus
                self.score += bonus
        else:
            self.powerups[pickup.kind] = pu.durations[pickup.kind]
        self.emit("pickup", kind=pickup.kind, x=pickup.x, y=pickup.y, bonus=bonus)

    # ------------------------------------------------------------------
    # Movement and collisions
    # ------------------------------------------------------------------
    def _update_bullets(self, dt):
        width, height = self.cfg.display.width, self.cfg.display.height
        for bullet in self.bullets:
            bullet.update(dt)
        for bullet in self.enemy_bullets:
            bullet.update(dt)
        self.bullets = [b for b in self.bullets if not b.off_screen(width, height)]
        self.enemy_bullets = [b for b in self.enemy_bullets if not b.off_screen(width, height)]

    def _spend_bullet(self, bullet):
        if bullet.pierce_left > 0:
            bullet.pierce_left -= 1
        else:
            bullet.alive = False

    def _collisions(self):
        # Player bullets shoot enemy bullets out of the air.
        for bullet in self.bullets:
            for shot in self.enemy_bullets:
                if bullet.alive and shot.alive and bullet.rect.colliderect(shot.rect):
                    shot.alive = False
                    self.score += self.cfg.score.bullet_cancel
                    self._spend_bullet(bullet)

        # Player bullets hit aliens and the boss, each target once per bullet.
        boss = self.boss
        for bullet in self.bullets:
            if not bullet.alive:
                continue
            rect = bullet.rect
            for enemy in self.enemies:
                if enemy.alive and enemy.uid not in bullet.hit_ids and rect.colliderect(enemy.rect):
                    bullet.hit_ids.add(enemy.uid)
                    self._damage_enemy(enemy, 1)
                    self._spend_bullet(bullet)
                    if not bullet.alive:
                        break
            if (bullet.alive and boss and boss.alive and boss.rect.bottom > 0
                    and boss.uid not in bullet.hit_ids and rect.colliderect(boss.rect)):
                bullet.hit_ids.add(boss.uid)
                self._damage_boss(1)
                self._spend_bullet(bullet)

        self.bullets = [b for b in self.bullets if b.alive]
        self.enemy_bullets = [b for b in self.enemy_bullets if b.alive]
        self.enemies = [e for e in self.enemies if e.alive]

        ship = self.ship
        if not ship.alive:
            return
        hitbox = ship.hitbox
        for shot in self.enemy_bullets:
            if hitbox.colliderect(shot.rect):
                shot.alive = False
                if self._hit_player("bullet"):
                    break
        self.enemy_bullets = [b for b in self.enemy_bullets if b.alive]

        if ship.alive:
            for enemy in self.enemies:
                if enemy.alive and hitbox.colliderect(enemy.rect):
                    if "shield" in self.powerups:
                        self._damage_enemy(enemy, enemy.hp)
                        self.emit("shield_block", x=ship.x, y=ship.y)
                    elif ship.invulnerable_timer <= 0:
                        self._damage_enemy(enemy, enemy.hp)
                        self._hit_player("ram")
                        break
            self.enemies = [e for e in self.enemies if e.alive]

        if ship.alive:
            rect = ship.rect
            for pickup in self.pickups:
                if pickup.alive and rect.colliderect(pickup.rect):
                    pickup.alive = False
                    self._collect(pickup)
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
        boss = self.boss
        return {
            "state": self.state,
            "paused": self.paused,
            "score": self.score,
            "high_score": max(self.high_score, self.score),
            "wave": self.wave,
            "lives": self.lives,
            "specials": self.specials,
            "shield": round(self.powerups.get("shield", 0.0), 1),
            "powerups": {k: round(v, 1) for k, v in sorted(self.powerups.items())},
            "boss_hp": (boss.hp / boss.max_hp) if boss and boss.alive else None,
            "run_id": self.run_id,
            "seed": self.seed,
        }
