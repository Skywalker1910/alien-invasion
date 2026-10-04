"""Every tunable number in the game lives here.

Units used throughout:
  * distances and sizes are logical pixels (the playfield is always
    Display.width x Display.height, whatever the real window size is)
  * speeds are pixels per second
  * durations, cooldowns and intervals are seconds
  * chances are probabilities between 0 and 1

Nothing in this file depends on pygame, so it can be imported anywhere.
"""
from dataclasses import dataclass, field


@dataclass
class DisplayConfig:
    width: int = 960
    height: int = 640
    title: str = "Alien Invasion"
    fps_cap: int = 60
    # The simulation always advances in fixed steps of 1 / sim_hz seconds,
    # no matter how fast frames are drawn. That keeps movement, cooldowns
    # and spawns frame-rate independent and makes seeded runs repeatable.
    sim_hz: int = 120
    # After a long stall (tab in background, window drag) drop the backlog
    # instead of fast-forwarding through it.
    max_steps_per_frame: int = 12
    hud_height: int = 40


@dataclass
class PlayerConfig:
    size: tuple = (52, 42)
    hitbox_scale: float = 0.7          # forgiving hitbox, smaller than the sprite
    bottom_margin: int = 14
    speed: float = 380.0
    start_lives: int = 3               # 3 lives = exactly 3 hits
    max_lives: int = 5                 # extra-life pickups never go above this
    fire_cooldown: float = 0.24
    max_bullets: int = 4               # normal weapon, player bullets on screen
    bullet_speed: float = 760.0
    bullet_size: tuple = (4, 16)
    respawn_delay: float = 1.2         # ship is gone this long after a hit
    invulnerable_time: float = 2.0     # blinking grace period after respawning
    game_over_delay: float = 1.4       # let the last explosion play out
    # Special attack (Shift): a shockwave that clears every enemy bullet and
    # damages aliens within special_radius of the ship (and chips the boss).
    special_start: int = 2
    special_max: int = 3
    special_cooldown: float = 1.0
    special_damage: int = 2
    special_radius: float = 300.0
    special_boss_fraction: float = 0.12
    special_per_boss: int = 1          # charges gained for beating a boss


@dataclass
class EnemyType:
    hp: int
    points: int
    size: tuple
    tint: tuple
    drop_chance: float
    fire_weight: float                 # how likely this type is picked to shoot


@dataclass
class EnemyConfig:
    standard: EnemyType = field(default_factory=lambda: EnemyType(
        hp=1, points=50, size=(40, 38), tint=(130, 255, 130),
        drop_chance=0.05, fire_weight=1.0))
    armored: EnemyType = field(default_factory=lambda: EnemyType(
        hp=3, points=150, size=(44, 42), tint=(140, 180, 255),
        drop_chance=0.14, fire_weight=1.5))
    agile: EnemyType = field(default_factory=lambda: EnemyType(
        hp=1, points=120, size=(34, 32), tint=(255, 175, 80),
        drop_chance=0.10, fire_weight=0.5))

    # Formation grid
    grid_cols: int = 10
    grid_rows: int = 5
    slot_spacing: tuple = (66, 52)
    top_margin: int = 78

    # Formation marching
    march_speed: float = 38.0
    march_speed_per_wave: float = 5.0
    march_speed_max: float = 95.0
    march_thin_bonus: float = 55.0     # extra speed as the fleet thins out
    drop_distance: float = 16.0
    side_margin: int = 12

    # Agile dives: telegraph (flash + shake), then a swaying dive
    dive_first_wave: int = 3
    dive_interval: float = 5.0
    dive_interval_per_wave: float = -0.35
    dive_interval_min: float = 2.0
    dive_telegraph: float = 0.75
    dive_speed: float = 210.0
    dive_speed_per_wave: float = 8.0
    dive_speed_max: float = 300.0
    dive_sway: float = 70.0
    dive_sway_hz: float = 0.9
    return_speed: float = 260.0
    max_divers: int = 3

    hit_flash: float = 0.12


@dataclass
class EnemyFireConfig:
    bullet_size: tuple = (6, 14)
    bullet_speed: float = 230.0
    bullet_speed_per_wave: float = 10.0
    bullet_speed_max: float = 330.0
    interval: float = 1.7              # seconds between shots on wave 1
    interval_per_wave: float = -0.12
    interval_min: float = 0.6
    max_bullets: int = 2               # enemy bullets on screen on wave 1
    max_bullets_per_wave: float = 0.5
    max_bullets_cap: int = 6
    telegraph: float = 0.35            # shooter glows this long before firing
    aimed_from_wave: int = 4           # armored aliens aim from this wave on
    aimed_max_angle: float = 22.0      # degrees from straight down
    # Never fire from closer than this (vertically) to the ship, so every
    # shot leaves at least ~0.5 s to react.
    safe_distance: float = 170.0
    wave_start_grace: float = 1.0      # extra quiet time after the banner


@dataclass
class BossConfig:
    every: int = 5                     # waves 5, 10, 15, ... are boss waves
    size: tuple = (150, 140)
    tint: tuple = (255, 90, 120)
    y: float = 150.0
    speed: float = 110.0
    speed_phase2: float = 160.0
    hp: int = 40
    hp_per_boss: int = 25
    points: int = 2500
    points_per_boss: int = 1000
    pattern_cooldown: float = 1.7
    pattern_cooldown_phase2: float = 1.15
    phase2_at: float = 0.5             # fraction of HP left
    telegraph: float = 0.6
    bullet_speed: float = 250.0
    burst_count: int = 3
    burst_gap: float = 0.2
    fan_count: int = 5
    fan_step: float = 12.0             # degrees between fan bullets
    escort_from_boss: int = 2          # second boss onward brings escorts
    escort_count: int = 6


@dataclass
class PowerUpConfig:
    size: tuple = (26, 26)
    fall_speed: float = 120.0
    max_on_screen: int = 2
    min_gap: float = 5.0               # seconds between random drops
    weights: dict = field(default_factory=lambda: {
        "shield": 35, "spread": 30, "pierce": 25, "life": 10})
    durations: dict = field(default_factory=lambda: {
        "shield": 8.0, "spread": 10.0, "pierce": 10.0})
    spread_angle: float = 11.0         # degrees between spread bullets
    spread_max_bullets: int = 12
    pierce_hits: int = 3               # enemies one piercing bullet can pass through
    life_cap_bonus: int = 1000         # score instead of a life when at max lives
    boss_drop_guaranteed: bool = True
    expiry_warning: float = 2.0        # HUD blinks during the last seconds


@dataclass
class ScoreConfig:
    wave_clear_bonus: int = 100        # multiplied by the wave number
    bullet_cancel: int = 5             # shooting an enemy bullet out of the air


@dataclass
class FlowConfig:
    wave_banner: float = 1.6
    boss_banner: float = 2.4
    wave_clear_delay: float = 1.4


@dataclass
class Config:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    player: PlayerConfig = field(default_factory=PlayerConfig)
    enemy: EnemyConfig = field(default_factory=EnemyConfig)
    enemy_fire: EnemyFireConfig = field(default_factory=EnemyFireConfig)
    boss: BossConfig = field(default_factory=BossConfig)
    powerups: PowerUpConfig = field(default_factory=PowerUpConfig)
    score: ScoreConfig = field(default_factory=ScoreConfig)
    flow: FlowConfig = field(default_factory=FlowConfig)

    def enemy_type(self, kind):
        return getattr(self.enemy, kind)
