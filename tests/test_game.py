"""State-transition tests for the game core. Run with: python -m pytest"""
import math
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from invasion.autopilot import autopilot  # noqa: E402
from invasion.config import Config  # noqa: E402
from invasion.entities import Bullet, PowerUp  # noqa: E402
from invasion.game import GAME_OVER, PLAYING, TITLE, Game, InputState  # noqa: E402
from invasion.waves import plan_wave  # noqa: E402

IDLE = InputState()


def new_game(seed=1):
    game = Game(seed=seed)
    game.start_run()
    hold_fire(game)
    return game


def hold_fire(game):
    """Stop the aliens from shooting so tests control every bullet."""
    game.fire_timer = 1e9


def run(game, seconds, inp=IDLE):
    for _ in range(round(seconds * game.cfg.display.sim_hz)):
        game.step(inp)
        hold_fire(game)


def shoot_ship(game, count=1):
    for _ in range(count):
        game.enemy_bullets.append(Bullet(game.ship.x, game.ship.y, 0, 0, (6, 14)))


def give(game, kind):
    game._collect(PowerUp(kind, game.ship.x, game.ship.y, (26, 26)))


def wait_until_vulnerable(game):
    pc = game.cfg.player
    run(game, pc.respawn_delay + pc.invulnerable_time + 0.1)
    assert game.ship.vulnerable


def of_type(events, kind):
    return [e for e in events if e["type"] == kind]


# ----------------------------------------------------------------------
# Lives and damage
# ----------------------------------------------------------------------
def test_three_lives_means_exactly_three_hits():
    game = new_game()
    assert game.lives == 3
    for expected in (2, 1, 0):
        wait_until_vulnerable(game)
        shoot_ship(game)
        game.step(IDLE)
        assert game.lives == expected
    assert game.state == PLAYING          # explosion plays out first
    run(game, game.cfg.player.game_over_delay + 0.1)
    assert game.state == GAME_OVER
    assert game.lives == 0


def test_simultaneous_hits_cost_one_life():
    game = new_game()
    shoot_ship(game, count=3)
    enemy = game.enemies[0]
    enemy.mode, enemy.x, enemy.y = "diving", game.ship.x, game.ship.y
    game.step(IDLE)
    assert game.lives == 2
    run(game, 0.5)
    assert game.lives == 2


def test_respawn_grants_short_invulnerability():
    game = new_game()
    pc = game.cfg.player
    shoot_ship(game)
    game.step(IDLE)
    assert not game.ship.alive
    run(game, pc.respawn_delay + 0.05)
    assert game.ship.alive
    assert 0 < game.ship.invulnerable_timer <= pc.invulnerable_time
    shoot_ship(game)
    game.step(IDLE)
    assert game.lives == 2                # blinking ship can't be hit
    run(game, pc.invulnerable_time)
    shoot_ship(game)
    game.step(IDLE)
    assert game.lives == 1


def test_invasion_costs_a_life_even_with_shield_and_resets_formation():
    game = new_game()
    give(game, "shield")
    top = game.origin[1]
    game.banner_timer = 0
    game.origin[1] = game.ship.y - 60
    run(game, 0.1)
    assert game.lives == 2
    assert game.origin[1] == top
    assert "shield" not in game.powerups


# ----------------------------------------------------------------------
# Power-ups
# ----------------------------------------------------------------------
def test_shield_blocks_damage_then_expires():
    game = new_game()
    give(game, "shield")
    shoot_ship(game, count=2)
    game.step(IDLE)
    assert game.lives == 3
    game.drain_events()
    run(game, game.cfg.powerups.durations["shield"])
    assert "shield" not in game.powerups
    assert of_type(game.drain_events(), "powerup_expired") == [{"type": "powerup_expired", "kind": "shield"}]
    shoot_ship(game)
    game.step(IDLE)
    assert game.lives == 2


