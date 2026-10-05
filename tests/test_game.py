"""State-transition tests for the game core. Run with: python -m pytest"""
import math
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest  # noqa: E402

from invasion import weapons  # noqa: E402
from invasion.autopilot import autopilot  # noqa: E402
from invasion.config import Config  # noqa: E402
from invasion.entities import EnemyShot, Pickup  # noqa: E402
from invasion.game import GAME_OVER, PLAYING, TITLE, Game, InputState  # noqa: E402
from invasion.levels import build_wave, level_spec  # noqa: E402

IDLE = InputState()
FIRE = InputState(fire=True)


def new_game(seed=1):
    game = Game(seed=seed)
    game.start_run()
    calm(game)
    return game


def calm(game):
    """Freeze the level director and silence enemies so tests control everything."""
    game.phase = "test"
    game.banner_timer = 0.0
    game.enemies.clear()
    game.enemy_shots.clear()
    game.shots_cap = 0


def run(game, seconds, inp=IDLE):
    for _ in range(round(seconds * game.cfg.display.sim_hz)):
        game.step(inp)


def hit_ship(game, damage=10, count=1):
    for _ in range(count):
        game.enemy_shots.append(EnemyShot("bullet", game.ship.x, game.ship.y, 0, 0, (8, 14), damage))
    game.step(IDLE)


def give(game, kind):
    category = "weapon" if kind in game.cfg.weapons else "utility"
    game._collect(Pickup(kind, category, game.ship.x, game.ship.y, 0.0))


def add_enemy(game, kind="guardian", x=None, y=200, hp=None):
    enemy = game._new_enemy(kind)
    enemy.x = game.ship.x if x is None else x
    enemy.y = y
    enemy.anchor = (enemy.x, enemy.y)
    enemy.state = "hold"
    enemy.fire_timer = 1e9
    enemy.action_timer = 1e9
    if hp is not None:
        enemy.hp = enemy.max_hp = hp
    return enemy


def activate(game, kind):
    """Collect a storable upgrade and switch it on straight away."""
    give(game, kind)
    game.select_slot(game.ship.find(kind))


def of_type(events, kind):
    return [e for e in events if e["type"] == kind]


def wait_iframes(game):
    run(game, game.cfg.player.hurt_iframes + 0.05)


# ----------------------------------------------------------------------
# Hull, armor, shield, lives
# ----------------------------------------------------------------------
def test_damage_goes_to_armor_first_then_hull():
    game = new_game()
    hit_ship(game, 30)
    assert game.ship.hull == 70
    give(game, "armor")
    wait_iframes(game)
    hit_ship(game, 30)
    assert (game.ship.armor, game.ship.hull) == (20, 70)
    wait_iframes(game)
    hit_ship(game, 30)
    assert (game.ship.armor, game.ship.hull) == (0, 60)


def test_one_burst_cannot_chain_damage():
    game = new_game()
    hit_ship(game, 10, count=4)
    assert game.ship.hull == 90
    run(game, 0.1)
    hit_ship(game, 10)
    assert game.ship.hull == 90              # still inside the i-frames
    wait_iframes(game)
    hit_ship(game, 10)
    assert game.ship.hull == 80


def test_three_ships_means_three_hull_bars():
    game = new_game()
    pc = game.cfg.player
    for expected in (2, 1, 0):
        assert game.ship.alive
        hit_ship(game, pc.max_hull)
        assert game.lives == expected
        assert not game.ship.alive
        run(game, pc.respawn_delay + pc.invulnerable_time + 0.1)
    assert game.state == GAME_OVER


def test_shield_blocks_a_number_of_hits():
    game = new_game()
    give(game, "shield")
    charges = game.cfg.pickups["shield"].value
    assert game.ship.shield == charges
    for _ in range(int(charges)):
        hit_ship(game, 25)                   # blocks even back to back
    assert game.ship.hull == game.cfg.player.max_hull
    assert game.ship.shield == 0
    hit_ship(game, 25)
    assert game.ship.hull == 75


