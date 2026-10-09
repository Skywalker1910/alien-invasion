"""Window, menus, guide, leaderboard and the async main loop (desktop and browser)."""
import asyncio
import sys

import pygame

from .autopilot import autopilot
from .bridge import FORWARDED_EVENTS, IS_BROWSER, StateReporter, create_bridge
from .config import Config
from .controls import Controls
from .countries import load_countries
from .game import GAME_OVER, GAME_VERSION, PLAYING, TITLE, Game
from .guide import Guide
from .menu import BOARD, ENTRY, HELP, MAIN, PAUSE, EntryForm, Menu
from .render import Renderer
from .storage import clean_country, clean_name, open_store

BRIEFING_NEXT = (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_RIGHT, pygame.K_d)
BRIEFING_BACK = (pygame.K_LEFT, pygame.K_a, pygame.K_BACKSPACE)


class App:
    def __init__(self, cfg=None, seed=None, max_frames=None, autoplay=False, store=None):
        self.cfg = cfg or Config()
        d = self.cfg.display
        pygame.init()
        pygame.display.set_caption(d.title)
        self.display = self._open_window(d.width, d.height)
        # Everything is drawn on a fixed logical playfield, then scaled to
        # the window if the window is a different size.
        if self.display.get_size() == (d.width, d.height):
            self.screen = self.display
        else:
            self.screen = pygame.Surface((d.width, d.height))
        self.clock = pygame.time.Clock()
        self.game = Game(self.cfg, seed)
        self.renderer = Renderer(self.cfg)
        self.controls = Controls()
        self.menu = Menu(allow_quit=not IS_BROWSER)
        self.guide = Guide()
        self.store = store if store is not None else open_store()
        self.countries = load_countries()
        self.country_codes = {c["code"] for c in self.countries}
        self.bridge = create_bridge()
        self.reporter = StateReporter(self.bridge)
        self.max_frames = max_frames
        self.autoplay = autoplay
        self.running = True
        self.frames = 0

    @staticmethod
    def _open_window(width, height):
        if IS_BROWSER:
            return pygame.display.set_mode((width, height))
        try:
            return pygame.display.set_mode((width, height), pygame.SCALED | pygame.RESIZABLE)
        except pygame.error:
            return pygame.display.set_mode((width, height))

    def _to_logical(self, pos):
        if self.screen is self.display:
            return pos
        dw, dh = self.display.get_size()
        scale, ox, oy = self._letterbox(dw, dh)
        return ((pos[0] - ox) / scale, (pos[1] - oy) / scale)

    def _letterbox(self, dw, dh):
        w, h = self.cfg.display.width, self.cfg.display.height
        scale = min(dw / w, dh / h)
        return scale, (dw - w * scale) / 2, (dh - h * scale) / 2

    # ------------------------------------------------------------------
    # Actions (from menus, keys and the host)
    # ------------------------------------------------------------------
    def start(self, seed=None, tutorial=False):
        self.game.start_run(seed)
        self.menu.screen = None
        self.controls.consume_edges()
        first_time = not self.store.get("tutorial_done", False)
        if (tutorial or first_time) and not self.autoplay:
            self.guide.start()
            self.bridge.emit({"type": "briefing_started"})
        else:
            self.guide.stop()

    def finish_briefing(self):
        self.store.set("tutorial_done", True)
        self.bridge.emit({"type": "briefing_finished"})

    def show_leaderboard(self, highlight=None, after_run=False):
        self.menu.open_board(self.store.top(10), highlight, after_run)

    def save_score(self):
        form, game = self.menu.form, self.game
        name = clean_name(form.name)
        country = clean_country(form.country, self.country_codes)
        entry_id = self.store.add_score(name, country, game.score, game.level, game.run_id, game.seed)
        self.store.set("pilot", {"name": name, "country": country})
        self.bridge.emit({"type": "score_saved", "name": name, "country": country, "score": game.score,
                          "level": game.level, "run_id": game.run_id, "seed": game.seed,
                          "rank": self.store.rank(entry_id)})
        self.show_leaderboard(entry_id, after_run=True)

    def act(self, action):
        game = self.game
        if action == "play":
            self.start()
        elif action == "tutorial":
            self.start(tutorial=True)
        elif action == "leaderboard":
            self.show_leaderboard()
        elif action == "save" and self.menu.form:
            self.save_score()
        elif action == "skip":
            self.show_leaderboard(after_run=True)
        elif action == "resume":
            game.set_paused(False)
            self.menu.screen = None
            self.controls.consume_edges()
        elif action == "restart":
            game.abandon_run()
            self.start()
        elif action == "main_menu":
            game.abandon_run()
            self.guide.stop()
            self.menu.open(MAIN)
        elif action == "quit" and not IS_BROWSER:
            self.running = False

    def pause(self):
        if self.game.set_paused(True) or self.game.paused:
            self.menu.open(PAUSE)
            self.controls.release_all()

    def _after_game_over(self):
        """Ask for a pilot name if the run scored anything."""
        self.guide.stop()
        if self.game.score <= 0 or self.autoplay:
            return
        pilot = self.store.get("pilot", {}) or {}
        self.menu.open_entry(EntryForm(self.countries, pilot.get("name", ""), pilot.get("country", "")))

    def _sync_menu(self):
        """Keep the menu in step with pauses/resumes coming from elsewhere."""
        game, menu = self.game, self.menu
        if game.state == TITLE and menu.screen is None:
            menu.open(MAIN)
        elif game.state == PLAYING and game.paused and menu.screen is None:
            menu.open(PAUSE)
        elif game.state == PLAYING and not game.paused and menu.screen in (PAUSE, HELP):
            menu.screen = None
        elif game.state == GAME_OVER and menu.screen == PAUSE:
            menu.screen = None

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def _briefing_key(self, key):
        guide = self.guide
        if key == pygame.K_ESCAPE:
            guide.skip()
            self.finish_briefing()
        elif key in BRIEFING_NEXT:
            if guide.advance():
                self.finish_briefing()
        elif key in BRIEFING_BACK:
            guide.back()

    def handle_events(self):
        game, menu = self.game, self.menu
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if not IS_BROWSER:
                    self.running = False
            elif event.type == pygame.KEYDOWN:
                key = event.key
                if menu.screen is not None:
                    self.act(menu.key_event(event))
                elif game.state == PLAYING and self.guide.blocking:
                    self._briefing_key(key)
                elif game.state == PLAYING:
                    if key in (pygame.K_p, pygame.K_ESCAPE):
                        self.pause()
                    else:
                        self.controls.key_down(key)
                elif game.state == GAME_OVER:
                    if key == pygame.K_r:
                        self.start()
                    elif key in (pygame.K_ESCAPE, pygame.K_m):
                        self.act("main_menu")
            elif event.type == pygame.KEYUP:
                self.controls.key_up(event.key)
            elif event.type == pygame.MOUSEWHEEL and event.y:
                if menu.screen is not None:
                    menu.wheel(-event.y)
                elif game.state == PLAYING and not self.guide.blocking:
                    self.controls.press_switch(-event.y)
            elif event.type == pygame.MOUSEMOTION and menu.screen is not None:
                menu.hover(self._to_logical(event.pos))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if menu.screen is not None:
                    self.act(menu.click(self._to_logical(event.pos)))
                elif game.state == PLAYING and self.guide.blocking:
                    if self.guide.advance():
                        self.finish_briefing()
                elif game.state == GAME_OVER:
                    self.start()
            elif event.type == getattr(pygame, "WINDOWFOCUSLOST", None) and not IS_BROWSER:
                # Desktop only: in the browser the host page may own focus
                # (e.g. on-screen touch buttons) and decides about pausing.
                self.controls.release_all()
                if game.state == PLAYING:
                    self.pause()

    def handle_host_commands(self):
        game = self.game
        for cmd in self.bridge.poll():
            kind = cmd["type"]
            seed = cmd.get("seed")
            seed = seed if isinstance(seed, int) and not isinstance(seed, bool) else None
            if kind == "pause":
                if game.state == PLAYING:
                    self.pause()
            elif kind == "resume":
                if game.state == PLAYING:
                    self.act("resume")
            elif kind == "input":
                self.controls.set_virtual(**{k: cmd[k] for k in ("left", "right", "up", "down", "fire")
                                               if k in cmd})
            elif kind == "special":
                self.controls.press_special()
            elif kind == "switch":
                self.controls.press_switch(-1 if cmd.get("direction", 1) < 0 else 1)
            elif kind == "select" and isinstance(cmd.get("slot"), int):
                self.controls.press_select(cmd["slot"])
            elif kind == "skip_briefing" and self.guide.blocking:
                self.guide.skip()
                self.finish_briefing()
            elif kind == "start" and game.state in (TITLE, GAME_OVER):
                self.start(seed)
            elif kind == "restart" and game.state == GAME_OVER:
                self.start(seed)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def _forward_events(self, events, frame_dt):
        for event in events:
            if event["type"] in FORWARDED_EVENTS:
                self.bridge.emit(event)
        self.reporter.update(self.game.snapshot(), frame_dt)

    def _present(self):
        if self.screen is not self.display:
            dw, dh = self.display.get_size()
            scale, ox, oy = self._letterbox(dw, dh)
            size = (round(self.cfg.display.width * scale), round(self.cfg.display.height * scale))
            self.display.fill((0, 0, 0))
            self.display.blit(pygame.transform.smoothscale(self.screen, size), (round(ox), round(oy)))
        pygame.display.flip()

    def frame(self, frame_dt):
        """One rendered frame: input, fixed simulation steps, drawing."""
        game = self.game
        self.handle_events()
        self.handle_host_commands()
        if self.autoplay:
            if game.state != PLAYING:
                self.start()
            inp = autopilot(game)
        else:
            inp = self.controls.state()
        self._sync_menu()
        self.guide.update(frame_dt)
        # The briefing freezes the game: no simulation steps until it's done.
        if not self.guide.blocking and game.advance(frame_dt, inp) > 0:
            self.controls.consume_edges()
        events = game.drain_events()
        self.renderer.handle_events(events, game)
        self.guide.on_events(events)
        self._forward_events(events, frame_dt)
        if any(e["type"] == "game_over" for e in events):
            self._after_game_over()
        self.renderer.draw(self.screen, game, frame_dt, self.menu, self.guide)
        self._present()

    async def run(self):
        d = self.cfg.display
        self.bridge.emit({"type": "ready", "version": GAME_VERSION,
                          "width": d.width, "height": d.height})
        while self.running:
            frame_dt = self.clock.tick(d.fps_cap) / 1000.0
            self.frame(frame_dt)
            self.frames += 1
            if self.max_frames is not None and self.frames >= self.max_frames:
                self.running = False
            await asyncio.sleep(0)   # hand control back to the browser every frame
        if not IS_BROWSER:
            pygame.quit()


def parse_args(argv):
    """Tiny argument parser: --seed N, --frames N, --autoplay."""
    opts = {"seed": None, "max_frames": None, "autoplay": False}
    args = list(argv)
    while args:
        arg = args.pop(0)
        if arg == "--seed" and args:
            opts["seed"] = int(args.pop(0))
        elif arg == "--frames" and args:
            opts["max_frames"] = int(args.pop(0))
        elif arg == "--autoplay":
            opts["autoplay"] = True
    return opts


async def main(argv=None):
    opts = parse_args(sys.argv[1:] if argv is None else argv)
    await App(**opts).run()
