"""Everything that draws. Reads the game state, never changes it.

Cosmetic effects (particles, screen shake, floating text) use their own
random generator so they can never change a seeded run.
"""
import math
import os
import random

import pygame

from .game import GAME_OVER, PLAYING, TITLE

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

BG = (8, 10, 24)
HUD_BG = (16, 20, 42)
TEXT = (232, 236, 255)
DIM = (140, 150, 190)
RED = (255, 80, 90)
YELLOW = (255, 225, 90)
CYAN = (90, 220, 255)
VIOLET = (190, 120, 255)
GREEN = (120, 255, 150)
ORANGE = (255, 170, 70)

POWERUP_STYLE = {
    "shield": (CYAN, "S", "SHIELD"),
    "spread": (YELLOW, "3", "SPREAD"),
    "pierce": (VIOLET, "P", "PIERCE"),
    "life": (GREEN, "+", "EXTRA LIFE"),
}


def asset_path(*parts):
    return os.path.join(ASSET_DIR, *parts)


def load_image(name):
    image = pygame.image.load(asset_path("images", name))
    try:
        return image.convert_alpha()
    except pygame.error:          # no display yet (tests)
        return image


def recolor(image, tint):
    """Grayscale the image by brightness, then tint it."""
    out = image.copy()
    w, h = image.get_size()
    pixels = [(x, y) for x in range(w) for y in range(h)]
    lums = {}
    for p in pixels:
        r, g, b, a = image.get_at(p)
        if a:
            lums[p] = 0.3 * r + 0.59 * g + 0.11 * b
    top = max(lums.values(), default=1) or 1
    for p, lum in lums.items():
        k = 0.35 + 0.65 * lum / top
        a = image.get_at(p)[3]
        out.set_at(p, (min(255, int(tint[0] * k)), min(255, int(tint[1] * k)),
                       min(255, int(tint[2] * k)), a))
    return out


def silhouette(image, color=(255, 255, 255)):
    out = image.copy()
    out.fill(color + (0,), special_flags=pygame.BLEND_RGBA_MAX)
    return out


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size")

    def __init__(self, x, y, vx, vy, life, color, size):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color, self.size = color, size


class FloatText:
    __slots__ = ("text", "x", "y", "life", "color", "size")

    def __init__(self, text, x, y, color, size=26, life=1.0):
        self.text, self.x, self.y, self.color, self.size, self.life = text, x, y, color, size, life