def test_losing_a_ship_resets_loadout_but_keeps_shockwave():
    game = new_game()
    pc = game.cfg.player
    for kind in ("rail", "armor"):
        give(game, kind)
    activate(game, "overdrive")
    game.shock_charge = 0.6
    hit_ship(game, 500)
    assert game.lives == 2
    ship = game.ship
    assert ship.weapon is None and ship.buffs == {} and ship.armor == 0 and ship.shield == 0
    assert ship.inventory == []
    run(game, pc.respawn_delay + 0.05)
    assert ship.alive and ship.hull == pc.max_hull
    assert 0 < ship.invulnerable_timer <= pc.invulnerable_time
    hit_ship(game, 50)
    assert ship.hull == pc.max_hull          # blinking ship can't be hurt
    assert game.shock_charge > 0.6


# ----------------------------------------------------------------------
# Weapons
# ----------------------------------------------------------------------
@pytest.mark.parametrize("kind", list(Config().weapons))
def test_every_weapon_damages_a_target_above(kind):
    game = new_game()
    target = add_enemy(game, "guardian", y=250, hp=500)
    give(game, kind)
    run(game, 1.0, FIRE)
    assert target.hp < 500, kind


def test_ammo_weapons_count_shots_refill_and_run_out():
    game = new_game()
    give(game, "rail")
    full = game.cfg.weapons["rail"].ammo
    weapons.fire(game)
    weapons.fire(game)
    assert game.ship.ammo == full - 2
    give(game, "rail")
    assert game.ship.ammo == full            # same weapon refills
    game.drain_events()
    for _ in range(full):
        weapons.fire(game)
    assert game.ship.weapon is None
    assert of_type(game.drain_events(), "weapon_empty")


def test_second_weapon_is_stored_and_can_be_switched_to():
    game = new_game()
    give(game, "rapid")
    give(game, "plasma")
    ship = game.ship
    assert ship.weapon == "rapid"                    # already armed: new one waits
    assert [s.kind for s in ship.inventory] == ["rapid", "plasma"]
    game.step(InputState(switch=1))
    assert ship.weapon == "plasma"
    assert ship.ammo == game.cfg.weapons["plasma"].ammo
    game.step(InputState(switch=1))
    assert ship.weapon is None                       # wraps round to the blaster
    game.step(InputState(switch=-1))
    assert ship.weapon == "plasma"
    game.step(InputState(select=0))
    assert ship.weapon == "rapid"


def test_ammo_is_kept_per_slot_when_switching():
    game = new_game()
    give(game, "rail")
    give(game, "homing")
    for _ in range(5):
        weapons.fire(game)
    game.cycle_weapon(1)
    weapons.fire(game)
    game.cycle_weapon(-1)
    assert game.ship.weapon == "rail"
    assert game.ship.ammo == game.cfg.weapons["rail"].ammo - 5
    assert game.ship.inventory[1].ammo == game.cfg.weapons["homing"].ammo - 1


def test_timed_weapon_only_drains_while_equipped():
    game = new_game()
    give(game, "rapid")
    give(game, "spread")
    run(game, 5)
    full = game.cfg.weapons["spread"].duration
    assert game.ship.inventory[1].time == full
    game.select_slot(1)
    run(game, 2)
    assert game.ship.weapon_time == pytest.approx(full - 2, abs=0.05)


def test_empty_weapon_leaves_and_next_weapon_is_equipped():
    game = new_game()
    give(game, "rail")
    give(game, "plasma")
    game.drain_events()
    for _ in range(game.cfg.weapons["rail"].ammo):
        weapons.fire(game)
    assert game.ship.weapon == "plasma"
    assert [s.kind for s in game.ship.inventory] == ["plasma"]
    events = game.drain_events()
    assert of_type(events, "weapon_empty") and of_type(events, "weapon_switched")


def test_upgrades_are_stored_until_activated():
    game = new_game()
    give(game, "overdrive")
    give(game, "magnet")
    ship = game.ship
    assert ship.buffs == {}
    run(game, 3)
    assert ship.inventory[0].time == game.cfg.pickups["overdrive"].duration
    game.step(InputState(activate=True))             # F: oldest stored upgrade
    assert "overdrive" in ship.buffs and [s.kind for s in ship.inventory] == ["magnet"]
    game.step(InputState(select=0))                  # number key on an upgrade activates it
    assert "magnet" in ship.buffs and ship.inventory == []
    # Cycling weapons never touches upgrades.
    give(game, "wingmen")
    game.step(InputState(switch=1))
    assert "wingmen" not in ship.buffs and ship.find("wingmen") == 0


