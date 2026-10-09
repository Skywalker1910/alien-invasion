"""Tests for the leaderboard database, Orbi's briefing and the pilot entry flow."""
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

from invasion.countries import flag_path, load_countries  # noqa: E402
from invasion.game import GAME_OVER, PLAYING  # noqa: E402
from invasion.guide import STORY, Guide  # noqa: E402
from invasion.menu import BOARD, ENTRY, MAIN, EntryForm  # noqa: E402
from invasion.storage import MemoryStore, SQLiteStore, clean_name  # noqa: E402
from tests.test_app import RecordingBridge, make_app, press  # noqa: E402


# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------
@pytest.fixture(params=["memory", "sqlite"])
def store(request, tmp_path):
    if request.param == "memory":
        return MemoryStore()
    return SQLiteStore(str(tmp_path / "scores.db"))


def test_leaderboard_orders_by_score_and_ranks(store):
    store.add_score("Nova", "in", 500, 3)
    best = store.add_score("Kestrel", "us", 900, 5)
    low = store.add_score("Rook", "", 100, 1)
    top = store.top(10)
    assert [(e["name"], e["country"], e["score"]) for e in top] == [
        ("Kestrel", "us", 900), ("Nova", "in", 500), ("Rook", "", 100)]
    assert store.rank(best) == 1 and store.rank(low) == 3
    assert len(store.top(2)) == 2


def test_settings_round_trip(store):
    assert store.get("tutorial_done", False) is False
    store.set("tutorial_done", True)
    store.set("pilot", {"name": "Ace", "country": "jp"})
    assert store.get("tutorial_done") is True
    assert store.get("pilot") == {"name": "Ace", "country": "jp"}


def test_sqlite_scores_survive_reopening(tmp_path):
    path = str(tmp_path / "scores.db")
    SQLiteStore(path).add_score("Nova", "in", 1234, 4)
    again = SQLiteStore(path)
    assert again.top(1)[0]["name"] == "Nova"


def test_names_are_cleaned():
    assert clean_name("  Ace<script>  ") == "Acescript"
    assert clean_name("") == "Pilot"
    assert len(clean_name("x" * 40)) == 14


def test_every_country_has_a_bundled_flag():
    countries = load_countries()
    assert len(countries) > 200
    assert {"code": "in", "name": "India"} in countries
    assert all(os.path.exists(flag_path(c["code"])) for c in countries)


# ----------------------------------------------------------------------
# Orbi's briefing
# ----------------------------------------------------------------------
def test_guide_types_then_advances_and_finishes():
    guide = Guide()
    guide.start()
    assert guide.blocking and guide.typing
    assert guide.advance() is False and not guide.typing    # first press: finish the line
    assert guide.advance() is False and guide.page == 1     # second press: next page
    for _ in range(len(STORY) * 2):
        if guide.advance():
            break
    assert not guide.blocking and guide.tips_enabled


def test_tips_show_once_per_run():
    guide = Guide()
    guide.start()
    guide.skip()
    guide.on_events([{"type": "pickup_dropped"}])
    assert "capsule" in guide.tip.lower()
    guide.tip = None
    guide.on_events([{"type": "pickup_dropped"}])
    assert guide.tip is None
    guide.on_events([{"type": "pickup", "result": "stored"}])
    assert "Q / E" in guide.tip


def test_first_run_shows_briefing_and_freezes_the_game():
    app = make_app(first_time=True)
    press(app, pygame.K_RETURN)                    # Play
    assert app.game.state == PLAYING and app.guide.blocking
    ticks = app.game.ticks
    for _ in range(60):
        app.frame(1 / 60)
    assert app.game.ticks == ticks                 # frozen during the briefing
    press(app, pygame.K_ESCAPE)                    # skip
    assert not app.guide.blocking and app.store.get("tutorial_done") is True
    for _ in range(10):
        app.frame(1 / 60)
    assert app.game.ticks > ticks
    # Second run: no briefing.
    app.act("restart")
    assert not app.guide.blocking


def test_tutorial_menu_item_replays_the_briefing():
    app = make_app()
    app.frame(1 / 60)
    press(app, pygame.K_DOWN)
    press(app, pygame.K_DOWN)
    press(app, pygame.K_RETURN)                    # "Tutorial"
    assert app.guide.blocking
    for _ in range(len(STORY) * 2):
        press(app, pygame.K_SPACE)
    assert not app.guide.blocking


