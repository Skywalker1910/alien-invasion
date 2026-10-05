"""Menu state: main menu, pause menu and the help pages.

This only tracks which screen is open and which item is highlighted, and
turns key presses and clicks into actions. Drawing lives in render.py;
the App carries out the actions (start a run, resume, quit, ...).
"""
import pygame

MAIN = "main"
PAUSE = "pause"
HELP = "help"

HELP_PAGES = ("Basics", "Controls", "Enemies", "Bosses", "Weapons", "Upgrades")

UP_KEYS = (pygame.K_UP, pygame.K_w)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s)
LEFT_KEYS = (pygame.K_LEFT, pygame.K_a, pygame.K_q)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d, pygame.K_e, pygame.K_TAB)
OK_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
BACK_KEYS = (pygame.K_ESCAPE, pygame.K_BACKSPACE)


class Menu:
    def __init__(self, allow_quit=True):
        self.screen = MAIN            # MAIN, PAUSE, HELP, or None while playing
        self.back_to = MAIN           # where Help returns to
        self.index = 0                # highlighted item
        self.page = 0                 # help page
        self.allow_quit = allow_quit
        self.hitboxes = []            # (pygame.Rect, action), filled in by the renderer

    def items(self):
        if self.screen == MAIN:
            items = [("Play", "play"), ("Help", "help")]
        elif self.screen == PAUSE:
            items = [("Resume", "resume"), ("Help", "help"), ("Restart run", "restart"),
                     ("Main menu", "main_menu")]
        else:
            return []
        if self.allow_quit:
            items.append(("Quit", "quit"))
        return items

    def open(self, screen):
        self.screen = screen
        self.index = 0

    def open_help(self, page=0):
        if self.screen != HELP:
            self.back_to = self.screen or MAIN
        self.screen = HELP
        self.page = page

    def close_help(self):
        self.screen = self.back_to
        self.index = 0

    def turn_page(self, step):
        self.page = (self.page + step) % len(HELP_PAGES)

    def _do(self, action):
        """Handle actions that only change menu state; return the rest."""
        if action == "help":
            self.open_help()
            return None
        if action == "back":
            self.close_help()
            return None
        if action and action.startswith("page:"):
            self.page = int(action.split(":")[1])
            return None
        return action

    def key(self, key):
        """A key press while a menu is open. Returns an action or None."""
        if self.screen == HELP:
            if key in LEFT_KEYS:
                self.turn_page(-1)
            elif key in RIGHT_KEYS:
                self.turn_page(1)
            elif key in BACK_KEYS or key in OK_KEYS:
                self.close_help()
            return None
        items = self.items()
        if key in UP_KEYS:
            self.index = (self.index - 1) % len(items)
        elif key in DOWN_KEYS:
            self.index = (self.index + 1) % len(items)
        elif key in OK_KEYS:
            return self._do(items[self.index][1])
        elif key == pygame.K_h:
            self.open_help()
        elif self.screen == PAUSE and key in (pygame.K_ESCAPE, pygame.K_p):
            return "resume"
        return None

    def click(self, pos):
        for rect, action in self.hitboxes:
            if rect.collidepoint(pos):
                return self._do(action)
        return None

    def hover(self, pos):
        items = [a for _, a in self.items()]
        for rect, action in self.hitboxes:
            if rect.collidepoint(pos) and action in items:
                self.index = items.index(action)