class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg
        d = cfg.display
        self.width, self.height = d.width, d.height
        self.world = pygame.Surface((d.width, d.height))
        self.overlay = pygame.Surface((d.width, d.height), pygame.SRCALPHA)
        self.fx_rng = random.Random(1234)
        self.time = 0.0
        self.particles = []
        self.texts = []
        self.rings = []               # (x, y, radius, max_radius, color, life)
        self.shake = 0.0
        self.flash = 0.0
        self.flash_color = RED
        self.hint = ""
        self._fonts = {}
        self._text_cache = {}
        self.stars = [(self.fx_rng.uniform(0, d.width), self.fx_rng.uniform(0, d.height),
                       self.fx_rng.choice((14, 26, 48)), self.fx_rng.randint(70, 220))
                      for _ in range(110)]
        self._load_sprites()

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------
    def _load_sprites(self):
        cfg = self.cfg
        ship = load_image("ship.png")
        alien = load_image("alien.png")
        self.ship_img = pygame.transform.smoothscale(ship, cfg.player.size)
        self.life_icon = pygame.transform.smoothscale(ship, (24, 20))
        self.enemy_imgs = {}
        for kind in ("standard", "armored", "agile"):
            etype = cfg.enemy_type(kind)
            img = pygame.transform.smoothscale(recolor(alien, etype.tint), etype.size)
            self.enemy_imgs[kind] = (img, silhouette(img))
        boss = pygame.transform.smoothscale(recolor(alien, cfg.boss.tint), cfg.boss.size)
        self.boss_imgs = (boss, silhouette(boss))

    def font(self, size):
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def text(self, msg, size, color):
        key = (msg, size, color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 400:
                self._text_cache.clear()
            surf = self._text_cache[key] = self.font(size).render(msg, True, color)
        return surf

    def blit_text(self, target, msg, size, color, **pos):
        surf = self.text(msg, size, color)
        target.blit(surf, surf.get_rect(**pos))

    # ------------------------------------------------------------------
    # Feedback from game events
    # ------------------------------------------------------------------
    def burst(self, x, y, color, count, speed, size=3, life=0.6):
        rng = self.fx_rng
        for _ in range(count):
            angle = rng.uniform(0, math.tau)
            v = rng.uniform(speed * 0.3, speed)
            self.particles.append(Particle(x, y, math.cos(angle) * v, math.sin(angle) * v,
                                           rng.uniform(life * 0.5, life), color, rng.randint(2, size)))

    def handle_events(self, events, game):
        for ev in events:
            kind = ev["type"]
            if kind == "enemy_killed":
                color = self.cfg.enemy_type(ev["kind"]).tint
                self.burst(ev["x"], ev["y"], color, 18, 220)
                self.texts.append(FloatText(f"+{ev['points']}", ev["x"], ev["y"], color, 22, 0.7))
            elif kind in ("enemy_hit", "boss_hit"):
                self.burst(ev["x"], ev["y"] + 10, TEXT, 5, 140, 2, 0.25)
            elif kind == "boss_defeated":
                self.burst(ev["x"], ev["y"], self.cfg.boss.tint, 90, 420, 5, 1.4)
                self.burst(ev["x"], ev["y"], YELLOW, 50, 300, 4, 1.0)
                self.texts.append(FloatText(f"BOSS DOWN  +{ev['points']}", ev["x"], ev["y"], YELLOW, 40, 2.0))
                self.shake = max(self.shake, 0.6)
                self.flash, self.flash_color = 0.5, (255, 255, 255)
            elif kind == "boss_enraged":
                self.texts.append(FloatText("BOSS ENRAGED!", self.width / 2, 260, RED, 40, 1.6))
                self.shake = max(self.shake, 0.3)
            elif kind == "player_hit":
                self.burst(ev["x"], ev["y"], ORANGE, 60, 320, 5, 1.1)
                self.burst(ev["x"], ev["y"], TEXT, 25, 200, 3, 0.7)
                self.shake = max(self.shake, 0.45)
                self.flash, self.flash_color = 0.45, RED
                lives = ev["lives"]
                msg = "LAST LIFE!" if lives == 1 else ("" if lives <= 0 else f"{lives} LIVES LEFT")
                if ev["cause"] == "invasion":
                    msg = "THEY LANDED!  " + msg
                if msg:
                    self.texts.append(FloatText(msg, self.width / 2, self.height / 2, RED, 44, 1.4))
            elif kind == "shield_block":
                self.rings.append([ev["x"], ev["y"], 20, 60, CYAN, 0.3])
            elif kind == "pickup":
                color, _, label = POWERUP_STYLE[ev["kind"]]
                if ev.get("bonus"):
                    label = f"MAX LIVES  +{ev['bonus']}"
                self.burst(ev["x"], ev["y"], color, 24, 200, 3, 0.6)
                self.texts.append(FloatText(label + "!", ev["x"], ev["y"] - 30, color, 32, 1.2))
            elif kind == "powerup_expired":
                color, _, label = POWERUP_STYLE[ev["kind"]]
                self.texts.append(FloatText(f"{label} ended", game.ship.x, game.ship.y - 50, DIM, 22, 1.0))
            elif kind == "special":
                self.rings.append([ev["x"], ev["y"], 10, ev["radius"], (255, 255, 255), 0.45])
                self.flash, self.flash_color = 0.3, (200, 230, 255)
                self.shake = max(self.shake, 0.25)
            elif kind == "wave_started":
                self.hint = ev["hint"]
            elif kind == "run_started":
                self.particles.clear()
                self.texts.clear()
                self.rings.clear()
                self.hint = ""

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, target, game, frame_dt):
        if not game.paused:
            self.time += frame_dt
            self._update_fx(frame_dt)
        world = self.world
        world.fill(BG)
        self._draw_stars(world, 0 if game.paused else frame_dt)
        if game.state != TITLE:
            self._draw_world(world, game)
        self._draw_fx(world)

        offset = (0, 0)
        if self.shake > 0 and not game.paused:
            mag = 10 * self.shake
            offset = (round(self.fx_rng.uniform(-mag, mag)), round(self.fx_rng.uniform(-mag, mag)))
        target.fill(BG)
        target.blit(world, offset)

        if self.flash > 0:
            alpha = int(min(1.0, self.flash) * 150)
            self.overlay.fill(self.flash_color + (alpha,))
            target.blit(self.overlay, (0, 0))

        if game.state == TITLE:
            self._draw_title(target, game)
            return
        self._draw_hud(target, game)
        self._draw_banners(target, game)
        if game.paused:
            self._draw_pause(target)
        elif game.state == GAME_OVER:
            self._draw_game_over(target, game)

    def _update_fx(self, dt):
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= 0.96
            p.vy *= 0.96
            p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0]
        for t in self.texts:
            t.y -= 40 * dt
            t.life -= dt
        self.texts = [t for t in self.texts if t.life > 0]
        for ring in self.rings:
            ring[5] -= dt
            ring[2] += (ring[3] - ring[2]) * min(1.0, dt * 9)
        self.rings = [r for r in self.rings if r[5] > 0]
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt * 1.5)

    def _draw_stars(self, surf, dt):
        h = self.height
        for i, (x, y, speed, b) in enumerate(self.stars):
            y = (y + speed * dt) % h
            self.stars[i] = (x, y, speed, b)
            size = 2 if speed > 40 else 1
            surf.fill((b, b, min(255, b + 30)), (int(x), int(y), size, size))

    def _draw_world(self, surf, game):
        t = self.time
        for pickup in game.pickups:
            color, letter, _ = POWERUP_STYLE[pickup.kind]
            r = pickup.w // 2 + int(2 * math.sin(pickup.age * 8))
            center = (round(pickup.x), round(pickup.y))
            pygame.draw.circle(surf, color, center, r + 3, 2)
            pygame.draw.circle(surf, tuple(c // 3 for c in color), center, r)
            self.blit_text(surf, letter, 26, color, center=center)

        for enemy in game.enemies:
            img, white = self.enemy_imgs[enemy.kind]
            rect = enemy.rect
            if enemy.mode == "telegraph":
                rect.x += round(3 * math.sin(t * 70))
                if int(t * 10) % 2 == 0:
                    pygame.draw.rect(surf, ORANGE, rect.inflate(8, 8), 2, border_radius=6)
            surf.blit(white if enemy.flash_timer > 0 else img, rect)
            if enemy.max_hp > 1:
                for i in range(enemy.max_hp):
                    color = CYAN if i < enemy.hp else (50, 60, 90)
                    surf.fill(color, (rect.centerx - enemy.max_hp * 5 + i * 10, rect.top - 7, 8, 4))
            if enemy.charge_timer > 0:
                k = 1 - enemy.charge_timer / self.cfg.enemy_fire.telegraph
                pygame.draw.circle(surf, RED, (rect.centerx, rect.bottom + 2), 3 + int(5 * k))

        boss = game.boss
        if boss and boss.alive:
            img, white = self.boss_imgs
            rect = boss.rect
            if boss.charge_timer > 0 and int(t * 14) % 2 == 0:
                pygame.draw.ellipse(surf, RED, rect.inflate(16, 16), 3)
            surf.blit(white if boss.flash_timer > 0 else img, rect)
            if boss.charge_timer > 0:
                k = 1 - boss.charge_timer / self.cfg.boss.telegraph
                pygame.draw.circle(surf, RED, (rect.centerx, rect.bottom + 4), 4 + int(12 * k))

        for b in game.bullets:
            color = VIOLET if b.pierce_left > 0 else YELLOW
            surf.fill(color, b.rect)
        for b in game.enemy_bullets:
            r = b.rect
            surf.fill((120, 20, 40), r.inflate(4, 4))
            surf.fill((255, 120, 140), r)

        ship = game.ship
        if ship.alive:
            blinking = ship.invulnerable_timer > 0 and int(t * 12) % 2 == 1
            if not blinking:
                surf.blit(self.ship_img, ship.rect)
            shield = game.powerups.get("shield")
            if shield is not None:
                warn = shield < self.cfg.powerups.expiry_warning and int(t * 8) % 2 == 0
                if not warn:
                    radius = max(ship.w, ship.h) // 2 + 12
                    bubble = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
                    c = radius + 2
                    pygame.draw.circle(bubble, CYAN + (60,), (c, c), radius)
                    pygame.draw.circle(bubble, CYAN + (200,), (c, c), radius, 2)
                    surf.blit(bubble, bubble.get_rect(center=(round(ship.x), round(ship.y))))

    def _draw_fx(self, surf):
        for p in self.particles:
            k = p.life / p.max_life
            color = tuple(int(c * (0.4 + 0.6 * k)) for c in p.color)
            surf.fill(color, (int(p.x), int(p.y), p.size, p.size))
        for x, y, radius, _, color, _ in self.rings:
            pygame.draw.circle(surf, color, (round(x), round(y)), int(radius), 3)
        for t in self.texts:
            self.blit_text(surf, t.text, t.size, t.color, center=(round(t.x), round(t.y)))

    # ------------------------------------------------------------------
    # HUD and overlays
    # ------------------------------------------------------------------
    def _draw_hud(self, surf, game):
        cfg = self.cfg
        hud_h = cfg.display.hud_height
        surf.fill(HUD_BG, (0, 0, self.width, hud_h))
        pygame.draw.line(surf, (50, 60, 110), (0, hud_h - 1), (self.width, hud_h - 1))
        mid = hud_h // 2
        self.blit_text(surf, f"SCORE {game.score:,}", 30, TEXT, midleft=(14, mid))
        self.blit_text(surf, f"HI {max(game.high_score, game.score):,}", 24, DIM, midleft=(230, mid))
        self.blit_text(surf, f"WAVE {game.wave}", 30, YELLOW, center=(self.width // 2, mid))

        # Lives (ship icons) and special charges (diamonds), right aligned.
        x = self.width - 14
        for i in range(cfg.player.special_max):
            cx = x - 8
            points = [(cx, mid - 8), (cx + 7, mid), (cx, mid + 8), (cx - 7, mid)]
            if i < game.specials:
                pygame.draw.polygon(surf, ORANGE, points)
            else:
                pygame.draw.polygon(surf, (70, 70, 100), points, 1)
            x -= 18
        self.blit_text(surf, "SPECIAL", 20, DIM, midright=(x - 2, mid))
        x -= 76
        for i in range(game.lives):
            rect = self.life_icon.get_rect(midright=(x, mid))
            surf.blit(self.life_icon, rect)
            x -= 28
        self.blit_text(surf, "LIVES", 20, DIM, midright=(x - 2, mid))

        # Active power-ups with remaining time, bottom left.
        y = self.height - 26
        for kind in ("shield", "spread", "pierce"):
            remaining = game.powerups.get(kind)
            if remaining is None:
                continue
            color, _, label = POWERUP_STYLE[kind]
            warn = remaining < cfg.powerups.expiry_warning and int(self.time * 6) % 2 == 0
            full = cfg.powerups.durations[kind]
            surf.fill((30, 34, 60), (14, y, 120, 12))
            surf.fill(DIM if warn else color, (14, y, int(120 * remaining / full), 12))
            self.blit_text(surf, f"{label} {remaining:0.1f}s", 22, color, midleft=(142, y + 6))
            y -= 22

        boss = game.boss
        if boss and boss.alive:
            w = 420
            x0 = (self.width - w) // 2
            surf.fill((40, 20, 30), (x0, hud_h + 8, w, 12))
            surf.fill(RED, (x0, hud_h + 8, int(w * boss.hp / boss.max_hp), 12))
            pygame.draw.rect(surf, TEXT, (x0, hud_h + 8, w, 12), 1)
            self.blit_text(surf, f"BOSS #{boss.index}", 20, RED, midright=(x0 - 8, hud_h + 14))

    def _draw_banners(self, surf, game):
        cx, cy = self.width // 2, self.height // 2 - 40
        if game.state != PLAYING:
            return
        if game.banner_timer > 0:
            if game.plan and game.plan.is_boss:
                if int(self.time * 4) % 2 == 0:
                    self.blit_text(surf, "WARNING: BOSS APPROACHING", 56, RED, center=(cx, cy))
            else:
                self.blit_text(surf, f"WAVE {game.wave}", 72, YELLOW, center=(cx, cy))
            if self.hint:
                self.blit_text(surf, self.hint, 30, TEXT, center=(cx, cy + 50))
        elif game.clear_timer > 0:
            bonus = self.cfg.score.wave_clear_bonus * game.wave
            self.blit_text(surf, "WAVE CLEAR", 64, GREEN, center=(cx, cy))
            self.blit_text(surf, f"+{bonus} bonus", 30, TEXT, center=(cx, cy + 46))

    def _dim(self, surf, alpha=160):
        self.overlay.fill((0, 0, 10, alpha))
        surf.blit(self.overlay, (0, 0))

    def _draw_pause(self, surf):
        self._dim(surf)
        cx, cy = self.width // 2, self.height // 2
        self.blit_text(surf, "PAUSED", 80, TEXT, center=(cx, cy - 30))
        self.blit_text(surf, "Press P or Esc to resume", 30, DIM, center=(cx, cy + 30))

    def _draw_game_over(self, surf, game):
        self._dim(surf, 170)
        cx, cy = self.width // 2, self.height // 2
        self.blit_text(surf, "GAME OVER", 88, RED, center=(cx, cy - 80))
        self.blit_text(surf, f"Score {game.score:,}", 44, TEXT, center=(cx, cy - 10))
        self.blit_text(surf, f"Reached wave {game.wave}   ·   {game.kills} aliens destroyed",
                       28, DIM, center=(cx, cy + 34))
        if game.new_high_score:
            self.blit_text(surf, "NEW HIGH SCORE!", 32, YELLOW, center=(cx, cy + 74))
        self.blit_text(surf, "Press R (or click) to play again", 32, TEXT, center=(cx, cy + 120))

    def _draw_title(self, surf, game):
        cx = self.width // 2
        self.blit_text(surf, "ALIEN INVASION", 96, GREEN, center=(cx, 150))
        img = self.enemy_imgs
        for i, kind in enumerate(("standard", "armored", "agile")):
            x = cx - 220 + i * 220
            surf.blit(img[kind][0], img[kind][0].get_rect(center=(x, 250)))
            label = {"standard": "Standard · 1 hit", "armored": "Armored · 3 hits",
                     "agile": "Agile · dives"}[kind]
            self.blit_text(surf, label, 24, self.cfg.enemy_type(kind).tint, center=(x, 290))
        lines = [
            "Move: Arrow keys or A / D       Shoot: Space (hold)",
            "Special shockwave: Shift       Pause: P or Esc",
            "Power-ups:  S shield   3 spread   P pierce   + extra life",
        ]
        for i, line in enumerate(lines):
            self.blit_text(surf, line, 28, DIM, center=(cx, 360 + i * 34))
        if int(self.time * 2) % 2 == 0:
            self.blit_text(surf, "Press Space or Enter (or click) to start", 38, TEXT, center=(cx, 500))
        if game.high_score:
            self.blit_text(surf, f"High score {game.high_score:,}", 28, YELLOW, center=(cx, 550))
