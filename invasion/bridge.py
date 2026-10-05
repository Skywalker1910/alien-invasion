"""Optional bridge between the game and a JavaScript host page.

Only active when running in the browser under Pygbag (sys.platform is
"emscripten"). On desktop every call is a harmless no-op, so the rest of
the game never needs to check where it is running.

Game -> host: each event is a JSON object with a "type" field. It is
delivered three ways so hosts can pick whichever fits:
  * window.dispatchEvent(new CustomEvent("alien-invasion", {detail}))
  * window.AlienInvasionBridge.onEvent(detail), if the host set it
  * window.parent.postMessage({source: "alien-invasion", ...detail}, origin)
    when the game runs inside an iframe. origin defaults to "*" and can be
    pinned with the page's ?parentOrigin=https://example.com query string.

Host -> game: commands are JSON objects with a "type" field:
  * window.AlienInvasionBridge.send({type: "pause"})
  * or, from a parent page, iframe.contentWindow.postMessage(
        {target: "alien-invasion", type: "pause"}, "*")
    (only messages from the direct parent window are accepted)

The bridge never sends names, credentials or anything to the network.
"""
import json
import sys

IS_BROWSER = sys.platform == "emscripten"

_JS_SHIM = r"""
(function () {
  if (window.AlienInvasionBridge) return;
  var params = new URLSearchParams(window.location.search);
  var bridge = {
    parentOrigin: params.get("parentOrigin") || "*",
    onEvent: null,
    _inbox: [],
    send: function (cmd) {
      bridge._inbox.push(typeof cmd === "string" ? cmd : JSON.stringify(cmd));
    },
    _drain: function () {
      var out = JSON.stringify(bridge._inbox);
      bridge._inbox.length = 0;
      return out;
    },
    _emit: function (json) {
      var detail = JSON.parse(json);
      try { window.dispatchEvent(new CustomEvent("alien-invasion", { detail: detail })); } catch (e) {}
      try { if (typeof bridge.onEvent === "function") bridge.onEvent(detail); } catch (e) {}
      try {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage(Object.assign({ source: "alien-invasion" }, detail), bridge.parentOrigin);
        }
      } catch (e) {}
    }
  };
  window.addEventListener("message", function (e) {
    var d = e.data;
    if (e.source === window.parent && d && d.target === "alien-invasion") bridge.send(d);
  });
  window.AlienInvasionBridge = bridge;
})();
"""

# Game events forwarded to the host as-is (besides ready / state).
FORWARDED_EVENTS = {
    "run_started", "level_started", "wave_started", "level_cleared", "boss_spawned",
    "boss_stage", "boss_defeated", "player_destroyed", "pickup", "paused", "resumed",
    "game_over", "run_abandoned", "weapon_switched", "upgrade_activated",
}

# Commands the host may send. Anything else is ignored.
COMMANDS = {"pause", "resume", "input", "special", "switch", "select", "activate", "start",
            "restart"}


class NullBridge:
    """Desktop stand-in: accepts everything, does nothing."""

    active = False

    def emit(self, event):
        pass

    def poll(self):
        return []


class BrowserBridge:
    active = True

    def __init__(self):
        import platform  # Pygbag's module exposing the JS window
        self.window = platform.window
        self.window.eval(_JS_SHIM)

    def emit(self, event):
        payload = json.dumps(json.dumps(event, separators=(",", ":")))
        self.window.eval(f"window.AlienInvasionBridge._emit({payload})")

    def poll(self):
        raw = self.window.eval("window.AlienInvasionBridge._drain()")
        commands = []
        for item in json.loads(str(raw)):
            try:
                cmd = json.loads(item)
            except (TypeError, ValueError):
                continue
            if isinstance(cmd, dict) and cmd.get("type") in COMMANDS:
                commands.append(cmd)
        return commands


class SafeBridge:
    """Wraps a bridge so a failing host connection never crashes the game."""

    def __init__(self, inner):
        self.inner = inner
        self.active = inner.active

    def _disable(self, exc):
        print(f"[bridge] disabled after error: {exc!r}")
        self.inner = NullBridge()
        self.active = False

    def emit(self, event):
        try:
            self.inner.emit(event)
        except Exception as exc:  # noqa: BLE001 - host errors must not kill the game
            self._disable(exc)

    def poll(self):
        try:
            return self.inner.poll()
        except Exception as exc:  # noqa: BLE001
            self._disable(exc)
            return []


def create_bridge():
    if not IS_BROWSER:
        return SafeBridge(NullBridge())
    try:
        return SafeBridge(BrowserBridge())
    except Exception as exc:  # noqa: BLE001
        print(f"[bridge] unavailable: {exc!r}")
        return SafeBridge(NullBridge())


class StateReporter:
    """Sends a compact state event whenever it changes. Changes to lives,
    level, wave, pause or game state go out at once; fast-changing values
    (score, hull, ammo, timers) at most every min_interval seconds."""

    IMMEDIATE = ("state", "paused", "level", "wave", "lives", "run_id")
    FIELDS = IMMEDIATE + ("score", "multiplier", "hull", "armor", "shield", "weapon", "inventory",
                          "selected", "buffs",
                          "shock", "boss")

    def __init__(self, bridge, min_interval=0.25):
        self.bridge = bridge
        self.min_interval = min_interval
        self.last = None
        self.since = 0.0

    def update(self, snapshot, frame_dt):
        self.since += frame_dt
        state = {k: snapshot[k] for k in self.FIELDS}
        if state == self.last:
            return
        urgent = self.last is None or any(state[k] != self.last[k] for k in self.IMMEDIATE)
        if not urgent and self.since < self.min_interval:
            return
        self.last = state
        self.since = 0.0
        self.bridge.emit(dict(state, type="state"))
