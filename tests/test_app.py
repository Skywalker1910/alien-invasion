"""Smoke tests for the window loop, controls and the host bridge."""
import asyncio
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from invasion.app import App  # noqa: E402
from invasion.storage import MemoryStore  # noqa: E402
from invasion.bridge import NullBridge, SafeBridge, StateReporter  # noqa: E402
from invasion.controls import Controls  # noqa: E402
from invasion.game import PLAYING, TITLE  # noqa: E402


def make_app(seed=3, first_time=False, **kwargs):
    """An App with an in-memory store; the first-run briefing is off unless asked for."""
    store = MemoryStore()
    if not first_time:
        store.set("tutorial_done", True)
    app = App(seed=seed, store=store, **kwargs)
    pygame.event.clear()          # the headless display can queue a focus-lost event
    return app


class RecordingBridge:
    active = True

    def __init__(self, commands=()):
        self.sent = []
        self.commands = list(commands)

    def emit(self, event):
        self.sent.append(event)

    def poll(self):
        out, self.commands = self.commands, []
        return out


def test_autoplay_smoke_run():
    app = make_app(seed=11, max_frames=900, autoplay=True)
    asyncio.run(app.run())
    assert app.frames == 900


def test_keyboard_flow_and_no_wide_bullet_cheat():
    app = make_app(seed=3)
    width = app.cfg.player.blaster_size[0]
    for key in (pygame.K_t, pygame.K_RETURN):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
    app.frame(1 / 60)
    assert app.game.state == PLAYING
    assert app.cfg.player.blaster_size[0] == width
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_p))
    app.frame(1 / 60)
    assert app.game.paused
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    app.frame(1 / 60)
    assert not app.game.paused


def test_host_commands_and_events():
    app = make_app(seed=3)
    bridge = RecordingBridge([{"type": "start", "seed": 42}])
    app.bridge = bridge
    app.reporter = StateReporter(bridge)
    app.frame(1 / 60)
    assert app.game.state == PLAYING and app.game.seed == 42
    types = [e["type"] for e in bridge.sent]
    assert "run_started" in types and "state" in types

    bridge.commands = [{"type": "input", "right": True, "fire": True}]
    x0 = app.game.ship.x
    for _ in range(30):
        app.frame(1 / 60)
    assert app.game.ship.x > x0 and app.game.shots

    bridge.commands = [{"type": "pause"}]
    app.frame(1 / 60)
    assert app.game.paused
    bridge.commands = [{"type": "resume"}, {"type": "input", "right": False, "fire": False}]
    app.frame(1 / 60)
    assert not app.game.paused
    assert {"paused", "resumed"} <= {e["type"] for e in bridge.sent}


def test_controls_merge_keyboard_and_virtual_input():
    controls = Controls()
    controls.key_down(pygame.K_a)
    controls.key_down(pygame.K_w)
    controls.set_virtual(fire=True, down=True)
    state = controls.state()
    assert state.left and state.up and state.down and state.fire and not state.right
    controls.key_down(pygame.K_LSHIFT)
    assert controls.state().special
    controls.consume_edges()
    assert not controls.state().special
    controls.release_all()
    assert controls.state() == type(state)()


def test_state_reporter_throttles_score_only_changes():
    bridge = RecordingBridge()
    reporter = StateReporter(bridge, min_interval=0.25)
    snap = {k: None for k in StateReporter.FIELDS}
    snap.update(state=PLAYING, paused=False, score=0, level=1, wave=1, lives=3, run_id="1-1")
    reporter.update(snap, 0.016)
    reporter.update(dict(snap, score=50, health=90), 0.016)        # throttled
    reporter.update(dict(snap, score=50, lives=2), 0.016)         # lives change: immediate
    assert [e.get("lives") for e in bridge.sent] == [3, 2]
    reporter.update(dict(snap, score=80, lives=2), 0.3)           # after the interval
    assert bridge.sent[-1]["score"] == 80


