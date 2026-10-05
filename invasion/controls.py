"""Turns keyboard state and virtual (host / touch) input into InputState."""
import pygame

from .game import InputState

LEFT_KEYS = (pygame.K_LEFT, pygame.K_a)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d)
UP_KEYS = (pygame.K_UP, pygame.K_w)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s)
FIRE_KEYS = (pygame.K_SPACE,)
SPECIAL_KEYS = (pygame.K_LSHIFT, pygame.K_RSHIFT)
PREV_KEYS = (pygame.K_q,)
NEXT_KEYS = (pygame.K_e,)
ACTIVATE_KEYS = (pygame.K_f,)
# 1..9 then 0 select inventory slots 1..10 (index 0..9)
SLOT_KEYS = {key: i for i, key in enumerate(
    (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
     pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9, pygame.K_0))}
SLOT_KEYS.update({key: i for i, key in enumerate(
    (pygame.K_KP1, pygame.K_KP2, pygame.K_KP3, pygame.K_KP4, pygame.K_KP5,
     pygame.K_KP6, pygame.K_KP7, pygame.K_KP8, pygame.K_KP9, pygame.K_KP0))})


class Controls:
    def __init__(self):
        self.held = set()
        self.virtual = {"left": False, "right": False, "up": False, "down": False, "fire": False}
        self.special_pressed = False
        self.switch = 0
        self.select = -1
        self.activate = False

    def key_down(self, key):
        """Track a key press during play."""
        self.held.add(key)
        if key in SPECIAL_KEYS:
            self.special_pressed = True
        elif key in PREV_KEYS:
            self.switch = -1
        elif key in NEXT_KEYS:
            self.switch = 1
        elif key in ACTIVATE_KEYS:
            self.activate = True
        elif key in SLOT_KEYS:
            self.select = SLOT_KEYS[key]

    def key_up(self, key):
        self.held.discard(key)

    def set_virtual(self, **buttons):
        """Virtual buttons from the browser host, e.g. on-screen touch controls."""
        for name in self.virtual:
            if name in buttons:
                self.virtual[name] = bool(buttons[name])

    def press_special(self):
        self.special_pressed = True

    def press_switch(self, direction):
        self.switch = 1 if direction > 0 else -1

    def press_select(self, slot):
        self.select = slot

    def press_activate(self):
        self.activate = True

    def release_all(self):
        """Forget held keys, e.g. when the window loses focus."""
        self.held.clear()
        for name in self.virtual:
            self.virtual[name] = False

    def state(self):
        held = self.held
        return InputState(
            left=self.virtual["left"] or any(k in held for k in LEFT_KEYS),
            right=self.virtual["right"] or any(k in held for k in RIGHT_KEYS),
            up=self.virtual["up"] or any(k in held for k in UP_KEYS),
            down=self.virtual["down"] or any(k in held for k in DOWN_KEYS),
            fire=self.virtual["fire"] or any(k in held for k in FIRE_KEYS),
            special=self.special_pressed,
            switch=self.switch,
            select=self.select,
            activate=self.activate,
        )

    def consume_edges(self):
        self.special_pressed = False
        self.switch = 0
        self.select = -1
        self.activate = False
