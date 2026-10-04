"""Everything that draws. Reads the game state, never changes it.

Cosmetic effects (particles, screen shake, floating text, stars) use their
own random generator so they can never change a seeded run.
"""
import math
import os
import random

import pygame

from .config import CYAN, GOLD, GREEN, ORANGE, PINK, RED, STEEL, VIOLET, WHITE, YELLOW
from .entities import PART_SIZES
from .game import GAME_OVER, PLAYING, TITLE
from .levels import THEMES

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

TEXT = (232, 236, 255)
DIM = (140, 150, 190)
PANEL = (12, 16, 36)
PANEL_EDGE = (50, 60, 110)

ENEMY_COLORS = {"drone": (90, 240, 150), "wasp": (255, 210, 60), "striker": (90, 210, 255),
                "lancer": (255, 160, 70), "guardian": (190, 130, 255), "dreadnought": (255, 90, 90),
                "cargo": (220, 220, 230), "asteroid": (160, 140, 120), "mine": (255, 90, 90)}


def asset_path(*parts):
    return os.path.join(ASSET_DIR, *parts)


def load_image(name):
    image = pygame.image.load(asset_path("images", name + ".png"))
    try:
        return image.convert_alpha()
    except pygame.error:          # no display yet (tests)
        return image


def silhouette(image, color=(255, 255, 255)):
    out = image.copy()
    out.fill(color + (0,), special_flags=pygame.BLEND_RGBA_MAX)
    return out