def test_full_inventory_replaces_the_emptiest_slot():
    game = new_game()
    cap = game.cfg.player.inventory_slots
    kinds = list(game.cfg.weapons) + ["wingmen", "overdrive"]
    for kind in kinds:
        give(game, kind)
    ship = game.ship
    assert len(ship.inventory) == cap
    ship.selected = 0                                # spread equipped, protected
    ship.inventory[2].ammo = 1                       # railgun nearly empty
    game.drain_events()
    give(game, "magnet")
    assert len(ship.inventory) == cap
    assert ship.find("rail") is None and ship.find("magnet") is not None
    assert ship.weapon == "spread"
    assert of_type(game.drain_events(), "inventory_replaced")[0]["kind"] == "rail"


def test_losing_a_ship_keeps_the_rest_of_the_inventory():
    game = new_game()
    give(game, "rail")
    give(game, "laser")
    give(game, "overdrive")
    activate(game, "wingmen")
    hit_ship(game, 500)
    ship = game.ship
    assert [s.kind for s in ship.inventory] == ["laser", "overdrive"]
    assert ship.weapon is None and ship.buffs == {}


def test_timed_weapon_expires():
    game = new_game()
    give(game, "spread")
    run(game, game.cfg.weapons["spread"].duration + 0.05)
    assert game.ship.weapon is None


def test_laser_only_drains_while_firing():
    game = new_game()
    give(game, "laser")
    full = game.ship.weapon_time
    run(game, 2.0)
    assert game.ship.weapon_time == full
    run(game, 2.0, FIRE)
    assert game.ship.weapon_time == pytest.approx(full - 2.0, abs=0.05)


# ----------------------------------------------------------------------
# Pickups and buffs
# ----------------------------------------------------------------------
def test_buffs_refresh_and_expire():
    game = new_game()
    activate(game, "wingmen")
    run(game, 10)
    activate(game, "wingmen")
    assert game.ship.buffs["wingmen"] == game.cfg.pickups["wingmen"].duration
    game.drain_events()
    run(game, game.cfg.pickups["wingmen"].duration + 0.05)
    assert "wingmen" not in game.ship.buffs
    assert of_type(game.drain_events(), "buff_expired")


def test_overdrive_doubles_damage():
    game = new_game()
    a = add_enemy(game, x=200, hp=100)
    game.ship.x = 200
    weapons.fire(game)
    run(game, 0.5)
    normal = 100 - a.hp
    b = add_enemy(game, x=700, hp=100)
    game.ship.x = 700
    activate(game, "overdrive")
    game.ship.fire_timer = 0
    weapons.fire(game)
    run(game, 0.5)
    assert 100 - b.hp == 2 * normal


def test_pickups_fall_and_can_be_missed():
    game = new_game()
    game.ship.x = 900
    game._drop_pickup(100, 300)
    game.drain_events()
    run(game, 3)
    assert game.pickups == []
    assert of_type(game.drain_events(), "pickup_missed")


def test_magnet_pulls_pickups_in():
    game = new_game()
    activate(game, "magnet")
    game._drop_pickup(game.ship.x + 200, game.ship.y - 220)
    kind = game.pickups[0].kind
    game.drain_events()
    run(game, 1.5)
    assert any(e["kind"] == kind for e in of_type(game.drain_events(), "pickup"))


def test_pity_timer_guarantees_a_drop():
    game = new_game()
    drone = add_enemy(game, "drone", hp=1)
    game.pity_timer = game.cfg.drops.pity_time + 1
    game._damage_enemy(drone, 1)
    assert len(game.pickups) == 1


