"""Game objects. They hold state and simple motion; the rules that tie
them together live in game.py, and enemy behavior lives in ai.py.

Positions are floats (x, y is the center). A pygame.Rect is built on demand
for collisions. Nothing here draws, so the simulation runs headless.
"""
import math

import pygame


class Body:
    def __init__(self, x, y, size):
        self.x = float(x)
        self.y = float(y)
        self.w, self.h = size
        self.alive = True

    @property
    def rect(self):
        return pygame.Rect(round(self.x - self.w / 2), round(self.y - self.h / 2), self.w, self.h)


class Ship(Body):
    """The player's ship and everything it carries."""

    def __init__(self, cfg):
        self.cfg = cfg
        pc = cfg.player
        super().__init__(cfg.display.width / 2, self.home_y(cfg), pc.size)
        self.hull = pc.max_hull
        self.armor = 0.0
        self.shield = 0                 # hits the shield can still block
        self.fire_timer = 0.0
        self.wing_timer = 0.0
        self.respawn_timer = 0.0
        self.invulnerable_timer = 0.0
        self.hurt_timer = 0.0
        self.weapon = None              # name of a collected weapon, None = blaster
        self.ammo = 0                   # shots left (ammo weapons)
        self.weapon_time = 0.0          # seconds left (timed weapons)
        self.buffs = {}                 # wingmen / overdrive / magnet -> seconds left
        self.laser_on = False
        self.laser_top = 0.0            # where the beam currently stops
        self.tilt = 0.0                 # -1..1, for the renderer

    @staticmethod
    def home_y(cfg):
        return cfg.display.height - cfg.player.bottom_margin - cfg.player.size[1] / 2

    @property
    def hitbox(self):
        r = self.rect
        k = 1 - self.cfg.player.hitbox_scale
        return r.inflate(-round(r.w * k), -round(r.h * k))

    @property
    def vulnerable(self):
        return self.alive and self.invulnerable_timer <= 0 and self.hurt_timer <= 0

    def move(self, dx, dy, dt):
        pc = self.cfg.player
        width, height = self.cfg.display.width, self.cfg.display.height
        if dx and dy:
            dx, dy = dx * 0.7071, dy * 0.7071
        self.x += dx * pc.speed * dt
        self.y += dy * pc.speed * dt
        self.x = max(self.w / 2, min(width - self.w / 2, self.x))
        self.y = max(height * pc.top_zone, min(self.home_y(self.cfg), self.y))
        self.tilt += (dx - self.tilt) * min(1.0, dt * 12)

    def reset_loadout(self):
        self.weapon = None
        self.ammo = 0
        self.weapon_time = 0.0
        self.buffs.clear()
        self.shield = 0
        self.armor = 0.0
        self.laser_on = False


class Shot(Body):
    """A player projectile."""

    def __init__(self, kind, x, y, vx, vy, size, damage, pierce=0):
        super().__init__(x, y, size)
        self.kind = kind                # bullet, rail, homing, plasma, flak, shrapnel
        self.vx = vx
        self.vy = vy
        self.damage = damage
        self.pierce = pierce
        self.hit_ids = set()
        self.life = 2.5
        self.splash_radius = 0.0
        self.splash_damage = 0.0
        self.turn_rate = 0.0
        self.fuse = 0.0
        self.shrapnel = 0

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    def steer(self, tx, ty, dt):
        """Turn toward a target at a limited rate (homing missiles)."""
        speed = math.hypot(self.vx, self.vy)
        current = math.atan2(self.vy, self.vx)
        wanted = math.atan2(ty - self.y, tx - self.x)
        diff = (wanted - current + math.pi) % math.tau - math.pi
        turn = max(-self.turn_rate * dt, min(self.turn_rate * dt, diff))
        angle = current + turn
        self.vx, self.vy = math.cos(angle) * speed, math.sin(angle) * speed

    def off_screen(self, width, height, margin=40):
        return (self.y < -margin or self.y > height + margin
                or self.x < -margin or self.x > width + margin)


class EnemyShot(Shot):
    """An enemy projectile: bullet, missile (homing, can be shot down) or orb."""

    def __init__(self, kind, x, y, vx, vy, size, damage):
        super().__init__(kind, x, y, vx, vy, size, damage)
        self.hp = 1.0 if kind == "missile" else 0.0
        self.life = 6.0


