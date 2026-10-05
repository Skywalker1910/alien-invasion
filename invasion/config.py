"""Every tunable number and every piece of game content lives here.

Units used throughout:
  * distances and sizes are logical pixels (the playfield is always
    DisplayConfig.width x height, whatever the real window size is)
  * speeds are pixels per second
  * durations, cooldowns and intervals are seconds
  * damage and hit points are plain numbers (the basic blaster does 1)
  * chances are probabilities between 0 and 1

Nothing in this file depends on pygame, so it can be imported anywhere.
"""
from dataclasses import dataclass, field

WHITE = (240, 244, 255)
GREEN = (110, 255, 150)
CYAN = (90, 220, 255)
YELLOW = (255, 225, 90)
ORANGE = (255, 160, 60)
RED = (255, 80, 90)
VIOLET = (190, 120, 255)
PINK = (255, 110, 200)
STEEL = (170, 185, 210)
GOLD = (255, 200, 80)
TEAL = (80, 240, 210)


@dataclass
class DisplayConfig:
    width: int = 960
    height: int = 640
    title: str = "Alien Invasion"
    fps_cap: int = 60
    # The simulation always advances in fixed steps of 1 / sim_hz seconds,
    # however fast frames are drawn. That keeps movement, cooldowns and
    # spawns frame-rate independent and makes seeded runs repeatable.
    sim_hz: int = 60
    # After a long stall (tab in background, window drag) drop the backlog
    # instead of fast-forwarding through it.
    max_steps_per_frame: int = 6
    hud_height: int = 36


@dataclass
class PlayerConfig:
    size: tuple = (48, 54)
    hitbox_scale: float = 0.55         # forgiving hitbox, smaller than the sprite
    speed: float = 560.0
    top_zone: float = 0.52             # ship can fly up to this fraction of the screen
    bottom_margin: int = 58            # room for the bottom HUD bar
    max_hull: float = 100.0
    max_armor: float = 100.0
    max_shield: int = 10               # shield charges (each blocks one hit)
    inventory_slots: int = 10          # stored weapons + timed upgrades
    start_lives: int = 3
    max_lives: int = 5
    hurt_iframes: float = 0.35         # after taking damage, ignore damage this long
    respawn_delay: float = 1.0
    invulnerable_time: float = 2.0     # blinking grace period after respawning
    game_over_delay: float = 1.6
    # Basic blaster, always available, unlimited.
    blaster_cooldown: float = 0.12
    blaster_damage: float = 1.0
    blaster_speed: float = 980.0
    blaster_size: tuple = (4, 18)
    # Shockwave (Shift): an expanding ring that shreds anything it passes,
    # then needs time to recharge.
    shock_recharge: float = 16.0
    shock_damage: float = 20.0             # kills a guardian, not a dreadnought
    shock_part_damage: float = 10.0    # damage to boss weapons inside the ring
    shock_radius: float = 520.0
    shock_speed: float = 1300.0
    # Combo: kills in quick succession raise the score multiplier.
    combo_window: float = 2.2
    combo_step: int = 6                # kills per +1 multiplier
    combo_max: int = 5


@dataclass
class WeaponSpec:
    label: str
    color: tuple
    ammo: int = 0                      # limited shots (0 = limited by time instead)
    duration: float = 0.0              # limited time (seconds of use)
    cooldown: float = 0.2
    damage: float = 1.0
    speed: float = 900.0
    count: int = 1                     # projectiles per shot
    angle: float = 0.0                 # degrees between projectiles / jitter
    pierce: int = 0                    # extra enemies a projectile passes through
    splash_radius: float = 0.0
    splash_damage: float = 0.0
    turn_rate: float = 0.0             # homing, radians per second
    chain: int = 0                     # extra targets for chain lightning
    chain_range: float = 0.0
    fuse: float = 0.0                  # flak: seconds before bursting
    shrapnel: int = 0
    size: tuple = (4, 16)


