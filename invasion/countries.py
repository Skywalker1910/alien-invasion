"""Country list for the leaderboard (ISO 3166-1 codes + names).

Read from assets/flags/countries.json, which tools/fetch_flags.py wrote
next to the bundled flag images.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "assets", "flags", "countries.json")


def load_countries():
    try:
        with open(PATH, encoding="utf-8") as f:
            return [{"code": c["code"], "name": c["name"]} for c in json.load(f)]
    except (OSError, ValueError, KeyError):
        return []


def flag_path(code):
    return os.path.join(ROOT, "assets", "flags", f"{code}.png")