class Enemy(Body):
    def __init__(self, uid, kind, spec, hp):
        super().__init__(0, 0, spec.size)
        self.uid = uid
        self.kind = kind
        self.spec = spec
        self.hp = hp
        self.max_hp = hp
        self.points = spec.points
        self.state = "enter"
        self.t = 0.0                    # time in the current state
        self.age = 0.0
        self.phase = 0.0                # per-enemy offset for bobbing
        self.anchor = None
        self.start = None
        self.ctrl = None
        self.end = None
        self.duration = 1.0
        self.amp = 0.0
        self.freq = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.fire_timer = 0.0
        self.charge_timer = 0.0         # glowing before a shot
        self.action_timer = 0.0         # next dive / reposition
        self.beam_x = 0.0
        self.beam_hit = False
        self.flash = 0.0
        self.spin = 0.0                 # asteroids
        self.armed = -1.0               # mines: < 0 idle, >= 0 counting down
        self.escaped = False
        self.minion = False             # launched by a boss hangar

    @property
    def beaming(self):
        return self.state == "beam"

    @property
    def charging_beam(self):
        return self.state == "beam_charge"


def bezier(p0, p1, p2, p3, t):
    u = 1 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
            a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1])


def path_length(p0, p1, p2, p3, steps=12):
    total, prev = 0.0, p0
    for i in range(1, steps + 1):
        cur = bezier(p0, p1, p2, p3, i / steps)
        total += math.hypot(cur[0] - prev[0], cur[1] - prev[1])
        prev = cur
    return total


class Hardpoint:
    """A weapon (or the core) mounted on a boss. Only hardpoints of the
    boss's current stage can be damaged; everything else is armored."""

    def __init__(self, uid, spec, hp, size):
        self.uid = uid
        self.kind = spec.kind
        self.spec = spec
        self.offset = spec.offset
        self.stage = spec.stage
        self.hp = hp
        self.max_hp = hp
        self.w, self.h = size
        self.alive = True
        self.fire_timer = spec.interval * 0.6
        self.charge_timer = 0.0
        self.burst_left = 0
        self.burst_timer = 0.0
        self.beam_state = None          # None, "charge", "beam"
        self.beam_timer = 0.0
        self.beam_hit = False
        self.flash = 0.0
        self.ring_turn = 0              # alternates core patterns
        self.x = 0.0
        self.y = 0.0

    @property
    def rect(self):
        return pygame.Rect(round(self.x - self.w / 2), round(self.y - self.h / 2), self.w, self.h)


PART_SIZES = {"cannon": (40, 36), "spread": (44, 36), "missile": (40, 36), "laser": (36, 44),
              "hangar": (70, 34), "core": (64, 56)}


class Boss(Body):
    def __init__(self, cfg, index, cycle, uid_start):
        spec = cfg.bosses[index]
        super().__init__(cfg.display.width / 2, -spec.size[1] / 2, spec.size)
        self.spec = spec
        self.index = index
        self.cycle = cycle
        self.label = spec.label
        self.points = int(spec.points * (1 + cycle))
        self.target_y = cfg.display.hud_height + spec.size[1] / 2
        self.direction = 1
        self.stage = 1
        self.stage_timer = 0.0          # breather between stages (no damage, no fire)
        scale = 1 + cfg.boss.endless_hp_per_cycle * cycle
        self.parts = [Hardpoint(uid_start + i, hp_spec, hp_spec.hp * scale, PART_SIZES[hp_spec.kind])
                      for i, hp_spec in enumerate(spec.hardpoints)]
        self.stages = max(p.stage for p in self.parts)
        self.place_parts()

    @property
    def entering(self):
        return self.y < self.target_y

    def place_parts(self):
        for part in self.parts:
            part.x = self.x + part.offset[0]
            part.y = self.y + part.offset[1]

    def active_parts(self):
        return [p for p in self.parts if p.alive and p.stage == self.stage]

    def stage_hp(self):
        parts = [p for p in self.parts if p.stage == self.stage]
        return sum(max(0.0, p.hp) for p in parts), sum(p.max_hp for p in parts)

    def move(self, dt, enter_speed, width):
        if self.entering:
            self.y = min(self.target_y, self.y + enter_speed * dt)
        else:
            self.x += self.direction * self.spec.speed * dt
            # Drift sideways, but keep every weapon on screen and reachable.
            extent = max(abs(p.offset[0]) + p.w / 2 for p in self.parts)
            reach = max(20.0, width / 2 - 30 - extent)
            center = width / 2
            if self.x > center + reach:
                self.x, self.direction = center + reach, -1
            elif self.x < center - reach:
                self.x, self.direction = center - reach, 1
        self.place_parts()


class Pickup(Body):
    def __init__(self, kind, category, x, y, phase):
        super().__init__(x, y, (30, 30))
        self.kind = kind
        self.category = category        # "weapon" or "utility"
        self.age = 0.0
        self.phase = phase
        self.base_x = float(x)


class Shockwave:
    def __init__(self, x, y, max_radius, speed):
        self.x, self.y = x, y
        self.radius = 0.0
        self.max_radius = max_radius
        self.speed = speed
        self.hit = set()
        self.alive = True

    def update(self, dt):
        self.radius += self.speed * dt
        if self.radius >= self.max_radius:
            self.alive = False