def test_weapon_powerups_refresh_and_expire():
    game = new_game()
    durations = game.cfg.powerups.durations
    give(game, "spread")
    run(game, 6)
    give(game, "spread")                   # refresh to full, never stacks past it
    assert math.isclose(game.powerups["spread"], durations["spread"])
    give(game, "pierce")                   # different kinds stack

    game.bullets.clear()
    game._fire_player()
    assert len(game.bullets) == 3
    assert all(b.pierce_left == game.cfg.powerups.pierce_hits for b in game.bullets)

    run(game, durations["spread"] + 0.05)
    assert game.powerups == {}
    game.bullets.clear()
    game.ship.fire_timer = 0
    game._fire_player()
    assert len(game.bullets) == 1 and game.bullets[0].pierce_left == 0


def test_piercing_bullet_passes_through_enemies():
    game = new_game()
    give(game, "pierce")
    targets = game.enemies[:3]
    for i, enemy in enumerate(targets):
        enemy.hp = 1
        enemy.x, enemy.y = 100, 300 + i * 50
    bullet = Bullet(100, 300, 0, 0, (4, 200), pierce=3)
    game.bullets = [bullet]
    game._collisions()
    assert all(not e.alive for e in targets)
    assert bullet.alive and bullet.pierce_left == 0


def test_losing_a_life_clears_powerups_but_keeps_specials():
    game = new_game()
    for kind in ("shield", "spread", "pierce"):
        give(game, kind)
    game.powerups.pop("shield")
    specials = game.specials
    shoot_ship(game)
    game.step(IDLE)
    assert game.lives == 2
    assert game.powerups == {}
    assert game.specials == specials


def test_extra_life_is_capped():
    game = new_game()
    cap = game.cfg.player.max_lives
    pickups = cap + 2
    for _ in range(pickups):
        give(game, "life")
    assert game.lives == cap
    over_cap = pickups - (cap - game.cfg.player.start_lives)
    assert game.score == over_cap * game.cfg.powerups.life_cap_bonus
    for _ in range(300):                   # never dropped while at the cap
        game._maybe_drop(100, 100, 1.0, guaranteed=True)
    assert "life" not in {p.kind for p in game.pickups}


# ----------------------------------------------------------------------
# Flow
# ----------------------------------------------------------------------
def clear_wave(game):
    for enemy in list(game.enemies):
        game._damage_enemy(enemy, enemy.hp)
    game.enemies = []
    if game.boss:
        game._damage_boss(game.boss.hp)


def test_wave_progression_and_boss_every_fifth_wave():
    game = new_game()
    for wave in range(1, 7):
        assert game.wave == wave
        assert (game.boss is not None) == (wave == 5)
        clear_wave(game)
        game.step(IDLE)
        assert game.clear_timer > 0
        events = game.drain_events()
        assert of_type(events, "wave_cleared")[0]["wave"] == wave
        run(game, game.cfg.flow.wave_clear_delay + 0.05)
    specials_after_boss = min(game.cfg.player.special_max,
                              game.cfg.player.special_start + game.cfg.player.special_per_boss)
    assert game.specials == specials_after_boss


def test_game_over_is_emitted_once_per_run():
    game = new_game(seed=5)
    game.drain_events()
    for _ in range(3):
        wait_until_vulnerable(game)
        shoot_ship(game)
        game.step(IDLE)
    run(game, 5)
    events = game.drain_events()
    over = of_type(events, "game_over")
    assert len(over) == 1
    assert over[0]["run_id"] == game.run_id and over[0]["seed"] == 5
    game._end_run()                         # even if something calls it again
    assert of_type(game.drain_events(), "game_over") == []

    assert game.restart()
    assert of_type(game.drain_events(), "run_started")
    hold_fire(game)
    for _ in range(3):
        wait_until_vulnerable(game)
        shoot_ship(game)
        game.step(IDLE)
    run(game, 5)
    assert len(of_type(game.drain_events(), "game_over")) == 1


def test_restart_cleans_up_everything():
    game = new_game(seed=9)
    first_run = game.run_id
    give(game, "shield")
    give(game, "spread")
    game.score = 12345
    game.specials = 0
    game._start_wave(3)
    game._fire_player()
    game._maybe_drop(200, 200, 1.0, guaranteed=True)
    shoot_ship(game)
    game.lives = 1
    game.powerups.pop("shield")
    game.step(IDLE)
    run(game, 3)
    assert game.state == GAME_OVER
    assert game.high_score >= 12345

    assert game.restart()
    assert game.state == PLAYING
    assert game.run_id != first_run
    assert (game.score, game.wave, game.lives) == (0, 1, 3)
    assert game.specials == game.cfg.player.special_start
    assert game.powerups == {} and game.pickups == [] and game.enemy_bullets == []
    assert game.bullets == [] and game.boss is None
    assert game.ship.alive and not game.game_over_emitted
    assert game.high_score >= 12345         # session high score survives restarts