def test_utility_caps():
    game = new_game()
    pc = game.cfg.player
    hit_ship(game, 50)
    give(game, "repair")
    assert game.ship.hull == 85
    for _ in range(5):
        give(game, "repair")
        give(game, "armor")
        give(game, "shield")
        give(game, "life")
    assert game.ship.hull == pc.max_hull
    assert game.ship.armor == pc.max_armor
    assert game.ship.shield == pc.max_shield
    assert game.lives == pc.max_lives
    game.pickups.clear()
    for _ in range(200):
        game._drop_pickup(100, 100)
    assert not {"life", "shield"} & {p.kind for p in game.pickups}


# ----------------------------------------------------------------------
# Shockwave and combo
# ----------------------------------------------------------------------
def test_shockwave_kills_heavy_ships_then_recharges():
    game = new_game()
    guardian = add_enemy(game, "guardian", y=game.ship.y - 200)
    game.step(InputState(special=True))
    assert game.shock_charge == 0
    run(game, 0.5)
    assert not guardian.alive
    game.step(InputState(special=True))
    assert len(game.shockwaves) == 0         # not recharged yet
    game.drain_events()
    run(game, game.cfg.player.shock_recharge)
    assert game.shock_charge == 1.0
    assert of_type(game.drain_events(), "shock_ready")


def test_combo_multiplier_builds_and_resets_on_damage():
    game = new_game()
    for i in range(game.cfg.player.combo_step * 2):
        game._damage_enemy(add_enemy(game, "drone", x=50 + i * 30, hp=1), 1)
    assert game.multiplier == 3
    hit_ship(game, 5)
    assert game.multiplier == 1


# ----------------------------------------------------------------------
# Bosses
# ----------------------------------------------------------------------
def boss_game(level=3):
    game = new_game()
    game._start_level(level)
    calm(game)
    game.boss.y = game.boss.target_y
    game.boss.place_parts()
    return game


def shoot_at(game, x, y_from=None):
    shot = weapons.Shot("bullet", x, y_from or game.boss.rect.bottom + 30, 0, -900, (4, 18), 1.0)
    game.shots.append(shot)
    for _ in range(10):
        game.step(IDLE)
        if not shot.alive:
            break
    return shot


def test_boss_hull_deflects_and_only_active_weapons_take_damage():
    game = boss_game()
    boss = game.boss
    boss.spec.speed = 0
    stage1 = [p for p in boss.parts if p.stage == 1]
    stage2 = [p for p in boss.parts if p.stage == 2]
    gap_x = boss.x + 110                      # between the outer cannons and inner turrets
    game.drain_events()
    shoot_at(game, gap_x)
    assert of_type(game.drain_events(), "deflect")
    hp = stage2[0].hp
    shoot_at(game, stage2[0].x)
    assert stage2[0].hp == hp                # armored until stage 2
    hp = stage1[0].hp
    shoot_at(game, stage1[0].x)
    assert stage1[0].hp < hp


@pytest.mark.parametrize("level", [3, 6, 10])
def test_bosses_fight_in_three_stages_then_the_level_moves_on(level):
    game = boss_game(level)
    boss = game.boss
    game.drain_events()
    stages = []
    while game.boss:
        for part in boss.active_parts():
            game._damage_part(part, part.hp)
        stages.append(boss.stage)
        boss.stage_timer = 0
    events = game.drain_events()
    assert [e["stage"] for e in of_type(events, "boss_stage")] == [2, 3]
    assert of_type(events, "boss_defeated")
    assert of_type(events, "level_cleared")
    assert len(game.pickups) >= 3
    game.phase = "clear"
    run(game, game.cfg.flow.level_clear_delay + 0.05)
    assert game.level == level + 1


def test_boss_levels_and_endless_mode():
    cfg = Config()
    bosses = [n for n in range(1, 31) if level_spec(n, cfg).is_boss]
    assert bosses == [3, 6, 10, 15, 20, 25, 30]
    assert level_spec(15, cfg).boss_cycle == 1


# ----------------------------------------------------------------------
# Levels and flow
# ----------------------------------------------------------------------
def test_level_one_is_drones_only_and_levels_progress():
    game = Game(seed=4)
    game.start_run()
    seen = set()
    for _ in range(60 * 120):
        for enemy in game.enemies:
            seen.add(enemy.kind)
            enemy.alive = False
        game.enemy_shots.clear()
        game.step(IDLE)
        if game.level >= 2:
            break
    assert game.level == 2
    assert seen <= {"drone", "cargo"}