def test_failing_bridge_is_disabled_not_fatal():
    class Broken:
        active = True

        def emit(self, event):
            raise RuntimeError("host went away")

        def poll(self):
            raise RuntimeError("host went away")

    bridge = SafeBridge(Broken())
    bridge.emit({"type": "ready"})
    assert bridge.poll() == [] and not bridge.active
    assert isinstance(bridge.inner, NullBridge)


def test_title_waits_for_player():
    app = make_app(seed=3)
    for _ in range(10):
        app.frame(1 / 60)
    assert app.game.state == TITLE


def press(app, key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
    app.frame(1 / 60)
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key))
    app.frame(1 / 60)


def test_main_menu_help_pages_and_back():
    from invasion.menu import HELP, HELP_PAGES, MAIN
    app = make_app(seed=3)
    app.frame(1 / 60)
    assert app.menu.screen == MAIN
    for _ in range(3):
        press(app, pygame.K_DOWN)
    press(app, pygame.K_RETURN)                   # Play, Leaderboard, Tutorial, "Help"
    assert app.menu.screen == HELP and app.menu.page == 0
    for _ in range(len(HELP_PAGES)):
        press(app, pygame.K_RIGHT)                # every page draws without errors
    assert app.menu.page == 0
    press(app, pygame.K_LEFT)
    assert app.menu.page == len(HELP_PAGES) - 1
    press(app, pygame.K_ESCAPE)
    assert app.menu.screen == MAIN and app.game.state == TITLE


def test_menu_buttons_are_clickable():
    from invasion.menu import HELP
    app = make_app(seed=3)
    app.frame(1 / 60)
    rect = dict((a, r) for r, a in app.menu.hitboxes)["help"]
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    app.frame(1 / 60)
    assert app.menu.screen == HELP
    tab = dict((a, r) for r, a in app.menu.hitboxes)["page:3"]
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=tab.center))
    app.frame(1 / 60)
    assert app.menu.page == 3


def test_pause_menu_restart_and_main_menu():
    from invasion.menu import MAIN, PAUSE
    app = make_app(seed=3)
    bridge = RecordingBridge()
    app.bridge = bridge
    press(app, pygame.K_RETURN)                   # Play
    first = app.game.run_id
    press(app, pygame.K_ESCAPE)
    assert app.game.paused and app.menu.screen == PAUSE
    press(app, pygame.K_DOWN)
    press(app, pygame.K_DOWN)
    press(app, pygame.K_RETURN)                   # "Restart run"
    assert app.game.state == PLAYING and not app.game.paused and app.game.run_id != first
    press(app, pygame.K_p)
    for _ in range(3):
        press(app, pygame.K_DOWN)
    press(app, pygame.K_RETURN)                   # "Main menu"
    assert app.game.state == TITLE and app.menu.screen == MAIN
    types = [e["type"] for e in bridge.sent]
    assert types.count("run_abandoned") == 2 and "game_over" not in types


def test_inventory_keys_and_mouse_wheel():
    from invasion.entities import Pickup
    app = make_app(seed=3)
    press(app, pygame.K_RETURN)
    game = app.game
    for kind in ("rail", "plasma"):
        game._collect(Pickup(kind, "weapon", 0, 0, 0))
    game._collect(Pickup("overdrive", "utility", 0, 0, 0))
    assert "overdrive" in game.ship.buffs and len(game.ship.inventory) == 2
    press(app, pygame.K_e)
    assert game.ship.weapon == "plasma"
    press(app, pygame.K_1)
    assert game.ship.weapon == "rail"
    pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    app.frame(1 / 60)
    assert game.ship.weapon == "plasma"


def test_host_inventory_commands():
    from invasion.entities import Pickup
    app = make_app(seed=3)
    bridge = RecordingBridge([{"type": "start"}])
    app.bridge = bridge
    app.frame(1 / 60)
    game = app.game
    for kind in ("rail", "plasma"):
        game._collect(Pickup(kind, "weapon", 0, 0, 0))
    bridge.commands = [{"type": "switch", "direction": 1}]
    app.frame(1 / 60)
    assert game.ship.weapon == "plasma"
    bridge.commands = [{"type": "select", "slot": 0}]
    app.frame(1 / 60)
    assert game.ship.weapon == "rail"
