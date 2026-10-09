"""Local save data: the leaderboard and a few settings.

One small interface, three backends:
  * SQLiteStore        desktop: a SQLite database in save/alien_invasion.db
  * LocalStorageStore  browser (Pygbag): JSON in the page's localStorage,
                       because files written in the browser don't persist
  * MemoryStore        tests, or a fallback if the others fail

A leaderboard entry is: pilot name, country code, score, level, plus the
run id and seed so a run can be traced back. Names are game names only:
short, limited to plain characters, never a real-name requirement.
"""
import json
import os
import re
import time

from .bridge import IS_BROWSER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "save", "alien_invasion.db")
STORAGE_KEY = "alien_invasion.v1"
NAME_MAX = 14
KEEP = 200                       # entries kept per store

_NAME_OK = re.compile(r"[^A-Za-z0-9 _\-.]")


def clean_name(name):
    """Letters, digits, space, _ - . only; trimmed to NAME_MAX characters."""
    name = _NAME_OK.sub("", str(name or "")).strip()[:NAME_MAX].strip()
    return name or "Pilot"


def clean_country(code, valid_codes):
    code = str(code or "").lower()
    return code if code in valid_codes else ""


def _sort_key(entry):
    return (-entry["score"], entry["date"], entry["id"])


class MemoryStore:
    kind = "memory"

    def __init__(self):
        self.scores = []
        self.settings = {}
        self._next = 1

    def add_score(self, name, country, score, level, run_id="", seed=0):
        entry = {"id": self._next, "name": name, "country": country, "score": int(score),
                 "level": int(level), "run_id": run_id, "seed": int(seed), "date": time.time()}
        self._next += 1
        self.scores.append(entry)
        self.scores.sort(key=_sort_key)
        del self.scores[KEEP:]
        self._save()
        return entry["id"]

    def top(self, n=10):
        return [dict(e) for e in sorted(self.scores, key=_sort_key)[:n]]

    def rank(self, entry_id):
        for i, entry in enumerate(sorted(self.scores, key=_sort_key)):
            if entry["id"] == entry_id:
                return i + 1
        return None

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self._save()

    def _save(self):
        pass


class LocalStorageStore(MemoryStore):
    """Browser: everything in one localStorage key as JSON."""

    kind = "localStorage"

    def __init__(self, window):
        super().__init__()
        self.storage = window.localStorage
        raw = self.storage.getItem(STORAGE_KEY)
        if raw:
            try:
                data = json.loads(str(raw))
                self.scores = list(data.get("scores", []))
                self.settings = dict(data.get("settings", {}))
                self._next = max([e["id"] for e in self.scores] + [0]) + 1
            except (ValueError, TypeError, KeyError):
                pass

    def _save(self):
        self.storage.setItem(STORAGE_KEY, json.dumps({"scores": self.scores, "settings": self.settings}))


class SQLiteStore:
    """Desktop: a small SQLite database."""

    kind = "sqlite"

    def __init__(self, path=DB_PATH):
        import sqlite3  # imported here: the browser build may not ship it
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS scores (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT    NOT NULL,
                country TEXT    NOT NULL DEFAULT '',
                score   INTEGER NOT NULL,
                level   INTEGER NOT NULL,
                run_id  TEXT    NOT NULL DEFAULT '',
                seed    INTEGER NOT NULL DEFAULT 0,
                date    REAL    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS scores_by_score ON scores (score DESC, date ASC);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.db.commit()

    def add_score(self, name, country, score, level, run_id="", seed=0):
        cur = self.db.execute(
            "INSERT INTO scores (name, country, score, level, run_id, seed, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, country, int(score), int(level), run_id, int(seed), time.time()))
        self.db.execute("DELETE FROM scores WHERE id NOT IN "
                        "(SELECT id FROM scores ORDER BY score DESC, date ASC, id ASC LIMIT ?)", (KEEP,))
        self.db.commit()
        return cur.lastrowid

    def top(self, n=10):
        rows = self.db.execute("SELECT id, name, country, score, level, run_id, seed, date FROM scores "
                               "ORDER BY score DESC, date ASC, id ASC LIMIT ?", (n,)).fetchall()
        keys = ("id", "name", "country", "score", "level", "run_id", "seed", "date")
        return [dict(zip(keys, row)) for row in rows]

    def rank(self, entry_id):
        row = self.db.execute("SELECT score, date, id FROM scores WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            return None
        score, date, eid = row
        better = self.db.execute(
            "SELECT COUNT(*) FROM scores WHERE score > ? OR (score = ? AND (date < ? OR (date = ? AND id < ?)))",
            (score, score, date, date, eid)).fetchone()[0]
        return better + 1

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self.db.commit()


def open_store():
    """The best store available here; never raises."""
    try:
        if IS_BROWSER:
            import platform
            return LocalStorageStore(platform.window)
        return SQLiteStore()
    except Exception as exc:  # noqa: BLE001 - saving must never break the game
        print(f"[storage] using memory only: {exc!r}")
        return MemoryStore()