def default_weapons():
    return {
        "spread": WeaponSpec("Spread Shot", YELLOW, duration=12.0, cooldown=0.15, damage=1.0,
                             speed=920.0, count=5, angle=9.0, size=(5, 14)),
        "rapid": WeaponSpec("Rapid Fire", ORANGE, ammo=240, cooldown=0.05, damage=1.0,
                            speed=1150.0, angle=4.0, size=(3, 14)),
        "rail": WeaponSpec("Railgun", CYAN, ammo=26, cooldown=0.36, damage=6.0, speed=2100.0,
                           pierce=99, size=(6, 44)),
        "laser": WeaponSpec("Laser Beam", PINK, duration=7.0, damage=18.0, size=(12, 0)),
        "homing": WeaponSpec("Homing Missiles", RED, ammo=40, cooldown=0.24, damage=3.0,
                             speed=560.0, count=2, turn_rate=7.0, size=(6, 14)),
        "plasma": WeaponSpec("Plasma Cannon", VIOLET, ammo=16, cooldown=0.42, damage=7.0,
                             speed=620.0, splash_radius=95.0, splash_damage=4.0, size=(18, 18)),
        "chain": WeaponSpec("Chain Lightning", TEAL, ammo=30, cooldown=0.24, damage=3.0,
                            chain=4, chain_range=240.0),
        "flak": WeaponSpec("Flak Burst", GOLD, ammo=32, cooldown=0.3, damage=2.0, speed=720.0,
                           fuse=0.3, shrapnel=10, size=(9, 9)),
    }


@dataclass
class PickupSpec:
    label: str
    color: tuple
    weight: float                      # relative drop weight
    value: float = 0.0
    duration: float = 0.0
    storable: bool = False             # goes into the inventory, activated by the player


def default_pickups():
    return {
        "repair": PickupSpec("Repair", GREEN, 16, value=35),           # +35 hull
        "shield": PickupSpec("Shield", CYAN, 12, value=6),              # blocks 6 hits
        "armor": PickupSpec("Armor", STEEL, 10, value=50),             # +50 armor
        "shock": PickupSpec("Shock Charge", WHITE, 7),                  # recharge shockwave
        "wingmen": PickupSpec("Wingmen", TEAL, 7, duration=15, storable=True),
        "overdrive": PickupSpec("Overdrive", PINK, 6, duration=8, storable=True),  # x2 dmg
        "magnet": PickupSpec("Magnet", GOLD, 6, duration=14, storable=True),  # pulls pickups
        "life": PickupSpec("Extra Ship", GREEN, 2),
    }


@dataclass
class DropConfig:
    weapon_weight: float = 6.0         # weight of each of the 8 weapons
    max_on_screen: int = 4
    fall_speed: float = 150.0
    sway: float = 22.0
    pity_time: float = 8.0             # no drop for this long -> next kill drops
    low_hull_repair_boost: float = 2.5 # repair weight multiplier below half hull
    magnet_radius: float = 340.0
    magnet_speed: float = 620.0
    bonus_points: int = 250            # e.g. repair at full hull


@dataclass
class EnemySpec:
    label: str
    hp: float
    points: int
    size: tuple
    speed: float
    ram_damage: float
    fire: str = "none"                 # none, single, twin, beam, spread, missile
    fire_interval: float = 3.0
    bullet_speed: float = 320.0
    bullet_damage: float = 8.0
    drop_chance: float = 0.05
    threat: int = 1                    # wave budget cost
    hazard: bool = False


def default_enemies():
    return {
        "drone": EnemySpec("Drone", 1, 40, (36, 30), 300, 14, "single", 3.0, 330, 7, 0.06, 1),
        "wasp": EnemySpec("Wasp", 2, 70, (30, 34), 520, 26, "none", drop_chance=0.04, threat=1),
        "striker": EnemySpec("Striker", 4, 110, (44, 38), 330, 18, "twin", 2.1, 380, 8, 0.10, 2),
        "lancer": EnemySpec("Lancer", 8, 220, (44, 52), 300, 20, "beam", 3.2, 0, 24, 0.14, 3),
        "guardian": EnemySpec("Guardian", 16, 380, (66, 56), 160, 28, "spread", 2.4, 330, 9, 0.22, 5),
        "dreadnought": EnemySpec("Dreadnought", 38, 1000, (100, 82), 95, 40, "missile", 2.6, 250, 15,
                                 1.0, 9),
        "cargo": EnemySpec("Supply Pod", 6, 150, (58, 34), 210, 0, drop_chance=1.0, threat=0),
        "asteroid": EnemySpec("Asteroid", 5, 25, (48, 48), 190, 22, drop_chance=0.03, hazard=True,
                              threat=0),
        "mine": EnemySpec("Mine", 2, 30, (28, 28), 120, 0, drop_chance=0.03, hazard=True, threat=0),
    }


