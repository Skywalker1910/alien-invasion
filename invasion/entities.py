"""Game objects and their own movement rules.

Entities keep exact float positions (x, y is the center) and build a
pygame.Rect on demand for collisions. They never draw themselves and never
touch the display, so the whole simulation runs headless in tests.
"""
import math

import pygame


class Entity:
    def __init__(self, x, y, size):
        self.x = float(x)
        self.y = float(y)
        self.w, self.h = size
        self.alive = True

    @property
    def rect(self):
        r = pygame.Rect(0, 0, self.w, self.h)
        r.center = (round(self.x), round(self.y))
        return r


class Ship(Entity):
    """The player's ship. Lives and power-ups are tracked by the game."""

    def __init__(self, cfg):
        self.cfg = cfg
        width, height = cfg.display.width, cfg.display.height
        size = cfg.player.size
        super().__init__(width / 2, height - cfg.player.bottom_margin - size[1] / 2, size)
        self.fire_timer = 0.0
        self.respawn_timer = 0.0
        self.invulnerable_timer = 0.0

    @property
    def hitbox(self):
        r = self.rect
        scale = self.cfg.player.hitbox_scale
        return r.inflate(-round(r.w * (1 - scale)), -round(r.h * (1 - scale)))

    @property
    def vulnerable(self):
        return self.alive and self.invulnerable_timer <= 0

    def move(self, direction, dt):
        self.x += direction * self.cfg.player.speed * dt
        half = self.w / 2
        self.x = max(half, min(self.cfg.display.width - half, self.x))

    def center(self):
        self.x = self.cfg.display.width / 2


class Bullet(Entity):
    def __init__(self, x, y, vx, vy, size, pierce=0):
        super().__init__(x, y, size)
        self.vx = vx
        self.vy = vy
        self.pierce_left = pierce      # extra enemies it may pass through
        self.hit_ids = set()           # enemies already damaged by this bullet

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt

    def off_screen(self, width, height):
        r = self.rect
        return r.bottom < 0 or r.top > height or r.right < 0 or r.left > width


class Enemy(Entity):
    """A formation alien. kind is 'standard', 'armored' or 'agile'.

    mode:
      formation  - marching with the fleet in its slot
      telegraph  - agile only: shaking in its slot, about to dive
      diving     - agile only: swaying dive toward where the ship was
      returning  - agile only: flying back into its slot from the top
    """

    def __init__(self, uid, kind, etype, slot):
        super().__init__(0, 0, etype.size)
        self.uid = uid
        self.kind = kind
        self.hp = etype.hp
        self.max_hp = etype.hp
        self.points = etype.points
        self.slot = slot                # (dx, dy) offset from the fleet origin
        self.mode = "formation"
        self.mode_timer = 0.0
        self.flash_timer = 0.0          # white flash after being hit
        self.charge_timer = 0.0         # > 0 while winding up a shot
        self.pending_shot = None        # angle of the shot being charged
        self.dive_x0 = 0.0
        self.dive_target_x = 0.0
        self.dive_t = 0.0

    def slot_position(self, origin):
        return origin[0] + self.slot[0], origin[1] + self.slot[1]

    def hit(self, damage, flash):
        self.hp -= damage
        self.flash_timer = flash
        if self.hp <= 0:
            self.alive = False
        return not self.alive

    def start_dive(self, ship_x):
        self.mode = "diving"
        self.dive_x0 = self.x
        self.dive_target_x = ship_x
        self.dive_t = 0.0
        self.charge_timer = 0.0
        self.pending_shot = None

    def update_dive(self, dt, speed, sway, sway_hz):
        self.dive_t += dt
        self.y += speed * dt
        # Drift from the launch column toward where the ship was, swaying
        # side to side so the path is readable but not a straight line.
        drift = min(1.0, self.dive_t / 1.6)
        base_x = self.dive_x0 + (self.dive_target_x - self.dive_x0) * drift
        self.x = base_x + sway * math.sin(self.dive_t * sway_hz * 2 * math.pi)

    def update_return(self, dt, target, speed):
        dx, dy = target[0] - self.x, target[1] - self.y
        dist = math.hypot(dx, dy)
        step = speed * dt
        if dist <= step:
            self.x, self.y = target
            self.mode = "formation"
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step


class Boss(Entity):
    def __init__(self, cfg, index):
        bc = cfg.boss
        super().__init__(cfg.display.width / 2, -bc.size[1], bc.size)
        self.uid = -index
        self.kind = "boss"
        self.index = index
        self.max_hp = bc.hp + bc.hp_per_boss * (index - 1)
        self.hp = self.max_hp
        self.points = bc.points + bc.points_per_boss * (index - 1)
        self.target_y = bc.y
        self.direction = 1
        self.flash_timer = 0.0
        self.pattern_timer = bc.pattern_cooldown
        self.pattern_index = 0
        self.charge_timer = 0.0         # telegraph before a pattern
        self.pending_pattern = None
        self.burst_left = 0
        self.burst_timer = 0.0
        self.second_fan_timer = 0.0

    @property
    def entering(self):
        return self.y < self.target_y

    def in_phase2(self, threshold):
        return self.hp <= self.max_hp * threshold

    def hit(self, damage, flash):
        self.hp -= damage
        self.flash_timer = flash
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return not self.alive

    def move(self, dt, speed, width, margin):
        if self.entering:
            self.y = min(self.target_y, self.y + 120 * dt)
            return
        self.x += self.direction * speed * dt
        half = self.w / 2
        if self.x + half >= width - margin:
            self.x = width - margin - half
            self.direction = -1
        elif self.x - half <= margin:
            self.x = margin + half
            self.direction = 1


class PowerUp(Entity):
    def __init__(self, kind, x, y, size):
        super().__init__(x, y, size)
        self.kind = kind
        self.age = 0.0

    def update(self, dt, fall_speed):
        self.age += dt
        self.y += fall_speed * dt
