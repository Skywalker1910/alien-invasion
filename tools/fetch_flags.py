"""Downloads country flags into assets/flags/ (run once, results are committed).

    python tools/fetch_flags.py

Flags come from flagcdn.com (images of national flags, which are public
domain). Only ISO 3166-1 two-letter codes are kept. The game never
downloads anything at runtime; it only reads the bundled PNGs and
assets/flags/countries.json.
"""
import json
import os
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "flags")
CODES_URL = "https://flagcdn.com/en/codes.json"
FLAG_URL = "https://flagcdn.com/w40/{code}.png"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "alien-invasion-asset-fetch"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    codes = json.loads(fetch(CODES_URL))
    countries = sorted(((code, name) for code, name in codes.items() if len(code) == 2),
                       key=lambda item: item[1])
    for code, _ in countries:
        path = os.path.join(OUT, f"{code}.png")
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(fetch(FLAG_URL.format(code=code)))
            time.sleep(0.05)
    with open(os.path.join(OUT, "countries.json"), "w", encoding="utf-8") as f:
        json.dump([{"code": c, "name": n} for c, n in countries], f, ensure_ascii=False, indent=0)
    print(f"{len(countries)} flags in {OUT}")


if __name__ == "__main__":
    main()