@dataclass
class EnemyRules:
    hit_flash: float = 0.08
    charge_time: float = 0.3           # glow before an ordinary shot
    safe_distance: float = 140.0       # never shoot from closer than this to the ship
    shots_cap: int = 8                 # enemy shots on screen, level 1
    shots_cap_per_level: int = 2
    shots_cap_max: int = 26
    beam_telegraph: float = 0.8
    beam_time: float = 0.45
    beam_width: int = 16
    missile_turn: float = 2.0
    missile_life: float = 4.5
    mine_trigger: float = 85.0
    mine_fuse: float = 0.45
    mine_radius: float = 90.0
    mine_damage: float = 24.0
    wasp_aim: float = 0.4
    # Per-level scaling (applied to level n as 1 + rate * (n - 1), capped)
    hp_per_level: float = 0.07
    fire_rate_per_level: float = 0.05
    fire_rate_max: float = 1.9
    bullet_speed_per_level: float = 0.03
    bullet_speed_max: float = 1.45


@dataclass
class HardpointSpec:
    kind: str                          # cannon, spread, missile, laser, hangar, core
    offset: tuple                      # from the boss center
    hp: float
    stage: int                         # active (and vulnerable) in this stage
    interval: float


@dataclass
class BossSpec:
    label: str
    size: tuple
    speed: float
    points: int
    hardpoints: list


def default_bosses():
    hp = HardpointSpec
    return [
        BossSpec("Harbinger", (420, 150), 70, 5000, [
            hp("cannon", (-150, 28), 22, 1, 1.9), hp("cannon", (150, 28), 22, 1, 1.9),
            hp("spread", (-68, 50), 26, 2, 2.2), hp("spread", (68, 50), 26, 2, 2.2),
            hp("core", (0, 38), 45, 3, 1.6),
        ]),
        BossSpec("Leviathan", (560, 170), 60, 9000, [
            hp("cannon", (-226, 40), 26, 1, 1.8), hp("cannon", (226, 40), 26, 1, 1.8),
            hp("missile", (-128, 22), 24, 1, 2.8), hp("missile", (128, 22), 24, 1, 2.8),
            hp("laser", (-62, 62), 34, 2, 4.0), hp("laser", (62, 62), 34, 2, 4.0),
            hp("hangar", (0, 18), 34, 2, 5.5),
            hp("core", (0, 56), 70, 3, 1.4),
        ]),
        BossSpec("Overmind", (720, 190), 55, 15000, [
            hp("cannon", (-300, 44), 30, 1, 1.7), hp("cannon", (300, 44), 30, 1, 1.7),
            hp("spread", (-200, 60), 32, 1, 2.1), hp("spread", (200, 60), 32, 1, 2.1),
            hp("hangar", (0, 16), 40, 1, 5.0),
            hp("laser", (-110, 70), 38, 2, 3.6), hp("laser", (110, 70), 38, 2, 3.6),
            hp("missile", (-250, 18), 30, 2, 2.4), hp("missile", (250, 18), 30, 2, 2.4),
            hp("core", (0, 72), 100, 3, 1.2),
        ]),
    ]


@dataclass
class BossRules:
    levels: tuple = (3, 6, 10)         # boss levels; after 10 a boss every 5 levels
    endless_every: int = 5
    endless_hp_per_cycle: float = 0.5
    enter_speed: float = 90.0
    stage_pause: float = 1.4           # invulnerable breather between stages
    stage_rage: tuple = (1.0, 0.85, 0.72)  # fire interval multiplier per stage
    burst_count: int = 3
    burst_gap: float = 0.14
    cannon_bullet: tuple = (400.0, 10.0)   # speed, damage
    spread_bullet: tuple = (330.0, 9.0)
    spread_count: int = 5
    spread_step: float = 13.0
    missile: tuple = (250.0, 16.0)
    laser_damage: float = 28.0
    hangar_minions: int = 2
    minion_cap: int = 6
    core_ring: int = 12
    core_bullet: tuple = (300.0, 10.0)
    part_points: int = 400


@dataclass
class FlowConfig:
    level_banner: float = 2.0
    boss_banner: float = 2.6
    level_clear_delay: float = 2.0
    wave_max_time: float = 13.0        # next wave comes even if enemies remain
    wave_trickle: int = 2              # ...or as soon as this few are left


@dataclass
class Config:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    weapons: dict = field(default_factory=default_weapons)
    pickups: dict = field(default_factory=default_pickups)
    drops: DropConfig = field(default_factory=DropConfig)
    enemies: dict = field(default_factory=default_enemies)
    enemy: EnemyRules = field(default_factory=EnemyRules)
    bosses: list = field(default_factory=default_bosses)
    boss: BossRules = field(default_factory=BossRules)
    flow: FlowConfig = field(default_factory=FlowConfig)
