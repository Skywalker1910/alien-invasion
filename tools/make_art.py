"""Draws all game sprites and saves them as PNGs in assets/images/.

    python tools/make_art.py

Everything is drawn with polygons at 4x size and scaled down for smooth
edges. Boss hulls read hardpoint positions from invasion/config.py so the
turret sockets on the art line up with the hitboxes in the game. Re-run
this after changing sizes or hardpoint offsets.
"""
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from invasion.config import Config  # noqa: E402
from invasion.entities import PART_SIZES  # noqa: E402

OUT = os.path.join(ROOT, "assets", "images")
SS = 4


def shade(color, k):
    return tuple(max(0, min(255, int(c * k))) for c in color[:3])


class Art:
    """A supersampled canvas using normalized (0..1) coordinates."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.surf = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA)

    def p(self, x, y):
        return (x * self.w * SS, y * self.h * SS)

    def poly(self, color, pts, width=0):
        pygame.draw.polygon(self.surf, color, [self.p(x, y) for x, y in pts], width * SS)

    def mpoly(self, color, half, width=0):
        """Polygon mirrored around x = 0.5 (give the right half, top to bottom)."""
        pts = list(half) + [(1 - x, y) for x, y in reversed(half)]
        self.poly(color, pts, width)

    def ellipse(self, color, x0, y0, x1, y1, width=0):
        r = pygame.Rect(*self.p(x0, y0), (x1 - x0) * self.w * SS, (y1 - y0) * self.h * SS)
        pygame.draw.ellipse(self.surf, color, r, width * SS)

    def circle(self, color, x, y, r, width=0):
        pygame.draw.circle(self.surf, color, self.p(x, y), r * SS, width * SS)

    def line(self, color, a, b, width=1):
        pygame.draw.line(self.surf, color, self.p(*a), self.p(*b), max(1, int(width * SS)))

    def rect(self, color, x0, y0, x1, y1, radius=0):
        r = pygame.Rect(*self.p(x0, y0), (x1 - x0) * self.w * SS, (y1 - y0) * self.h * SS)
        pygame.draw.rect(self.surf, color, r, border_radius=radius * SS)

    def glow(self, x, y, radius, color, strength=1.0):
        layer = pygame.Surface(self.surf.get_size(), pygame.SRCALPHA)
        cx, cy = self.p(x, y)
        steps = 10
        for i in range(steps, 0, -1):
            r = radius * SS * i / steps
            a = int(255 * strength * (1 - i / steps) ** 1.6)
            pygame.draw.circle(layer, color[:3] + (a,), (cx, cy), r)
        self.surf.blit(layer, (0, 0))

    def save(self, name):
        img = pygame.transform.smoothscale(self.surf, (self.w, self.h))
        pygame.image.save(img, os.path.join(OUT, name + ".png"))
        return img


# ----------------------------------------------------------------------
# Player and allies
# ----------------------------------------------------------------------
def player(cfg):
    a = Art(*cfg.player.size)
    base, light, dark = (70, 110, 210), (160, 200, 255), (30, 50, 110)
    a.glow(0.5, 0.95, 9, (255, 150, 60), 0.9)
    a.mpoly(dark, [(0.5, 0.02), (0.6, 0.3), (0.64, 0.55), (0.95, 0.78), (1.0, 0.93), (0.64, 0.86), (0.6, 0.98)])
    a.mpoly(base, [(0.5, 0.06), (0.58, 0.32), (0.61, 0.56), (0.9, 0.78), (0.94, 0.88), (0.6, 0.82), (0.56, 0.93)])
    a.mpoly(light, [(0.5, 0.1), (0.54, 0.34), (0.55, 0.7), (0.5, 0.8)])
    a.mpoly((230, 70, 80), [(0.88, 0.76), (0.98, 0.9), (0.93, 0.92)])
    a.ellipse((20, 30, 60), 0.42, 0.28, 0.58, 0.5)
    a.ellipse((110, 230, 255), 0.44, 0.3, 0.56, 0.46)
    a.ellipse((230, 250, 255), 0.47, 0.32, 0.51, 0.38)
    a.rect((40, 50, 80), 0.45, 0.86, 0.55, 0.97, 2)
    return a.save("player")


def wingman():
    a = Art(22, 22)
    a.glow(0.5, 0.9, 5, (120, 220, 255), 0.8)
    a.mpoly((40, 120, 140), [(0.5, 0.05), (0.75, 0.5), (1.0, 0.8), (0.6, 0.75), (0.55, 0.95)])
    a.mpoly((90, 240, 210), [(0.5, 0.15), (0.65, 0.5), (0.85, 0.72), (0.55, 0.68)])
    a.circle((230, 255, 250), 0.5, 0.45, 2)
    return a.save("wingman")


# ----------------------------------------------------------------------
# Enemies (they face down: the nose is at the bottom)
# ----------------------------------------------------------------------
def drone(size):
    a = Art(*size)
    body, light = (40, 170, 110), (120, 255, 170)
    a.mpoly(shade(body, 0.6), [(0.5, 0.3), (0.98, 0.45), (0.82, 0.8), (0.6, 0.72)])
    a.ellipse(shade(body, 0.7), 0.12, 0.18, 0.88, 0.78)
    a.ellipse(body, 0.16, 0.2, 0.84, 0.66)
    a.ellipse(light, 0.3, 0.16, 0.7, 0.42)
    a.ellipse((20, 40, 30), 0.38, 0.5, 0.62, 0.8)
    a.glow(0.5, 0.66, 6, (255, 70, 60), 1.0)
    a.circle((255, 220, 200), 0.5, 0.66, 1.5)
    for x in (0.25, 0.75):
        a.circle((200, 255, 210), x, 0.42, 1.2)
    return a.save("enemy_drone")


def wasp(size):
    a = Art(*size)
    a.ellipse((180, 230, 255, 110), -0.05, 0.1, 0.48, 0.5)
    a.ellipse((180, 230, 255, 110), 0.52, 0.1, 1.05, 0.5)
    a.ellipse((180, 230, 255, 180), -0.05, 0.1, 0.48, 0.5, 1)
    a.ellipse((180, 230, 255, 180), 0.52, 0.1, 1.05, 0.5, 1)
    a.ellipse((40, 30, 10), 0.28, 0.0, 0.72, 0.42)
    a.ellipse((250, 200, 40), 0.3, 0.3, 0.7, 0.86)
    for y in (0.42, 0.56, 0.7):
        a.rect((30, 25, 10), 0.3, y, 0.7, y + 0.06)
    a.mpoly((40, 30, 10), [(0.5, 1.0), (0.56, 0.8), (0.6, 0.76)])
    a.circle((255, 60, 40), 0.4, 0.2, 2)
    a.circle((255, 60, 40), 0.6, 0.2, 2)
    return a.save("enemy_wasp")


def striker(size):
    a = Art(*size)
    body, light = (40, 140, 180), (130, 220, 250)
    a.glow(0.5, 0.06, 8, (90, 200, 255), 0.7)
    a.mpoly(shade(body, 0.55), [(0.5, 0.0), (0.66, 0.12), (1.0, 0.2), (0.86, 0.5), (0.62, 0.66), (0.54, 1.0)])
    a.mpoly(body, [(0.5, 0.06), (0.64, 0.18), (0.92, 0.24), (0.8, 0.46), (0.6, 0.6), (0.52, 0.9)])
    a.mpoly(light, [(0.5, 0.12), (0.58, 0.3), (0.55, 0.6), (0.5, 0.75)])
    for x in (0.3, 0.7):
        a.rect((30, 40, 60), x - 0.04, 0.45, x + 0.04, 0.95, 1)
        a.circle((255, 120, 220), x, 0.94, 1.5)
    a.ellipse((255, 90, 200), 0.44, 0.3, 0.56, 0.48)
    return a.save("enemy_striker")


def lancer(size):
    a = Art(*size)
    body = (220, 120, 40)
    a.glow(0.5, 0.05, 9, (255, 170, 80), 0.6)
    a.mpoly(shade(body, 0.5), [(0.5, 0.0), (0.8, 0.1), (1.0, 0.35), (0.75, 0.5), (0.58, 0.45)])
    a.mpoly(body, [(0.5, 0.04), (0.76, 0.13), (0.92, 0.33), (0.72, 0.45), (0.56, 0.4)])
    a.rect((90, 70, 70), 0.43, 0.25, 0.57, 0.92, 2)
    a.rect((200, 190, 190), 0.47, 0.28, 0.53, 0.9, 1)
    for y in (0.5, 0.62, 0.74):
        a.rect((255, 150, 60), 0.4, y, 0.6, y + 0.04)
    a.glow(0.5, 0.93, 10, (255, 60, 60), 1.0)
    a.circle((255, 230, 200), 0.5, 0.93, 2)
    a.ellipse((255, 230, 120), 0.42, 0.12, 0.58, 0.24)
    return a.save("enemy_lancer")


def guardian(size):
    a = Art(*size)
    body, light = (110, 60, 170), (190, 140, 255)
    a.mpoly(shade(body, 0.45), [(0.5, 0.0), (0.82, 0.05), (1.0, 0.42), (0.86, 0.86), (0.6, 1.0)])
    a.mpoly(body, [(0.5, 0.05), (0.78, 0.1), (0.94, 0.42), (0.82, 0.8), (0.58, 0.93)])
    a.mpoly(light, [(0.5, 0.12), (0.66, 0.2), (0.72, 0.42), (0.62, 0.62), (0.5, 0.66)])
    for x in (0.18, 0.82):
        a.poly(shade(light, 0.8), [(x - 0.08, 0.35), (x + 0.08, 0.35), (x + 0.05, 0.6), (x - 0.05, 0.6)])
    a.line(shade(body, 0.5), (0.3, 0.5), (0.7, 0.5), 1)
    for x in (0.35, 0.5, 0.65):
        a.rect((40, 20, 60), x - 0.04, 0.78, x + 0.04, 0.97, 1)
        a.circle((255, 120, 255), x, 0.96, 1.6)
    a.glow(0.5, 0.4, 12, (220, 160, 255), 0.7)
    a.circle((250, 230, 255), 0.5, 0.4, 3)
    return a.save("enemy_guardian")


def dreadnought(size):
    a = Art(*size)
    body, dark, light = (170, 40, 50), (70, 15, 25), (240, 110, 110)
    for x in (0.3, 0.5, 0.7):
        a.glow(x, 0.04, 12, (255, 120, 80), 0.8)
    a.mpoly(dark, [(0.5, 0.02), (0.75, 0.04), (0.98, 0.3), (1.0, 0.58), (0.78, 0.8), (0.62, 0.98)])
    a.mpoly(body, [(0.5, 0.06), (0.72, 0.08), (0.93, 0.3), (0.94, 0.55), (0.75, 0.75), (0.58, 0.92)])
    a.mpoly(shade(body, 1.2), [(0.5, 0.1), (0.62, 0.14), (0.68, 0.5), (0.56, 0.8)])
    for y in (0.3, 0.45, 0.6):
        a.line(dark, (0.12, y), (0.88, y), 1)
    for x in (0.2, 0.8):
        a.rect((40, 10, 15), x - 0.06, 0.35, x + 0.06, 0.62, 2)
        for y in (0.4, 0.48, 0.56):
            a.circle((255, 200, 120), x, y, 1.6)
    a.ellipse((40, 10, 20), 0.42, 0.2, 0.58, 0.36)
    a.ellipse((255, 160, 140), 0.45, 0.23, 0.55, 0.32)
    a.glow(0.5, 0.92, 9, (255, 80, 60), 0.9)
    return a.save("enemy_dreadnought")


def cargo(size):
    a = Art(*size)
    a.glow(0.04, 0.5, 8, (120, 220, 255), 0.8)
    a.glow(0.96, 0.5, 8, (120, 220, 255), 0.8)
    a.rect((80, 85, 95), 0.08, 0.1, 0.92, 0.9, 4)
    a.rect((140, 145, 155), 0.12, 0.16, 0.88, 0.84, 3)
    for i in range(7):
        x = 0.16 + i * 0.1
        a.poly((250, 200, 40), [(x, 0.62), (x + 0.05, 0.62), (x + 0.1, 0.8), (x + 0.05, 0.8)])
    a.rect((60, 60, 70), 0.14, 0.3, 0.86, 0.36)
    a.glow(0.5, 0.18, 6, (120, 255, 140), 1.0)
    return a.save("enemy_cargo")


def mine(size):
    a = Art(*size)
    for i in range(8):
        ang = i * math.tau / 8
        x, y = 0.5 + math.cos(ang) * 0.46, 0.5 + math.sin(ang) * 0.46
        a.line((120, 120, 130), (0.5, 0.5), (x, y), 2)
        a.circle((200, 200, 210), x, y, 1.5)
    a.circle((70, 30, 35), 0.5, 0.5, size[0] * 0.3)
    a.circle((140, 50, 60), 0.46, 0.46, size[0] * 0.2)
    a.circle((255, 80, 80), 0.5, 0.5, 2.5)
    return a.save("enemy_mine")


def asteroid(size):
    rng = random.Random(7)
    a = Art(*size)
    pts = []
    for i in range(11):
        ang = i * math.tau / 11
        r = 0.42 + rng.uniform(-0.07, 0.06)
        pts.append((0.5 + math.cos(ang) * r, 0.5 + math.sin(ang) * r))
    a.poly((70, 60, 55), pts)
    a.poly((120, 105, 90), [(0.5 + (x - 0.5) * 0.88 - 0.03, 0.5 + (y - 0.5) * 0.88 - 0.03) for x, y in pts])
    for _ in range(5):
        cx, cy, r = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7), rng.uniform(2, 4.5)
        a.circle((85, 72, 62), cx, cy, r)
        a.circle((140, 125, 110), cx - 0.02, cy - 0.02, r * 0.5)
    return a.save("enemy_asteroid")


# ----------------------------------------------------------------------
# Bosses and their weapons
# ----------------------------------------------------------------------
BOSS_STYLE = [
    ((150, 30, 45), (60, 10, 20), (255, 110, 90)),     # Harbinger: crimson
    ((90, 45, 150), (35, 15, 70), (200, 140, 255)),    # Leviathan: violet
    ((150, 110, 40), (45, 35, 20), (255, 215, 110)),   # Overmind: gold
]


def boss(index, spec):
    w, h = spec.size
    a = Art(w, h)
    body, dark, accent = BOSS_STYLE[index]
    mid = shade(body, 0.75)

    # Engine glow along the top edge (the ship faces down at the player).
    for i in range(6 + index * 2):
        a.glow(0.12 + i * 0.76 / (5 + index * 2), 0.03, 18, shade(accent, 0.9), 0.55)

    # Main hull: a wide upper deck tapering to a prow.
    if index == 0:
        outline = [(0.5, 0.0), (0.78, 0.0), (0.98, 0.16), (1.0, 0.42), (0.84, 0.5), (0.66, 0.64),
                   (0.58, 0.9), (0.5, 0.98)]
    elif index == 1:
        outline = [(0.5, 0.0), (0.84, 0.0), (1.0, 0.18), (0.98, 0.4), (0.78, 0.48), (0.64, 0.7),
                   (0.56, 0.9), (0.5, 0.96)]
    else:
        outline = [(0.5, 0.0), (0.92, 0.0), (1.0, 0.16), (0.98, 0.38), (0.8, 0.46), (0.68, 0.62),
                   (0.58, 0.84), (0.5, 0.94)]

    # Armored pods with struts carry every hardpoint, so no weapon floats.
    pods = []
    for hp in spec.hardpoints:
        pw, ph = PART_SIZES[hp.kind]
        cx = 0.5 + hp.offset[0] / w
        cy = 0.5 + hp.offset[1] / h
        rx, ry = pw * 0.85 / w, ph * 0.85 / h
        pods.append((cx, cy, rx, ry, hp.kind))
        a.line(dark, (cx, cy), (0.5 + (cx - 0.5) * 0.6, 0.22), 7)
        a.line(mid, (cx, cy), (0.5 + (cx - 0.5) * 0.6, 0.22), 4)

    a.mpoly(dark, outline)
    a.mpoly(body, [(0.5 + (x - 0.5) * 0.95, 0.02 + y * 0.93) for x, y in outline])
    # Shading bands: darker toward the top, lit toward the prow.
    for i in range(6):
        y0 = i / 6 * 0.6
        layer = Art(w, h)
        layer.rect(shade(dark, 1.0) + (int(70 - i * 12),), 0.0, y0, 1.0, y0 + 0.1)
        layer.surf.blit(a.surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        a.surf.blit(layer.surf, (0, 0))

    # Raised spine with windows.
    a.mpoly(shade(body, 1.3), [(0.5, 0.04), (0.56, 0.06), (0.6, 0.4), (0.55, 0.75), (0.5, 0.85)])
    a.mpoly(shade(body, 1.55), [(0.5, 0.08), (0.53, 0.1), (0.55, 0.4), (0.5, 0.7)])
    for i in range(6):
        y = 0.12 + i * 0.08
        a.circle(accent, 0.5, y, 1.6)

    # Bevelled panel lines.
    for i in range(1, 5):
        y = i * 0.1
        a.line(dark, (0.08, y), (0.92, y), 1)
        a.line(shade(body, 1.35), (0.08, y + 0.008), (0.92, y + 0.008), 0.5)
    for x in (0.2, 0.32, 0.68, 0.8):
        a.line(dark, (x, 0.04), (x, 0.42), 1)

    # Signature details.
    if index == 0:  # Harbinger: swept horns
        for side in (-1, 1):
            a.poly(dark, [(0.5 + side * 0.44, 0.1), (0.5 + side * 0.53, 0.0), (0.5 + side * 0.5, 0.3)])
            a.poly(accent, [(0.5 + side * 0.45, 0.12), (0.5 + side * 0.51, 0.04), (0.5 + side * 0.49, 0.24)])
    elif index == 1:  # Leviathan: ribbed fins
        for side in (-1, 1):
            for i in range(4):
                x = 0.5 + side * (0.24 + i * 0.06)
                a.line(shade(accent, 0.7), (x, 0.06), (x + side * 0.03, 0.4), 2)
    else:  # Overmind: towers and a great eye around the core
        for side in (-1, 1):
            for i in range(3):
                x = 0.5 + side * (0.3 + i * 0.07)
                a.rect(dark, x - 0.012, 0.0, x + 0.012, 0.2)
                a.circle(accent, x, 0.02, 2)
        a.ellipse(shade(accent, 0.5), 0.36, 0.5, 0.64, 1.0, 3)

    # Pods and sockets on top of the hull.
    for cx, cy, rx, ry, kind in pods:
        a.ellipse(dark, cx - rx, cy - ry, cx + rx, cy + ry * 1.1)
        a.ellipse(mid, cx - rx * 0.88, cy - ry * 0.85, cx + rx * 0.88, cy + ry * 0.95)
        a.ellipse(shade(accent, 0.6), cx - rx * 0.88, cy - ry * 0.85, cx + rx * 0.88, cy + ry * 0.95, 1)
        a.ellipse((14, 10, 16), cx - rx * 0.66, cy - ry * 0.62, cx + rx * 0.66, cy + ry * 0.72)
    return a.save(f"boss_{index + 1}")


def part(kind):
    w, h = PART_SIZES[kind]
    a = Art(w, h)
    metal, dark, glow = (150, 150, 165), (55, 55, 70), (255, 90, 80)
    if kind == "cannon":
        a.circle(dark, 0.5, 0.4, w * 0.4)
        a.circle(metal, 0.5, 0.4, w * 0.32)
        a.rect(dark, 0.4, 0.4, 0.6, 1.0, 1)
        a.rect(metal, 0.44, 0.45, 0.56, 0.98, 1)
        a.circle(glow, 0.5, 0.4, 3)
    elif kind == "spread":
        a.ellipse(dark, 0.05, 0.05, 0.95, 0.75)
        a.ellipse(metal, 0.12, 0.1, 0.88, 0.66)
        for ang in (-28, 0, 28):
            r = math.radians(ang)
            a.line(dark, (0.5, 0.4), (0.5 + math.sin(r) * 0.45, 0.4 + math.cos(r) * 0.58), 4)
        a.circle((255, 200, 80), 0.5, 0.38, 3)
    elif kind == "missile":
        a.rect(dark, 0.05, 0.08, 0.95, 0.95, 3)
        a.rect(metal, 0.1, 0.13, 0.9, 0.88, 2)
        for x in (0.28, 0.5, 0.72):
            a.circle((30, 30, 40), x, 0.65, 4)
            a.circle((255, 120, 60), x, 0.65, 1.6)
    elif kind == "laser":
        a.mpoly(dark, [(0.5, 0.0), (0.95, 0.15), (0.8, 0.7), (0.56, 1.0)])
        a.mpoly(metal, [(0.5, 0.05), (0.88, 0.18), (0.74, 0.66), (0.54, 0.92)])
        a.glow(0.5, 0.78, 10, (255, 60, 160), 1.0)
        a.circle((255, 220, 240), 0.5, 0.78, 2.5)
    elif kind == "hangar":
        a.rect(dark, 0.0, 0.1, 1.0, 0.95, 4)
        a.rect((25, 25, 35), 0.12, 0.3, 0.88, 0.85, 2)
        for i in range(5):
            a.line((80, 80, 100), (0.15 + i * 0.175, 0.32), (0.15 + i * 0.175, 0.83), 1)
        for x in (0.06, 0.94):
            a.circle((120, 255, 140), x, 0.5, 2)
    elif kind == "core":
        a.mpoly(dark, [(0.5, 0.0), (0.9, 0.1), (1.0, 0.5), (0.9, 0.9), (0.5, 1.0)])
        a.glow(0.5, 0.5, 26, (255, 240, 160), 0.9)
        a.circle((255, 200, 90), 0.5, 0.5, 12)
        a.circle((255, 255, 230), 0.5, 0.5, 6)
        a.mpoly(metal, [(0.5, 0.0), (0.9, 0.1), (1.0, 0.5), (0.9, 0.9), (0.5, 1.0)], 2)
    return a.save(f"part_{kind}")


# ----------------------------------------------------------------------
# Pickup icons (drawn inside a capsule by the renderer)
# ----------------------------------------------------------------------
def icon(kind, color):
    a = Art(22, 22)
    c, white = color, (255, 255, 255)
    if kind == "spread":
        for ang in (-34, 0, 34):
            r = math.radians(ang)
            tip = (0.5 + math.sin(r) * 0.4, 0.9 - math.cos(r) * 0.62)
            a.line(shade(c, 0.6), (0.5, 0.9), tip, 1)
            a.circle(c, tip[0], tip[1], 2.6)
            a.circle(white, tip[0], tip[1], 1.1)
    elif kind == "rapid":
        for x in (0.28, 0.5, 0.72):
            a.rect(c, x - 0.06, 0.15, x + 0.06, 0.85, 1)
    elif kind == "rail":
        a.rect(c, 0.42, 0.25, 0.58, 0.95)
        a.poly(white, [(0.5, 0.0), (0.72, 0.3), (0.28, 0.3)])
    elif kind == "laser":
        a.glow(0.5, 0.5, 8, c, 1.0)
        a.rect(white, 0.44, 0.0, 0.56, 1.0)
    elif kind == "homing":
        a.line(c, (0.15, 0.95), (0.45, 0.45), 2)
        a.poly(white, [(0.82, 0.08), (0.62, 0.55), (0.42, 0.38)])
    elif kind == "plasma":
        a.circle(c, 0.5, 0.5, 8, 2)
        a.circle(white, 0.5, 0.5, 4.5)
    elif kind == "chain":
        a.poly(c, [(0.62, 0.0), (0.22, 0.55), (0.48, 0.55), (0.34, 1.0), (0.8, 0.4), (0.54, 0.4)])
    elif kind == "flak":
        for i in range(8):
            r = i * math.tau / 8
            a.line(c, (0.5, 0.5), (0.5 + math.cos(r) * 0.45, 0.5 + math.sin(r) * 0.45), 2)
        a.circle(white, 0.5, 0.5, 3)
    elif kind == "repair":
        a.rect(c, 0.38, 0.1, 0.62, 0.9, 1)
        a.rect(c, 0.1, 0.38, 0.9, 0.62, 1)
    elif kind == "shield":
        a.poly(c, [(0.5, 0.05), (0.9, 0.2), (0.82, 0.6), (0.5, 0.95), (0.18, 0.6), (0.1, 0.2)])
        a.poly(white, [(0.5, 0.2), (0.72, 0.3), (0.66, 0.56), (0.5, 0.75)])
    elif kind == "armor":
        pts = [(0.5 + math.cos(i * math.tau / 6) * 0.42, 0.5 + math.sin(i * math.tau / 6) * 0.42)
               for i in range(6)]
        a.poly(c, pts)
        a.poly(shade(c, 0.6), pts, 2)
    elif kind == "shock":
        for r in (9, 6, 3):
            a.circle(c, 0.5, 0.5, r, 2 if r > 3 else 0)
    elif kind == "wingmen":
        for x, y in ((0.5, 0.2), (0.2, 0.7), (0.8, 0.7)):
            a.poly(c, [(x, y - 0.18), (x + 0.14, y + 0.15), (x - 0.14, y + 0.15)])
    elif kind == "overdrive":
        for y in (0.15, 0.5):
            a.poly(c, [(0.5, y), (0.9, y + 0.35), (0.72, y + 0.35), (0.5, y + 0.15), (0.28, y + 0.35),
                       (0.1, y + 0.35)])
    elif kind == "magnet":
        a.rect(c, 0.15, 0.1, 0.35, 0.65)
        a.rect(c, 0.65, 0.1, 0.85, 0.65)
        a.ellipse(c, 0.15, 0.45, 0.85, 0.95)
        a.ellipse((0, 0, 0, 0), 0.35, 0.4, 0.65, 0.75)
        a.rect(white, 0.15, 0.1, 0.35, 0.25)
        a.rect(white, 0.65, 0.1, 0.85, 0.25)
    elif kind == "life":
        a.mpoly(c, [(0.5, 0.05), (0.62, 0.45), (0.95, 0.85), (0.6, 0.78), (0.56, 0.95)])
    return a.save(f"icon_{kind}")


def heart():
    a = Art(18, 16)
    color, light = (255, 70, 100), (255, 170, 185)
    a.circle(color, 0.3, 0.32, 4.6)
    a.circle(color, 0.7, 0.32, 4.6)
    a.poly(color, [(0.05, 0.42), (0.95, 0.42), (0.5, 0.98)])
    a.circle(light, 0.26, 0.26, 1.5)
    return a.save("icon_health")


def unknown_flag():
    a = Art(40, 27)
    a.rect((70, 80, 110), 0.0, 0.0, 1.0, 1.0)
    a.rect((110, 120, 150), 0.06, 0.08, 0.94, 0.92)
    a.circle((230, 235, 255), 0.5, 0.5, 6, 2)
    return a.save("flag_unknown")


ORANGE_BB = (240, 128, 40)


def _mask_circle(art, cx=0.5, cy=0.5, r=0.5):
    """Keep only what lies inside a circle (normalized units)."""
    mask = pygame.Surface(art.surf.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), art.p(cx, cy), r * art.w * SS)
    art.surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)


def orbi():
    """Orbi, the co-pilot droid: a white rolling ball with orange ring panels
    and a domed head, matching the portfolio's co-pilot assistant. Three
    sprites: the body pattern (rotated at runtime so it rolls), a fixed
    shading overlay, and the head (kept upright on top)."""
    # Body pattern
    a = Art(80, 80)
    white, grey, orange = (244, 244, 248), (175, 178, 190), ORANGE_BB
    a.circle(white, 0.5, 0.5, 40)
    # Side panels, partly wrapping round the ball
    for cx, cy in ((0.02, 0.18), (1.0, 0.2), (0.06, 0.98), (0.98, 0.94)):
        a.circle(orange, cx, cy, 15, 3)
        a.circle(grey, cx, cy, 8, 1)
    for (x0, y0), (x1, y1) in (((0.16, 0.42), (0.3, 0.28)), ((0.7, 0.28), (0.84, 0.42)),
                               ((0.18, 0.74), (0.3, 0.86)), ((0.7, 0.86), (0.82, 0.74))):
        a.line(orange, (x0, y0), (x1, y1), 2.2)
    for y in (0.12, 0.88):
        a.line(grey, (0.38, y), (0.62, y), 1)
    # Main panel: orange ring, white gap, inner orange ring with spokes
    a.circle(orange, 0.5, 0.52, 23)
    a.circle(white, 0.5, 0.52, 18.5)
    a.circle(orange, 0.5, 0.52, 12)
    a.circle(white, 0.5, 0.52, 8)
    for k in range(4):
        ang = math.pi / 4 + k * math.pi / 2
        a.line(orange, (0.5 + math.cos(ang) * 0.1, 0.52 + math.sin(ang) * 0.1),
               (0.5 + math.cos(ang) * 0.24, 0.52 + math.sin(ang) * 0.24), 2.6)
    a.circle(grey, 0.5, 0.52, 3.2)
    _mask_circle(a)
    a.circle((205, 208, 218), 0.5, 0.5, 40, 1)
    a.save("orbi_body")

    # Fixed shading: a soft shadow crescent bottom-right and a highlight
    s = Art(80, 80)
    s.circle((70, 74, 96, 95), 0.5, 0.5, 40)
    s.circle((0, 0, 0, 0), 0.42, 0.4, 37)
    s.ellipse((255, 255, 255, 110), 0.2, 0.12, 0.5, 0.34)
    _mask_circle(s)
    s.save("orbi_shade")

    # Head: white dome, orange band, dark bottom rim, big lens + small lens
    h = Art(54, 34)
    h.ellipse(white, 0.02, 0.04, 0.98, 1.9)
    h.rect(orange, 0.0, 0.46, 1.0, 0.56)
    for x in (0.22, 0.34, 0.46, 0.58, 0.7, 0.82):
        h.circle((255, 220, 170), x, 0.51, 1.3)
    h.rect(grey, 0.0, 0.7, 1.0, 0.78)
    h.rect((95, 98, 112), 0.0, 0.78, 1.0, 1.0)
    h.rect((0, 0, 0, 0), 0.0, 0.92, 1.0, 1.0)
    mask = pygame.Surface(h.surf.get_size(), pygame.SRCALPHA)
    pygame.draw.ellipse(mask, (255, 255, 255, 255), pygame.Rect(*h.p(0.02, 0.04), 0.96 * h.w * SS, 1.86 * h.h * SS))
    h.surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    h.circle((40, 42, 52), 0.4, 0.34, 6.2)
    h.circle((15, 16, 22), 0.4, 0.34, 4.6)
    h.circle((120, 125, 140), 0.4, 0.34, 4.6, 1)
    h.circle((230, 235, 255), 0.37, 0.29, 1.4)
    h.circle((30, 32, 40), 0.64, 0.38, 2.4)
    h.ellipse((255, 255, 255, 120), 0.18, 0.08, 0.52, 0.22)
    h.save("orbi_head")


def main():
    pygame.init()
    heart()
    unknown_flag()
    orbi()
    os.makedirs(OUT, exist_ok=True)
    cfg = Config()
    player(cfg)
    wingman()
    makers = {"drone": drone, "wasp": wasp, "striker": striker, "lancer": lancer,
              "guardian": guardian, "dreadnought": dreadnought, "cargo": cargo, "mine": mine,
              "asteroid": asteroid}
    for kind, maker in makers.items():
        maker(cfg.enemies[kind].size)
    for index, spec in enumerate(cfg.bosses):
        boss(index, spec)
    for kind in PART_SIZES:
        part(kind)
    for kind, spec in cfg.weapons.items():
        icon(kind, spec.color)
    for kind, spec in cfg.pickups.items():
        icon(kind, spec.color)
    print("sprites written to", OUT)


if __name__ == "__main__":
    main()
