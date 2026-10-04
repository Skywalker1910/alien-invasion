"""Turns keyboard state and virtual (host / touch) input into InputState."""
import pygame

from .game import InputState

LEFT_KEYS = (pygame.K_LEFT, pygame.K_a)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d)
FIRE_KEYS = (pygame.K_SPACE,)
SPECIAL_KEYS = (pygame.K_LSHIFT, pygame.K_RSHIFT)


class Controls:
    def __init__(self):
        self.held = set()
        self.virtual = {"left": False, "right": False, "fire": False}
        self.special_pressed = False

    def key_down(self, key):
        self.held.add(key)
        if key in SPECIAL_KEYS:
            self.special_pressed = True

    def key_up(self, key):
        self.held.discard(key)

    def set_virtual(self, **buttons):
        """Virtual buttons from the browser host, e.g. on-screen touch controls."""
        for name in self.virtual:
            if name in buttons:
                self.virtual[name] = bool(buttons[name])

    def press_special(self):
        self.special_pressed = True

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
            fire=self.virtual["fire"] or any(k in held for k in FIRE_KEYS),
            special=self.special_pressed,
        )

    def consume_edges(self):
        self.special_pressed = False