def test_waves_are_random_but_seeded():
    cfg = Config()
    spec = level_spec(5, cfg)
    import random
    a = build_wave(spec, 2, cfg, random.Random(1))
    b = build_wave(spec, 2, cfg, random.Random(1))
    c = build_wave(spec, 2, cfg, random.Random(2))
    key = lambda w: [(s.kind, s.pattern, round(s.start[0])) for s in w]  # noqa: E731
    assert key(a) == key(b) and key(a) != key(c)


def test_supply_pod_drops_two_pickups():
    game = new_game()
    pod = add_enemy(game, "cargo")
    game._damage_enemy(pod, 100)
    assert len(game.pickups) == 2


def test_game_over_is_emitted_once_per_run_and_restart_cleans_up():
    game = new_game(seed=5)
    first = game.run_id
    give(game, "rail")
    give(game, "magnet")
    activate(game, "overdrive")
    game.score = 4321
    game._drop_pickup(200, 200)
    for _ in range(3):
        game.ship.invulnerable_timer = 0
        game.ship.hurt_timer = 0
        game.ship.alive = True
        hit_ship(game, 1000)
    run(game, 5)
    events = game.drain_events()
    over = of_type(events, "game_over")
    assert len(over) == 1 and over[0]["seed"] == 5 and over[0]["level"] == 1
    game._end_run()
    assert of_type(game.drain_events(), "game_over") == []

    assert game.restart()
    assert game.state == PLAYING and game.run_id != first
    assert (game.score, game.level, game.lives) == (0, 1, 3)
    ship = game.ship
    assert ship.weapon is None and ship.buffs == {} and ship.hull == game.cfg.player.max_hull
    assert ship.inventory == []
    assert game.pickups == [] and game.enemy_shots == [] and game.boss is None
    assert game.shock_charge == 1.0 and game.high_score >= 4321


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
    before = (game.ticks, game.ship.weapon_time, game.ship.x)
    run(game, 3, InputState(right=True, fire=True))
    assert (game.ticks, game.ship.weapon_time, game.ship.x) == before
    assert game.set_paused(False)
    assert not game.set_paused(False)
    run(game, 0.5, InputState(right=True))
    assert game.ship.x > before[2]


def test_enemies_never_fire_from_point_blank():
    game = new_game()
    game.shots_cap = 99
    close = add_enemy(game, "striker", y=game.ship.y - game.cfg.enemy.safe_distance + 10)
    far = add_enemy(game, "striker", y=game.ship.y - game.cfg.enemy.safe_distance - 10)
    assert not game.can_enemy_fire(close)
    assert game.can_enemy_fire(far)


# ----------------------------------------------------------------------
# Timing and determinism
# ----------------------------------------------------------------------
def test_movement_and_timers_do_not_depend_on_frame_rate():
    results = []
    for fps in (30, 60, 144, 240):
        game = new_game()
        give(game, "spread")
        x0 = game.ship.x
        for _ in range(fps):
            game.advance(1 / fps, InputState(right=True))
        results.append((game.ship.x - x0, game.ship.weapon_time, game.ticks))
    step = 1 / game.cfg.display.sim_hz
    for moved, remaining, ticks in results:
        assert abs(ticks - results[0][2]) <= 1
        assert abs(moved - results[0][0]) <= game.cfg.player.speed * step + 1e-6
        assert abs(remaining - results[0][1]) <= step + 1e-6


def test_long_stalls_do_not_fast_forward():
    game = new_game()
    assert game.advance(5.0, IDLE) == game.cfg.display.max_steps_per_frame


def test_same_seed_and_inputs_give_the_same_run():
    def play(seed):
        game = Game(seed=seed)
        game.start_run()
        for _ in range(60 * 90):
            game.step(autopilot(game))
            if game.state != PLAYING:
                break
        return (game.score, game.level, game.wave, game.lives, game.kills, game.ticks,
                round(game.ship.hull, 3), [(e.kind, round(e.x, 2), round(e.y, 2)) for e in game.enemies])
    assert play(77) == play(77)
    assert play(77) != play(78)
