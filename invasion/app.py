"""Window, event handling and the async main loop (desktop and browser)."""
import asyncio
import sys

import pygame

from .autopilot import autopilot
from .bridge import FORWARDED_EVENTS, IS_BROWSER, StateReporter, create_bridge
from .config import Config
from .controls import Controls
from .game import GAME_OVER, GAME_VERSION, PLAYING, TITLE, Game
from .render import Renderer


class App:
    def __init__(self, cfg=None, seed=None, max_frames=None, autoplay=False):
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

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
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

    def handle_events(self):
        game = self.game
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if not IS_BROWSER:
                    self.running = False
            elif event.type == pygame.KEYDOWN:
                key = event.key
                self.controls.key_down(key)
                if key in (pygame.K_p, pygame.K_ESCAPE):
                    game.toggle_pause()
                elif key == pygame.K_r:
                    game.restart()
                elif key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER) and game.state == TITLE:
                    game.start_run()
                elif key == pygame.K_q and not IS_BROWSER:
                    self.running = False
            elif event.type == pygame.KEYUP:
                self.controls.key_up(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game.state == TITLE:
                    game.start_run()
                elif game.state == GAME_OVER:
                    game.restart()
            elif event.type == getattr(pygame, "WINDOWFOCUSLOST", None) and not IS_BROWSER:
                # Desktop only: in the browser the host page may own focus
                # (e.g. on-screen touch buttons) and decides about pausing.
                self.controls.release_all()
                game.set_paused(True)

    def handle_host_commands(self):
        game = self.game
        for cmd in self.bridge.poll():
            kind = cmd["type"]
            seed = cmd.get("seed")
            seed = seed if isinstance(seed, int) and not isinstance(seed, bool) else None
            if kind == "pause":
                game.set_paused(True)
            elif kind == "resume":
                game.set_paused(False)
            elif kind == "input":
                self.controls.set_virtual(**{k: cmd[k] for k in ("left", "right", "fire") if k in cmd})
            elif kind == "special":
                self.controls.press_special()
            elif kind == "start" and game.state in (TITLE, GAME_OVER):
                game.start_run(seed)
            elif kind == "restart":
                game.restart(seed)

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
                game.start_run()
            inp = autopilot(game)
        else:
            inp = self.controls.state()
        if game.advance(frame_dt, inp) > 0:
            self.controls.consume_edges()
        events = game.drain_events()
        self.renderer.handle_events(events, game)
        self._forward_events(events, frame_dt)
        self.renderer.draw(self.screen, game, frame_dt)
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
