"""Menu state: main menu, pause menu, help, pilot entry and leaderboard.

This only tracks which screen is open and what is highlighted, and turns
key presses and clicks into actions. Drawing lives in render.py; the App
carries out the actions (start a run, save a score, quit, ...).
"""
import pygame

from .storage import NAME_MAX

MAIN = "main"
PAUSE = "pause"
HELP = "help"
ENTRY = "entry"          # pilot name + country after a run
BOARD = "board"          # leaderboard

HELP_PAGES = ("Story", "Basics", "Controls", "Enemies", "Bosses", "Weapons", "Upgrades")

UP_KEYS = (pygame.K_UP, pygame.K_w)
DOWN_KEYS = (pygame.K_DOWN, pygame.K_s)
LEFT_KEYS = (pygame.K_LEFT, pygame.K_a, pygame.K_q)
RIGHT_KEYS = (pygame.K_RIGHT, pygame.K_d, pygame.K_e, pygame.K_TAB)
OK_KEYS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE)
BACK_KEYS = (pygame.K_ESCAPE, pygame.K_BACKSPACE)
LIST_ROWS = 8


class EntryForm:
    """Pilot name + country picker shown after a run that scored."""

    def __init__(self, countries, name="", country=""):
        self.countries = countries          # [{"code": "in", "name": "India"}, ...]
        self.name = name[:NAME_MAX]
        self.country = country
        self.field = "name"                 # "name" or "country"
        self.query = ""                     # type-to-filter for the country list
        self.cursor = 0
        self.scroll = 0
        self._jump_to(country)

    def filtered(self):
        q = self.query.lower()
        if not q:
            return self.countries
        # Exact code first, then names starting with the text, then the rest.
        matches = [c for c in self.countries if q in c["name"].lower() or c["code"] == q]
        return sorted(matches, key=lambda c: (c["code"] != q, not c["name"].lower().startswith(q)))

    def _jump_to(self, code):
        for i, c in enumerate(self.filtered()):
            if c["code"] == code:
                self.cursor = i
                self.scroll = max(0, i - LIST_ROWS // 2)
                return

    def _move(self, step):
        count = len(self.filtered())
        if not count:
            return
        self.cursor = max(0, min(count - 1, self.cursor + step))
        if self.cursor < self.scroll:
            self.scroll = self.cursor
        elif self.cursor >= self.scroll + LIST_ROWS:
            self.scroll = self.cursor - LIST_ROWS + 1

    def scroll_by(self, step):
        self._move(step)

    def choose(self, code):
        self.country = code
        self._jump_to(code)

    def key(self, event):
        """Returns "save", "skip" or None."""
        key = event.key
        if key == pygame.K_ESCAPE:
            return "skip"
        if key == pygame.K_TAB:
            self.field = "country" if self.field == "name" else "name"
            return None
        if self.field == "name":
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_DOWN):
                self.field = "country"
            elif key == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
            elif event.unicode and event.unicode.isprintable() and len(self.name) < NAME_MAX:
                self.name += event.unicode
            return None
        # country field
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            options = self.filtered()
            if options:
                self.country = options[self.cursor]["code"]
            return "save"
        if key == pygame.K_UP:
            if self.cursor == 0:
                self.field = "name"
            self._move(-1)
        elif key == pygame.K_DOWN:
            self._move(1)
        elif key == pygame.K_PAGEUP:
            self._move(-LIST_ROWS)
        elif key == pygame.K_PAGEDOWN:
            self._move(LIST_ROWS)
        elif key == pygame.K_BACKSPACE:
            self.query = self.query[:-1]
            self.cursor = self.scroll = 0
        elif event.unicode and event.unicode.isprintable():
            self.query += event.unicode
            self.cursor = self.scroll = 0
        return None


class Menu:
    def __init__(self, allow_quit=True):
        self.screen = MAIN            # one of the screens above, or None while playing
        self.back_to = MAIN           # where Help / Leaderboard return to
        self.index = 0                # highlighted item
        self.page = 0                 # help page
        self.allow_quit = allow_quit
        self.hitboxes = []            # (pygame.Rect, action), filled in by the renderer
        self.form = None              # EntryForm while ENTRY is open
        self.board = []               # leaderboard rows to show
        self.highlight = None         # id of the entry just saved
        self.after_run = False        # leaderboard reached from game over

    def items(self):
        if self.screen == MAIN:
            items = [("Play", "play"), ("Leaderboard", "leaderboard"), ("Tutorial", "tutorial"),
                     ("Help", "help")]
        elif self.screen == PAUSE:
            items = [("Resume", "resume"), ("Help", "help"), ("Restart run", "restart"),
                     ("Main menu", "main_menu")]
        elif self.screen == BOARD:
            return ([("Play again", "play"), ("Main menu", "main_menu")] if self.after_run
                    else [("Back", "back")])
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

    def open_entry(self, form):
        self.form = form
        self.open(ENTRY)

    def open_board(self, rows, highlight=None, after_run=False):
        if self.screen not in (BOARD, ENTRY):
            self.back_to = self.screen or MAIN
        self.board = rows
        self.highlight = highlight
        self.after_run = after_run
        self.form = None
        self.open(BOARD)

    def go_back(self):
        self.screen = self.back_to if self.back_to not in (HELP, BOARD, ENTRY) else MAIN
        self.index = 0

    def turn_page(self, step):
        self.page = (self.page + step) % len(HELP_PAGES)

    def _do(self, action):
        """Handle actions that only change menu state; return the rest."""
        if action == "help":
            self.open_help()
            return None
        if action == "back":
            self.go_back()
            return None
        if action and action.startswith("page:"):
            self.page = int(action.split(":")[1])
            return None
        if action and action.startswith("field:") and self.form:
            self.form.field = action.split(":")[1]
            return None
        if action and action.startswith("country:") and self.form:
            self.form.field = "country"
            self.form.choose(action.split(":")[1])
            return None
        return action

    def key_event(self, event):
        """A key press while a menu is open. Returns an action or None."""
        key = event.key
        if self.screen == ENTRY:
            return self.form.key(event) if self.form else None
        if self.screen == HELP:
            if key in LEFT_KEYS:
                self.turn_page(-1)
            elif key in RIGHT_KEYS:
                self.turn_page(1)
            elif key in BACK_KEYS or key in OK_KEYS:
                self.go_back()
            return None
        items = self.items()
        if not items:
            return None
        if key in UP_KEYS:
            self.index = (self.index - 1) % len(items)
        elif key in DOWN_KEYS:
            self.index = (self.index + 1) % len(items)
        elif key in OK_KEYS:
            return self._do(items[self.index][1])
        elif key == pygame.K_h and self.screen in (MAIN, PAUSE):
            self.open_help()
        elif self.screen == PAUSE and key in (pygame.K_ESCAPE, pygame.K_p):
            return "resume"
        elif self.screen == BOARD and key in BACK_KEYS:
            return "main_menu" if self.after_run else self._do("back")
        elif self.screen == BOARD and key == pygame.K_r and self.after_run:
            return "play"
        return None

    def wheel(self, step):
        if self.screen == ENTRY and self.form:
            self.form.field = "country"
            self.form.scroll_by(step)

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
