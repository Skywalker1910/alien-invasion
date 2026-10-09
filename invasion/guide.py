"""Orbi, the guide droid: the story briefing and first-run tips.

On a player's first run (or when they pick Tutorial from the menu) Orbi
flies in at the start of level 1, tells the story and explains the
controls. The game is frozen while the briefing is open. Afterwards Orbi
pops up with short, one-time tips the first time something new happens.

This is UI state only; drawing lives in render.py.
"""

STORY = [
    ("Year 2387", "Beep-boop! Hi pilot, I'm ORBI, your flight droid. Let me catch you up."),
    ("The Aurora Gate", "Behind us is the Aurora Gate, the last hyperspace gate. Every colony ship "
                        "comes home through it."),
    ("The Vex Armada", "The Vex Armada wants it dark. Their swarms and three motherships are "
                       "already crossing the Outer Rim."),
    ("Your mission", "You fly the Starling, the only fighter left at the gate. Hold the line "
                     "through ten sectors and take down their motherships!"),
    ("Flying", "Fly with the ARROW keys or WASD. Hold SPACE to shoot."),
    ("Capsules", "Wrecks drop capsules. Hexagons are weapons, circles are upgrades. Grab them "
                 "before they fall past you!"),
    ("Weapons", "Weapons go into your inventory. Switch with Q / E or keys 1-0. SHIFT fires a "
                "shockwave once it's charged."),
    ("Stay alive", "Watch your HEALTH heart. Armor and shields protect it. P or Esc pauses the "
                   "game. Good luck, pilot!"),
]

# One-time tips: game event type -> (tip key, text)
TIPS = {
    "pickup_dropped": ("capsule", "A capsule! Fly into it before it falls past you."),
    "player_damaged": ("damage", "Ouch! Keep an eye on your health heart."),
    "shock_ready": ("shock", "Shockwave charged! Press SHIFT when things get crowded."),
    "boss_spawned": ("boss", "A mothership! Shoot its glowing weapons - the hull is armored."),
    "cargo_spotted": ("cargo", "Supply pod! Shoot it for two capsules."),
    "dive_warning": ("dive", "That one's diving at you - move!"),
}
STORED_TIP = ("stored", "Weapon stored! Press Q / E to switch to it.")

TYPE_SPEED = 55.0          # characters per second
TIP_TIME = 4.5


class Guide:
    def __init__(self):
        self.briefing = False      # the blocking story / controls briefing
        self.page = 0
        self.chars = 0.0
        self.tips_enabled = False
        self.seen = set()
        self.tip = None            # text of the tip on screen
        self.tip_timer = 0.0
        self.t = 0.0               # animation clock
        self.enter = 0.0           # 0 -> 1 fly-in progress

    @property
    def blocking(self):
        return self.briefing

    def start(self):
        """Begin the briefing; tips stay on for the rest of this run."""
        self.briefing = True
        self.page = 0
        self.chars = 0.0
        self.enter = 0.0
        self.tips_enabled = True
        self.seen = set()
        self.tip = None

    def stop(self):
        """Run over or abandoned: no more tips."""
        self.briefing = False
        self.tips_enabled = False
        self.tip = None

    @property
    def text(self):
        return STORY[self.page][1]

    @property
    def title(self):
        return STORY[self.page][0]

    @property
    def typing(self):
        return self.chars < len(self.text)

    def advance(self):
        """Space / Enter / click: finish the line, or go to the next page.
        Returns True when the briefing has just ended."""
        if self.typing:
            self.chars = len(self.text)
            return False
        self.page += 1
        self.chars = 0.0
        if self.page >= len(STORY):
            self.briefing = False
            self.page = len(STORY) - 1
            return True
        return False

    def back(self):
        if self.page > 0:
            self.page -= 1
            self.chars = len(self.text)

    def skip(self):
        self.briefing = False
        return True

    def update(self, dt):
        self.t += dt
        self.enter = min(1.0, self.enter + dt * 2.5)
        if self.briefing:
            self.chars = min(len(self.text), self.chars + TYPE_SPEED * dt)
        if self.tip:
            self.tip_timer -= dt
            if self.tip_timer <= 0:
                self.tip = None

    def show_tip(self, key, text):
        if key in self.seen:
            return
        self.seen.add(key)
        self.tip = text
        self.tip_timer = TIP_TIME

    def on_events(self, events):
        if not self.tips_enabled or self.briefing:
            return
        for event in events:
            kind = event["type"]
            if kind == "pickup" and event.get("result") == "stored":
                self.show_tip(*STORED_TIP)
            elif kind in TIPS:
                self.show_tip(*TIPS[kind])