def darkened(image, k=0.35):
    out = image.copy()
    v = int(255 * k)
    out.fill((v, v, v, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return out


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "drag")

    def __init__(self, x, y, vx, vy, life, color, size, drag=0.94):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color, self.size, self.drag = color, size, drag


class FloatText:
    __slots__ = ("text", "x", "y", "life", "color", "size")

    def __init__(self, text, x, y, color, size=24, life=1.0):
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
        self.rings = []               # [x, y, radius, max_radius, color, life, max_life, width]
        self.bolts = []               # [points, life]
        self.delayed = []             # [delay, x, y, color, size] boss explosion chain
        self.shake = 0.0
        self.flash = 0.0
        self.flash_color = RED
        self.banner = None            # (title, subtitle, color, time_left)
        self.theme = 0
        self.warp = 0.0
        self.hint = ""
        self._fonts = {}
        self._text_cache = {}
        self._glows = {}
        self._nebulas = {}
        self.stars = [[self.fx_rng.uniform(0, d.width), self.fx_rng.uniform(0, d.height),
                       layer, self.fx_rng.randint(90, 230)]
                      for layer in (0, 1, 2) for _ in range((70, 45, 25)[layer])]
        self._load_sprites()

    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------
    def _load_sprites(self):
        cfg = self.cfg
        self.ship_img = load_image("player")
        self.life_icon = pygame.transform.smoothscale(self.ship_img, (16, 18))
        self.wingman_img = load_image("wingman")
        self.enemy_imgs = {}
        for kind in cfg.enemies:
            img = load_image(f"enemy_{kind}")
            self.enemy_imgs[kind] = (img, silhouette(img))
        self.asteroid_frames = [pygame.transform.rotate(self.enemy_imgs["asteroid"][0], a)
                                for a in range(0, 360, 15)]
        self.boss_imgs = [load_image(f"boss_{i + 1}") for i in range(len(cfg.bosses))]
        self.part_imgs = {}
        for kind in PART_SIZES:
            img = load_image(f"part_{kind}")
            self.part_imgs[kind] = (img, silhouette(img), darkened(img))
        self.icons = {kind: load_image(f"icon_{kind}") for kind in list(cfg.weapons) + list(cfg.pickups)}

    def font(self, size):
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def text(self, msg, size, color):
        key = (msg, size, color)
        surf = self._text_cache.get(key)
        if surf is None:
            if len(self._text_cache) > 500:
                self._text_cache.clear()
            surf = self._text_cache[key] = self.font(size).render(msg, True, color)
        return surf

    def blit_text(self, target, msg, size, color, shadow=False, **pos):
        surf = self.text(msg, size, color)
        rect = surf.get_rect(**pos)
        if shadow:
            target.blit(self.text(msg, size, (0, 0, 0)), rect.move(2, 2))
        target.blit(surf, rect)
        return rect

    def glow(self, color, radius):
        """A cached soft radial glow, drawn with additive blending."""
        key = (color, radius)
        surf = self._glows.get(key)
        if surf is None:
            surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            for i in range(12, 0, -1):
                k = i / 12
                a = int(150 * (1 - k) ** 1.8)
                pygame.draw.circle(surf, tuple(int(c * a / 255) for c in color) + (255,), (radius, radius),
                                   int(radius * k))
            self._glows[key] = surf
        return surf

    def add_glow(self, target, x, y, color, radius):
        g = self.glow(color, radius)
        target.blit(g, (round(x) - radius, round(y) - radius), special_flags=pygame.BLEND_RGB_ADD)

    def nebula(self, theme):
        """Pre-rendered background: soft additive gas clouds over a dark base."""
        surf = self._nebulas.get(theme)
        if surf is None:
            base, colors = THEMES[theme % len(THEMES)]
            rng = random.Random(theme * 97 + 5)
            surf = pygame.Surface((self.width, self.height))
            surf.fill(base)
            for _ in range(18):
                color = rng.choice(colors)
                r = int(rng.uniform(90, 230))
                dim = tuple(int(c * rng.uniform(0.25, 0.45)) for c in color)
                g = self.glow(dim, r)
                surf.blit(g, (rng.uniform(-r, self.width - r), rng.uniform(-r, self.height - r)),
                          special_flags=pygame.BLEND_RGB_ADD)
            self._nebulas[theme] = surf
        return surf

    # ------------------------------------------------------------------
    # Feedback from game events
    # ------------------------------------------------------------------
    def burst(self, x, y, color, count, speed, size=3, life=0.6):
        rng = self.fx_rng
        for _ in range(count):
            angle = rng.uniform(0, math.tau)
            v = rng.uniform(speed * 0.25, speed)
            self.particles.append(Particle(x, y, math.cos(angle) * v, math.sin(angle) * v,
                                           rng.uniform(life * 0.5, life), color, rng.randint(2, size)))

    def explode(self, x, y, color, scale=1.0):
        self.burst(x, y, color, int(22 * scale), 260 * scale, 4, 0.7)
        self.burst(x, y, (255, 230, 170), int(10 * scale), 160 * scale, 3, 0.4)
        self.rings.append([x, y, 6, 40 * scale, (255, 220, 160), 0.3, 0.3, 3])

    def float_text(self, msg, x, y, color, size=24, life=1.0):
        self.texts.append(FloatText(msg, x, y, color, size, life))

    def set_banner(self, title, subtitle, color, duration):
        self.banner = (title, subtitle, color, duration)

    def handle_events(self, events, game):
        cfg = self.cfg
        for ev in events:
            kind = ev["type"]
            x, y = ev.get("x", 0), ev.get("y", 0)
            if kind == "enemy_killed":
                color = ENEMY_COLORS.get(ev["kind"], WHITE)
                self.explode(x, y, color, 2.0 if ev.get("big") else 1.0)
                if ev.get("big"):
                    self.shake = max(self.shake, 0.3)
                self.float_text(f"+{ev['points']}", x, y - 10, color, 22, 0.6)
            elif kind in ("enemy_hit", "part_hit"):
                self.burst(x, y + 8, (255, 255, 230), 3, 160, 2, 0.2)
            elif kind == "deflect":
                self.burst(x, y, (200, 210, 255), 2, 120, 2, 0.15)
            elif kind == "part_destroyed":
                self.explode(x, y, ORANGE, 2.2)
                self.shake = max(self.shake, 0.35)
                self.float_text(f"WEAPON DOWN +{ev['points']}", x, y + 30, YELLOW, 24, 1.0)
            elif kind == "boss_stage":
                self.set_banner(f"STAGE {ev['stage']} / {ev['stages']}",
                                "Armor breached! New weapons online" if ev["stage"] < ev["stages"]
                                else "The core is exposed - hit it!", RED, 2.0)
                self.flash, self.flash_color = 0.3, (255, 255, 255)
            elif kind == "boss_defeated":
                rng = self.fx_rng
                for i in range(14):
                    self.delayed.append([i * 0.1, x + rng.uniform(-ev["w"] / 2, ev["w"] / 2),
                                         y + rng.uniform(-ev["h"] / 2, ev["h"] / 2), ORANGE, 2.5])
                self.shake = max(self.shake, 1.2)
                self.flash, self.flash_color = 0.6, (255, 255, 255)
                self.set_banner(f"{ev['name'].upper()} DESTROYED", f"+{ev['points']:,}", YELLOW, 2.2)
            elif kind == "boss_spawned":
                self.set_banner("WARNING", f"{ev['name']} approaching", RED, cfg.flow.boss_banner)
            elif kind == "player_damaged":
                self.burst(x, y, ORANGE, 12, 220, 3, 0.4)
                self.shake = max(self.shake, 0.18 + ev["amount"] / 100)
                self.flash, self.flash_color = 0.25, RED
            elif kind == "player_destroyed":
                self.explode(x, y, ORANGE, 3.0)
                self.shake = max(self.shake, 0.7)
                self.flash, self.flash_color = 0.5, RED
                lives = ev["lives"]
                if lives > 0:
                    self.set_banner("SHIP DESTROYED", "Last ship!" if lives == 1 else f"{lives} ships left",
                                    RED, 1.4)
            elif kind == "shield_block":
                self.rings.append([x, y, 30, 52, CYAN, 0.25, 0.25, 3])
            elif kind == "pickup":
                color = self._pickup_color(ev["kind"])
                self.burst(x, y, color, 20, 220, 3, 0.5)
                label = ev["label"].upper() + ("!" if not ev.get("bonus") else f" +{ev['bonus']}")
                self.float_text(label, x, y - 34, color, 30, 1.1)
            elif kind == "pickup_missed":
                self.float_text("missed", game.ship.x, self.height - 70, DIM, 18, 0.6)
            elif kind == "weapon_empty":
                self.float_text(f"{cfg.weapons[ev['weapon']].label} empty", game.ship.x,
                                game.ship.y - 50, DIM, 22, 0.9)
            elif kind == "buff_expired":
                self.float_text(f"{cfg.pickups[ev['kind']].label} ended", game.ship.x,
                                game.ship.y - 50, DIM, 22, 0.9)
            elif kind == "shockwave":
                self.flash, self.flash_color = 0.35, (180, 220, 255)
                self.shake = max(self.shake, 0.35)
            elif kind == "shock_ready":
                self.float_text("SHOCKWAVE READY", game.ship.x, game.ship.y - 60, CYAN, 24, 1.0)
            elif kind == "chain":
                self.bolts.append([ev["points"], 0.14])
            elif kind == "explosion":
                r = ev["radius"]
                self.rings.append([x, y, 10, r, (255, 170, 90), 0.35, 0.35, 4])
                self.burst(x, y, (255, 150, 70), 26, r * 3, 4, 0.5)
            elif kind == "flak_burst":
                self.burst(x, y, GOLD, 8, 200, 2, 0.25)
            elif kind == "missile_down":
                self.burst(x, y, ORANGE, 8, 160, 2, 0.3)
            elif kind == "multiplier":
                self.float_text(f"x{ev['value']} COMBO", self.width / 2, 90, PINK, 34, 1.0)
            elif kind == "mine_armed":
                pass
            elif kind == "cargo_spotted":
                self.float_text("SUPPLY POD! Shoot it", self.width / 2, 120, GREEN, 28, 1.5)
            elif kind == "level_started":
                self.theme = ev["theme"]
                if not ev["boss"]:
                    self.set_banner(f"LEVEL {ev['level']}", ev["name"], YELLOW, cfg.flow.level_banner)
                self.hint = ev["hint"]
            elif kind == "level_cleared":
                self.set_banner("SECTOR CLEAR", f"+{ev['bonus']:,} bonus", GREEN, cfg.flow.level_clear_delay)
                self.warp = cfg.flow.level_clear_delay
            elif kind == "run_started":
                self.particles.clear()
                self.texts.clear()
                self.rings.clear()
                self.bolts.clear()
                self.delayed.clear()
                self.banner = None
                self.hint = ""

    def _pickup_color(self, kind):
        if kind in self.cfg.weapons:
            return self.cfg.weapons[kind].color
        return self.cfg.pickups[kind].color

    # ------------------------------------------------------------------
    # Frame
    # ------------------------------------------------------------------
    def draw(self, target, game, frame_dt):
        if not game.paused:
            self.time += frame_dt
            self._update_fx(frame_dt)
        world = self.world
        self._draw_background(world, 0 if game.paused else frame_dt)
        if game.state != TITLE:
            self._draw_world(world, game)
        self._draw_fx(world)

        offset = (0, 0)
        if self.shake > 0 and not game.paused:
            mag = 9 * min(1.0, self.shake)
            offset = (round(self.fx_rng.uniform(-mag, mag)), round(self.fx_rng.uniform(-mag, mag)))
        target.fill((0, 0, 0))
        target.blit(world, offset)

        if self.flash > 0:
            self.overlay.fill(self.flash_color + (int(min(1.0, self.flash) * 120),))
            target.blit(self.overlay, (0, 0))

        if game.state == TITLE:
            self._draw_title(target, game)
            return
        self._draw_low_hull(target, game)
        self._draw_hud(target, game)
        self._draw_banner(target, game)
        if game.paused:
            self._draw_pause(target)
        elif game.state == GAME_OVER:
            self._draw_game_over(target, game)

    def _update_fx(self, dt):
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= p.drag
            p.vy *= p.drag
            p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0][-900:]
        for t in self.texts:
            t.y -= 45 * dt
            t.life -= dt
        self.texts = [t for t in self.texts if t.life > 0]
        for ring in self.rings:
            ring[5] -= dt
            ring[2] += (ring[3] - ring[2]) * min(1.0, dt * 10)
        self.rings = [r for r in self.rings if r[5] > 0]
        for bolt in self.bolts:
            bolt[1] -= dt
        self.bolts = [b for b in self.bolts if b[1] > 0]
        for item in self.delayed:
            item[0] -= dt
            if item[0] <= 0:
                self.explode(item[1], item[2], item[3], item[4])
        self.delayed = [d for d in self.delayed if d[0] > 0]
        self.shake = max(0.0, self.shake - dt)
        self.flash = max(0.0, self.flash - dt * 1.6)
        self.warp = max(0.0, self.warp - dt)
        if self.banner:
            title, sub, color, left = self.banner
            self.banner = (title, sub, color, left - dt) if left - dt > 0 else None

    def _draw_background(self, surf, dt):
        surf.blit(self.nebula(self.theme), (0, 0))
        boost = 1 + 5 * min(1.0, self.warp)
        speeds = (30, 90, 220)
        for star in self.stars:
            x, y, layer, b = star
            speed = speeds[layer] * boost
            star[1] = (y + speed * dt) % self.height
            length = 1 + int(speed / 120) + (int(speed / 60) if self.warp > 0 else 0)
            size = 1 if layer < 2 else 2
            c = (b, b, min(255, b + 25)) if layer else (b // 2, b // 2, b // 2 + 30)
            surf.fill(c, (int(x), int(star[1]), size, length))

    # ------------------------------------------------------------------
    # World
    # ------------------------------------------------------------------
    def _draw_world(self, surf, game):
        t = self.time
        height = self.height
        er = self.cfg.enemy

        boss = game.boss
        if boss:
            self._draw_boss(surf, boss, game)

        # Beams first so ships draw on top of them.
        for enemy in game.enemies:
            if enemy.state == "beam_charge":
                self._beam_warning(surf, enemy.beam_x, enemy.y + enemy.h / 2, er.beam_width)
            elif enemy.state == "beam":
                self._beam(surf, enemy.beam_x, enemy.y + enemy.h / 2, er.beam_width, ORANGE)
        if boss:
            for part in boss.parts:
                if part.alive and part.beam_state == "charge":
                    self._beam_warning(surf, part.x, part.y + part.h / 2, er.beam_width * 1.6)
                elif part.alive and part.beam_state == "beam":
                    self._beam(surf, part.x, part.y + part.h / 2, er.beam_width * 1.6, PINK)

        for pickup in game.pickups:
            self._draw_pickup(surf, pickup)

        for enemy in game.enemies:
            self._draw_enemy(surf, enemy, t)

        for shot in game.enemy_shots:
            self._draw_enemy_shot(surf, shot)

        self._draw_ship(surf, game)

        for shot in game.shots:
            self._draw_shot(surf, shot)

        for wave in game.shockwaves:
            k = 1 - wave.radius / wave.max_radius
            r = int(wave.radius)
            pygame.draw.circle(surf, (120, 200, 255), (round(wave.x), round(wave.y)), r, max(2, int(10 * k)))
            pygame.draw.circle(surf, (255, 255, 255), (round(wave.x), round(wave.y)), max(1, r - 4), 2)

        for enemy in game.enemies:
            if enemy.kind == "mine" and enemy.armed >= 0:
                pygame.draw.circle(surf, RED, (round(enemy.x), round(enemy.y)), int(er.mine_radius), 1)

    def _beam_warning(self, surf, x, y, width):
        if int(self.time * 20) % 2 == 0:
            pygame.draw.line(surf, (255, 60, 60), (x, y), (x, self.height), 2)
        self.add_glow(surf, x, y, (255, 60, 60), 14)
        pygame.draw.line(surf, (120, 20, 30), (x - width / 2, y), (x - width / 2, self.height), 1)
        pygame.draw.line(surf, (120, 20, 30), (x + width / 2, y), (x + width / 2, self.height), 1)

    def _beam(self, surf, x, y, width, color):
        flicker = 1 + 0.25 * math.sin(self.time * 60)
        w = width * flicker
        top = round(y)
        surf.fill(tuple(c // 3 for c in color), (round(x - w), top, round(w * 2), self.height - top))
        surf.fill(color, (round(x - w / 2), top, round(w), self.height - top))
        surf.fill((255, 255, 255), (round(x - w / 5), top, max(2, round(w / 2.5)), self.height - top))
        self.add_glow(surf, x, y, color, 22)

    def _draw_enemy(self, surf, enemy, t):
        kind = enemy.kind
        img, white = self.enemy_imgs[kind]
        rect = enemy.rect
        if kind == "asteroid":
            angle = (enemy.spin * enemy.age) % 360
            frame = self.asteroid_frames[int(angle / 15) % len(self.asteroid_frames)]
            surf.blit(frame, frame.get_rect(center=rect.center))
            return
        if enemy.state == "aim" or enemy.state == "dive" and enemy.t < 0.2:
            rect.x += round(3 * math.sin(t * 70))
        sprite = white if enemy.flash > 0 else img
        surf.blit(sprite, rect)
        if kind == "mine":
            on = enemy.armed >= 0 and int(t * 16) % 2 == 0 or int(t * 3) % 2 == 0
            if on:
                self.add_glow(surf, enemy.x, enemy.y, (255, 50, 50), 14)
        if enemy.charge_timer > 0:
            k = 1 - enemy.charge_timer / self.cfg.enemy.charge_time
            self.add_glow(surf, enemy.x, rect.bottom, (255, 80, 80), 6 + int(10 * k))
        if enemy.max_hp > 1 and enemy.hp < enemy.max_hp:
            w = max(24, rect.w - 8)
            x0 = rect.centerx - w // 2
            surf.fill((40, 10, 20), (x0, rect.top - 7, w, 4))
            surf.fill((120, 255, 140), (x0, rect.top - 7, int(w * max(0.0, enemy.hp) / enemy.max_hp), 4))

    def _draw_boss(self, surf, boss, game):
        img = self.boss_imgs[boss.index]
        surf.blit(img, boss.rect)
        t = self.time
        for part in boss.parts:
            normal, white, dark = self.part_imgs[part.kind]
            rect = part.rect
            if not part.alive:
                surf.blit(dark, rect)
                if int(t * 6 + part.uid) % 7 == 0:
                    self.burst(part.x, part.y, (90, 90, 90), 1, 40, 3, 0.6)
                continue
            if part.stage > boss.stage:
                surf.blit(dark, rect)
                pygame.draw.rect(surf, (90, 90, 110), rect.inflate(-6, -6), 1, border_radius=6)
                continue
            vulnerable = boss.stage_timer <= 0 and not boss.entering
            surf.blit(white if part.flash > 0 else normal, rect)
            if part.charge_timer > 0 or part.beam_state == "charge":
                self.add_glow(surf, part.x, rect.bottom, (255, 70, 70), 18)
            if vulnerable:
                pulse = 0.5 + 0.5 * math.sin(t * 6)
                color = (255, int(150 + 80 * pulse), 80)
                pygame.draw.rect(surf, color, rect.inflate(6, 6), 2, border_radius=8)
                w = rect.w
                surf.fill((40, 10, 20), (rect.x, rect.bottom + 4, w, 4))
                surf.fill(YELLOW, (rect.x, rect.bottom + 4, int(w * max(0.0, part.hp) / part.max_hp), 4))
        if boss.stage_timer > 0 and int(t * 10) % 2 == 0:
            pygame.draw.rect(surf, (255, 255, 255), boss.rect, 2, border_radius=12)

    def _draw_pickup(self, surf, pickup):
        color = self._pickup_color(pickup.kind)
        center = (round(pickup.x), round(pickup.y))
        low = pickup.y > self.height - 130
        if low and int(self.time * 10) % 2 == 0:
            return
        self.add_glow(surf, pickup.x, pickup.y, color, 26)
        r = 15 + int(2 * math.sin(pickup.age * 7))
        if pickup.category == "weapon":
            pts = [(center[0] + math.cos(i * math.tau / 6 + math.pi / 6) * r,
                    center[1] + math.sin(i * math.tau / 6 + math.pi / 6) * r) for i in range(6)]
            pygame.draw.polygon(surf, (10, 12, 28), pts)
            pygame.draw.polygon(surf, color, pts, 2)
        else:
            pygame.draw.circle(surf, (10, 12, 28), center, r)
            pygame.draw.circle(surf, color, center, r, 2)
        icon = self.icons[pickup.kind]
        surf.blit(icon, icon.get_rect(center=center))

    def _draw_enemy_shot(self, surf, shot):
        x, y = round(shot.x), round(shot.y)
        if shot.kind == "missile":
            angle = math.atan2(shot.vy, shot.vx)
            dx, dy = math.cos(angle), math.sin(angle)
            tail = (x - dx * 12, y - dy * 12)
            pygame.draw.line(surf, (200, 200, 210), tail, (x + dx * 6, y + dy * 6), 5)
            pygame.draw.circle(surf, RED, (x + round(dx * 6), y + round(dy * 6)), 3)
            self.add_glow(surf, tail[0], tail[1], (255, 140, 60), 9)
            if self.fx_rng.random() < 0.5:
                self.particles.append(Particle(tail[0], tail[1], 0, 0, 0.3, (150, 150, 160), 3, 1.0))
        elif shot.kind == "orb":
            self.add_glow(surf, x, y, (255, 70, 200), 12)
            pygame.draw.circle(surf, (255, 150, 230), (x, y), 5)
            pygame.draw.circle(surf, (255, 255, 255), (x, y), 2)
        elif shot.kind == "bolt":
            self.add_glow(surf, x, y, (255, 140, 40), 10)
            surf.fill((255, 170, 60), shot.rect)
            surf.fill((255, 250, 220), shot.rect.inflate(-4, -4))
        else:
            self.add_glow(surf, x, y, (255, 60, 80), 9)
            surf.fill((255, 90, 110), shot.rect.inflate(-2, 0))
            surf.fill((255, 230, 230), shot.rect.inflate(-5, -4))

    def _draw_shot(self, surf, shot):
        x, y = round(shot.x), round(shot.y)
        kind = shot.kind
        if kind == "rail":
            r = shot.rect
            self.add_glow(surf, x, y, CYAN, 18)
            surf.fill(CYAN, r)
            surf.fill((255, 255, 255), r.inflate(-3, 0))
        elif kind == "homing":
            pygame.draw.circle(surf, RED, (x, y), 4)
            self.add_glow(surf, x, y, (255, 120, 60), 9)
            if self.fx_rng.random() < 0.6:
                self.particles.append(Particle(x, y, 0, 0, 0.25, (255, 160, 90), 3, 1.0))
        elif kind == "plasma":
            self.add_glow(surf, x, y, VIOLET, 24)
            pygame.draw.circle(surf, (210, 160, 255), (x, y), 8)
            pygame.draw.circle(surf, (255, 255, 255), (x, y), 4)
        elif kind == "flak":
            self.add_glow(surf, x, y, GOLD, 12)
            pygame.draw.circle(surf, GOLD, (x, y), 5)
        elif kind == "shrapnel":
            surf.fill(GOLD, (x - 2, y - 2, 4, 4))
        else:
            r = shot.rect
            self.add_glow(surf, x, y, (255, 220, 90), 8)
            surf.fill((255, 230, 120), r)
            surf.fill((255, 255, 255), r.inflate(-2, -6))

    def _draw_ship(self, surf, game):
        ship = game.ship
        if not ship.alive:
            return
        t = self.time
        rect = ship.rect
        # Engine flame
        flame = 10 + self.fx_rng.uniform(0, 8)
        self.add_glow(surf, ship.x, rect.bottom, (255, 140, 50), int(flame + 6))
        pygame.draw.polygon(surf, (255, 200, 90), [(ship.x - 5, rect.bottom - 4), (ship.x + 5, rect.bottom - 4),
                                                   (ship.x, rect.bottom + flame)])
        if "overdrive" in ship.buffs:
            self.add_glow(surf, ship.x, ship.y, PINK, 46)
        if ship.laser_on:
            top = max(0, round(ship.laser_top))
            bottom = rect.top
            w = 6 + 2 * math.sin(t * 50)
            surf.fill((120, 30, 90), (round(ship.x - w * 1.4), top, round(w * 2.8), bottom - top))
            surf.fill(PINK, (round(ship.x - w / 2), top, round(w), bottom - top))
            surf.fill((255, 255, 255), (round(ship.x - 1), top, 3, bottom - top))
            self.add_glow(surf, ship.x, top, PINK, 20)
            self.add_glow(surf, ship.x, bottom, PINK, 14)
        blinking = (ship.invulnerable_timer > 0 or ship.hurt_timer > 0) and int(t * 16) % 2 == 1
        if not blinking:
            surf.blit(self.ship_img, rect)
        if "wingmen" in ship.buffs:
            for side in (-1, 1):
                wx = ship.x + side * 44
                wy = ship.y + 6 + 3 * math.sin(t * 5 + side)
                surf.blit(self.wingman_img, self.wingman_img.get_rect(center=(round(wx), round(wy))))
        if ship.shield > 0:
            radius = 36
            pulse = int(40 + 25 * math.sin(t * 6))
            bubble = self._bubble(radius, pulse)
            surf.blit(bubble, bubble.get_rect(center=rect.center))
        if ship.armor > 0:
            k = ship.armor / self.cfg.player.max_armor
            pygame.draw.arc(surf, STEEL, rect.inflate(18, 18), math.pi * (0.5 - k), math.pi * (0.5 + k), 3)

    def _bubble(self, radius, alpha):
        key = ("bubble", radius, alpha // 5)
        surf = self._glows.get(key)
        if surf is None:
            surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
            c = radius + 2
            pygame.draw.circle(surf, CYAN + (alpha,), (c, c), radius)
            pygame.draw.circle(surf, CYAN + (220,), (c, c), radius, 2)
            self._glows[key] = surf
        return surf

    def _draw_fx(self, surf):
        for p in self.particles:
            k = p.life / p.max_life
            color = tuple(int(c * (0.35 + 0.65 * k)) for c in p.color)
            surf.fill(color, (int(p.x), int(p.y), p.size, p.size))
        for x, y, radius, _, color, life, max_life, width in self.rings:
            k = life / max_life
            pygame.draw.circle(surf, tuple(int(c * k) for c in color), (round(x), round(y)), int(radius),
                               max(1, int(width * k)))
        rng = self.fx_rng
        for points, life in self.bolts:
            for (x0, y0), (x1, y1) in zip(points, points[1:]):
                segs = [(x0, y0)]
                for i in range(1, 6):
                    k = i / 6
                    segs.append((x0 + (x1 - x0) * k + rng.uniform(-9, 9), y0 + (y1 - y0) * k + rng.uniform(-9, 9)))
                segs.append((x1, y1))
                pygame.draw.lines(surf, (80, 240, 210), False, segs, 4)
                pygame.draw.lines(surf, (230, 255, 250), False, segs, 2)
                self.add_glow(surf, x1, y1, (80, 240, 210), 16)
        for t in self.texts:
            self.blit_text(surf, t.text, t.size, t.color, shadow=True, center=(round(t.x), round(t.y)))

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------
    def _draw_low_hull(self, surf, game):
        ship = game.ship
        if ship.alive and ship.hull < 30 and int(self.time * 4) % 2 == 0:
            self.overlay.fill((0, 0, 0, 0))
            for i in range(6):
                pygame.draw.rect(self.overlay, (255, 30, 30, 50 - i * 8), self.overlay.get_rect().inflate(-i * 10, -i * 10), 5)
            surf.blit(self.overlay, (0, 0))

    def _bar(self, surf, x, y, w, h, frac, color, back=(30, 34, 60)):
        surf.fill(back, (x, y, w, h))
        surf.fill(color, (x, y, int(w * max(0.0, min(1.0, frac))), h))
        pygame.draw.rect(surf, PANEL_EDGE, (x - 1, y - 1, w + 2, h + 2), 1)

    def _draw_hud(self, surf, game):
        cfg = self.cfg
        pc = cfg.player
        top_h = cfg.display.hud_height
        width, height = self.width, self.height

        # Top bar: score, combo, level, high score
        surf.fill(PANEL, (0, 0, width, top_h))
        pygame.draw.line(surf, PANEL_EDGE, (0, top_h - 1), (width, top_h - 1))
        mid = top_h // 2
        r = self.blit_text(surf, f"{game.score:,}", 34, TEXT, midleft=(14, mid))
        if game.multiplier > 1:
            pulse = 30 + int(4 * math.sin(self.time * 10))
            self.blit_text(surf, f"x{game.multiplier}", pulse, PINK, midleft=(r.right + 10, mid))
        name = game.spec.name if game.spec else ""
        wave = f"   wave {game.wave}/{game.spec.waves}" if game.spec and not game.spec.is_boss and game.wave else ""
        self.blit_text(surf, f"LEVEL {game.level}  {name}{wave}", 26, YELLOW, center=(width // 2, mid))
        self.blit_text(surf, f"HI {max(game.high_score, game.score):,}", 24, DIM, midright=(width - 14, mid))

        # Boss bar under the top bar
        boss = game.boss
        if boss:
            left, total = boss.stage_hp()
            w = 360
            x0 = (width - w) // 2
            y0 = top_h + 6
            self.blit_text(surf, f"{boss.label.upper()}  STAGE {boss.stage}/{boss.stages}", 20, RED,
                           shadow=True, midright=(x0 - 10, y0 + 5))
            self._bar(surf, x0, y0, w, 10, left / total if total else 0, RED, (50, 15, 25))

        # Bottom bar
        bar_y = height - pc.bottom_margin + 6
        surf.fill(PANEL, (0, bar_y - 6, width, pc.bottom_margin))
        pygame.draw.line(surf, PANEL_EDGE, (0, bar_y - 6), (width, bar_y - 6))
        ship = game.ship

        # Hull + armor
        hull_frac = max(0.0, ship.hull) / pc.max_hull
        hull_color = GREEN if hull_frac > 0.5 else (YELLOW if hull_frac > 0.25 else RED)
        self.blit_text(surf, "HULL", 18, DIM, topleft=(12, bar_y))
        self._bar(surf, 50, bar_y + 1, 170, 12, hull_frac, hull_color)
        self.blit_text(surf, f"{max(0, round(ship.hull))}", 18, TEXT, midleft=(226, bar_y + 7))
        self.blit_text(surf, "ARMR", 18, DIM, topleft=(12, bar_y + 18))
        self._bar(surf, 50, bar_y + 19, 170, 8, ship.armor / pc.max_armor, STEEL)
        # Shield charges
        x = 262
        self.blit_text(surf, "SHLD", 18, DIM, topleft=(x, bar_y))
        for i in range(pc.max_shield):
            cx = x + 6 + i * 11
            color = CYAN if i < ship.shield else (40, 50, 80)
            pygame.draw.circle(surf, color, (cx, bar_y + 24), 4)
        # Lives
        self.blit_text(surf, "SHIPS", 18, DIM, topleft=(x + 118, bar_y))
        for i in range(game.lives):
            surf.blit(self.life_icon, (x + 118 + i * 18, bar_y + 14))

        # Weapon
        wx = 500
        if ship.weapon:
            spec = cfg.weapons[ship.weapon]
            icon = self.icons[ship.weapon]
            surf.blit(icon, icon.get_rect(midleft=(wx, bar_y + 14)))
            self.blit_text(surf, spec.label.upper(), 20, spec.color, topleft=(wx + 28, bar_y))
            if spec.ammo:
                frac, label = ship.ammo / spec.ammo, f"{ship.ammo}"
            else:
                frac, label = ship.weapon_time / spec.duration, f"{ship.weapon_time:0.1f}s"
            self._bar(surf, wx + 28, bar_y + 18, 110, 8, frac, spec.color)
            self.blit_text(surf, label, 18, TEXT, midleft=(wx + 144, bar_y + 22))
        else:
            self.blit_text(surf, "BLASTER", 20, DIM, topleft=(wx + 28, bar_y))
            self.blit_text(surf, "unlimited", 16, DIM, topleft=(wx + 28, bar_y + 18))

        # Shockwave
        sx = 690
        ready = game.shock_charge >= 1.0
        color = CYAN if ready else (80, 110, 160)
        self.blit_text(surf, "SHOCK [SHIFT]" if ready else "SHOCK", 18, color, topleft=(sx, bar_y))
        self._bar(surf, sx, bar_y + 18, 90, 8, game.shock_charge, color)
        if ready and int(self.time * 3) % 2 == 0:
            pygame.draw.rect(surf, CYAN, (sx - 3, bar_y + 15, 96, 14), 1)

        # Buffs
        bx = 800
        for kind in ("wingmen", "overdrive", "magnet"):
            left = ship.buffs.get(kind)
            if left is None:
                continue
            spec = cfg.pickups[kind]
            icon = self.icons[kind]
            surf.blit(icon, (bx, bar_y))
            self._bar(surf, bx, bar_y + 26, 22, 4, left / spec.duration, spec.color)
            self.blit_text(surf, f"{left:0.0f}", 16, spec.color, topleft=(bx + 24, bar_y + 4))
            bx += 50

    def _draw_banner(self, surf, game):
        cx, cy = self.width // 2, self.height // 2 - 60
        if self.banner:
            title, sub, color, left = self.banner
            if title == "WARNING" and int(self.time * 5) % 2:
                return
            self.blit_text(surf, title, 72, color, shadow=True, center=(cx, cy))
            if sub:
                self.blit_text(surf, sub, 32, TEXT, shadow=True, center=(cx, cy + 48))
            if self.hint and game.phase == "intro":
                self.blit_text(surf, self.hint, 26, DIM, shadow=True, center=(cx, cy + 86))

    def _dim(self, surf, alpha=160):
        self.overlay.fill((0, 0, 10, alpha))
        surf.blit(self.overlay, (0, 0))

    def _draw_pause(self, surf):
        self._dim(surf)
        cx, cy = self.width // 2, self.height // 2
        self.blit_text(surf, "PAUSED", 80, TEXT, center=(cx, cy - 30))
        self.blit_text(surf, "Press P or Esc to resume", 30, DIM, center=(cx, cy + 30))

    def _draw_game_over(self, surf, game):
        self._dim(surf, 175)
        cx, cy = self.width // 2, self.height // 2
        self.blit_text(surf, "GAME OVER", 90, RED, shadow=True, center=(cx, cy - 90))
        self.blit_text(surf, f"Score {game.score:,}", 46, TEXT, center=(cx, cy - 20))
        self.blit_text(surf, f"Reached level {game.level}   ·   {game.kills} ships destroyed",
                       28, DIM, center=(cx, cy + 24))
        if game.new_high_score:
            self.blit_text(surf, "NEW HIGH SCORE!", 34, YELLOW, center=(cx, cy + 64))
        self.blit_text(surf, "Press R (or click) to play again", 32, TEXT, center=(cx, cy + 110))

    def _draw_title(self, surf, game):
        cx = self.width // 2
        self.blit_text(surf, "ALIEN INVASION", 100, (120, 255, 160), shadow=True, center=(cx, 90))
        kinds = ["drone", "wasp", "striker", "lancer", "guardian", "dreadnought"]
        spacing = 140
        for i, kind in enumerate(kinds):
            x = cx - spacing * 2.5 + i * spacing
            img = self.enemy_imgs[kind][0]
            bob = 4 * math.sin(self.time * 2 + i)
            surf.blit(img, img.get_rect(center=(x, 185 + bob)))
            spec = self.cfg.enemies[kind]
            self.blit_text(surf, spec.label, 22, ENEMY_COLORS[kind], center=(x, 238))
            self.blit_text(surf, f"{spec.hp:g} HP", 18, DIM, center=(x, 256))
        lines = [
            "Move: Arrows / WASD     Shoot: Space (hold)     Shockwave: Shift     Pause: P / Esc",
            "Shoot wrecks for capsules. Hexagons are weapons, circles are upgrades.",
            "Bosses: hit the glowing weapons - the hull is armored.",
        ]
        for i, line in enumerate(lines):
            self.blit_text(surf, line, 24, DIM, center=(cx, 300 + i * 28))
        kinds = list(self.cfg.weapons) + list(self.cfg.pickups)
        per_row = 8
        for i, kind in enumerate(kinds):
            row, col = divmod(i, per_row)
            x = cx - 3.5 * 104 + col * 104
            y = 410 + row * 54
            icon = self.icons[kind]
            color = self._pickup_color(kind)
            if row == 0:
                pts = [(x + math.cos(a * math.tau / 6 + math.pi / 6) * 15, y + math.sin(a * math.tau / 6 + math.pi / 6) * 15)
                       for a in range(6)]
                pygame.draw.polygon(surf, color, pts, 2)
            else:
                pygame.draw.circle(surf, color, (x, y), 15, 2)
            surf.blit(icon, icon.get_rect(center=(x, y)))
            label = self.cfg.weapons[kind].label if kind in self.cfg.weapons else self.cfg.pickups[kind].label
            self.blit_text(surf, label, 17, color, center=(x, y + 24))
        if int(self.time * 2) % 2 == 0:
            self.blit_text(surf, "Press Space or Enter (or click) to start", 36, TEXT, center=(cx, 545))
        if game.high_score:
            self.blit_text(surf, f"High score {game.high_score:,}", 26, YELLOW, center=(cx, 590))