def test_restart_is_ignored_mid_run_and_on_title():
    game = Game(seed=1)
    assert game.state == TITLE and not game.restart()
    game.start_run()
    game.score = 500
    assert not game.restart()
    assert game.score == 500


def test_pause_freezes_the_simulation():
    game = new_game()
    give(game, "spread")
    assert game.set_paused(True)
    before = (game.ticks, game.powerups["spread"], game.origin[0], game.ship.x)
    run(game, 3, InputState(right=True, fire=True))
    assert (game.ticks, game.powerups["spread"], game.origin[0], game.ship.x) == before
    assert game.set_paused(False)
    assert not game.set_paused(False)       # no duplicate resume events
    run(game, 0.5, InputState(right=True))
    assert game.ship.x > before[3]


# ----------------------------------------------------------------------
# Timing and determinism
# ----------------------------------------------------------------------
def test_movement_and_timers_do_not_depend_on_frame_rate():
    results = []
    for fps in (30, 60, 144, 240):
        game = new_game()
        give(game, "spread")
        x0 = game.ship.x
        for _ in range(fps):                # one second of frames
            game.advance(1 / fps, InputState(right=True))
        results.append((game.ship.x - x0, game.powerups["spread"], game.ticks))
    for moved, remaining, ticks in results:
        assert abs(ticks - results[0][2]) <= 1
        assert abs(moved - results[0][0]) <= game.cfg.player.speed / game.cfg.display.sim_hz + 1e-6
        assert abs(remaining - results[0][1]) <= 1 / game.cfg.display.sim_hz + 1e-6


def test_long_stalls_do_not_fast_forward():
    game = new_game()
    steps = game.advance(5.0, IDLE)
    assert steps == game.cfg.display.max_steps_per_frame


def test_same_seed_and_inputs_give_the_same_run():
    def play(seed):
        game = Game(seed=seed)
        game.start_run()
        for _ in range(120 * 90):
            game.step(autopilot(game))
            if game.state != PLAYING:
                break
        return (game.score, game.wave, game.lives, game.kills, game.ticks,
                [(round(e.x, 3), round(e.y, 3), e.hp) for e in game.enemies])
    assert play(77) == play(77)
    assert play(77) != play(78)


# ----------------------------------------------------------------------
# Fairness
# ----------------------------------------------------------------------
def test_early_waves_are_approachable():
    cfg = Config()
    first = plan_wave(1, cfg, Game(cfg).rng)
    assert {kind for kind, _, _ in first.enemies} == {"standard"}
    assert not first.aimed_shots and first.max_divers == 0
    assert first.max_enemy_bullets <= 2
    # A shot leaves at least ~0.5 s to react even at the top bullet speed.
    assert cfg.enemy_fire.safe_distance / cfg.enemy_fire.bullet_speed_max >= 0.5


def test_boss_fan_always_leaves_a_gap_wider_than_the_ship():
    cfg = Config()
    ship_y = cfg.display.height - cfg.player.bottom_margin - cfg.player.size[1] / 2
    distance = ship_y - (cfg.boss.y + cfg.boss.size[1] / 2)
    gap = distance * math.tan(math.radians(cfg.boss.fan_step))   # neighbouring bullets
    ship_hitbox = cfg.player.size[0] * cfg.player.hitbox_scale
    assert gap - cfg.enemy_fire.bullet_size[0] > ship_hitbox * 1.5


def test_enemies_do_not_fire_from_point_blank():
    game = new_game()
    for enemy in game.enemies:
        enemy.y = game.ship.y - game.cfg.enemy_fire.safe_distance + 10
        enemy.slot = (enemy.slot[0], 0)
    assert all(game.ship.y - e.y < game.cfg.enemy_fire.safe_distance for e in game.enemies)
    game.banner_timer = 0
    game.fire_timer = 0
    game._update_enemy_fire(game.dt)
    assert all(e.charge_timer <= 0 for e in game.enemies)