# ----------------------------------------------------------------------
# Pilot entry and leaderboard
# ----------------------------------------------------------------------
def end_run(app, score):
    game = app.game
    game.score = score
    game.lives = 1
    game.ship.invulnerable_timer = 0
    game._damage_player(10_000, "test")
    for _ in range(120):
        app.frame(1 / 60)
    assert game.state == GAME_OVER


def type_text(app, text):
    for ch in text:
        key = pygame.key.key_code(ch) if ch.isalnum() else pygame.K_SPACE
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, unicode=ch))
        app.frame(1 / 60)


def test_game_over_asks_for_name_and_country_then_shows_the_board():
    app = make_app()
    bridge = RecordingBridge()
    app.bridge = bridge
    press(app, pygame.K_RETURN)
    end_run(app, 4321)
    assert app.menu.screen == ENTRY
    type_text(app, "Ace")
    press(app, pygame.K_TAB)
    type_text(app, "ind")
    assert app.menu.form.filtered()[0]["code"] == "in"
    press(app, pygame.K_RETURN)                    # pick India and save
    assert app.menu.screen == BOARD
    top = app.store.top(1)[0]
    assert (top["name"], top["country"], top["score"]) == ("Ace", "in", 4321)
    assert app.menu.highlight == top["id"]
    saved = [e for e in bridge.sent if e["type"] == "score_saved"]
    assert saved and saved[0]["rank"] == 1 and saved[0]["country"] == "in"
    # Next time the form remembers the pilot.
    press(app, pygame.K_RETURN)                    # Play again
    end_run(app, 10)
    assert app.menu.form.name == "Ace" and app.menu.form.country == "in"


def test_skipping_saves_nothing_and_zero_scores_are_not_asked():
    app = make_app()
    press(app, pygame.K_RETURN)
    end_run(app, 500)
    press(app, pygame.K_ESCAPE)                    # skip
    assert app.menu.screen == BOARD and app.store.top() == []
    press(app, pygame.K_DOWN)
    press(app, pygame.K_RETURN)                    # Main menu
    assert app.menu.screen == MAIN
    press(app, pygame.K_RETURN)
    end_run(app, 0)
    assert app.menu.screen is None                 # nothing to save


def test_country_list_can_be_clicked():
    app = make_app()
    press(app, pygame.K_RETURN)
    end_run(app, 77)
    form = app.menu.form
    form.query = "jap"                             # filter so Japan is on screen
    app.frame(1 / 60)
    row = next(r for r, a in app.menu.hitboxes if a == "country:jp")
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=row.center))
    app.frame(1 / 60)
    assert form.country == "jp"


def test_entry_form_keyboard_editing():
    countries = [{"code": "fr", "name": "France"}, {"code": "in", "name": "India"}]
    form = EntryForm(countries, "Al", "fr")

    def key(k, ch=""):
        return form.key(pygame.event.Event(pygame.KEYDOWN, key=k, unicode=ch))

    key(pygame.K_BACKSPACE)
    key(pygame.K_x, "x")
    assert form.name == "Ax"
    key(pygame.K_RETURN)                           # to the country list
    assert form.field == "country" and form.cursor == 0
    key(pygame.K_DOWN)
    assert key(pygame.K_RETURN) == "save" and form.country == "in"
    assert key(pygame.K_ESCAPE) == "skip"


def test_tips_queue_instead_of_overlapping():
    guide = Guide()
    guide.start()
    guide.skip()
    guide.on_events([{"type": "pickup_dropped"}, {"type": "player_damaged"}])
    first = guide.tip
    assert "capsule" in first.lower() and len(guide.queue) == 1
    guide.update(4.6)                              # first tip times out
    guide.update(0.01)
    assert guide.tip != first and "health" in guide.tip.lower()


def test_tips_stay_inside_the_top_hud_bar():
    app = make_app()
    press(app, pygame.K_RETURN)
    app.guide.tips_enabled = True
    app.guide.show_tip("capsule", "A capsule! Fly into it before it falls past you.")
    for _ in range(30):
        app.frame(1 / 60)
    hud = pygame.Rect(0, 0, app.cfg.display.width, app.cfg.display.hud_height)
    # Draw the comms line on a clean surface and check where pixels landed.
    surf = pygame.Surface((app.cfg.display.width, app.cfg.display.height), pygame.SRCALPHA)
    app.renderer._draw_comms(surf, app.guide)
    bounds = surf.get_bounding_rect()
    assert bounds.width > 0 and hud.contains(bounds)
