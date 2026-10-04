"""Build (or serve) the browser version with Pygbag.

    python build_web.py           build into build/web/
    python build_web.py --serve   build and serve on http://localhost:8000

Only the files the game needs (main.py, invasion/, assets/) are copied into
a clean staging folder first, so virtualenvs, tests and caches never end up
in the web bundle.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "build" / "stage" / "alien_invasion"
OUTPUT = ROOT / "build" / "web"
INCLUDE = ["main.py", "invasion", "assets"]


def stage():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    for name in INCLUDE:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, STAGE / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, STAGE / name)


def main():
    serve = "--serve" in sys.argv[1:]
    stage()
    cmd = [sys.executable, "-m", "pygbag", "--ume_block", "0", "--title", "Alien Invasion"]
    if not serve:
        cmd.append("--build")
    cmd.append(str(STAGE))
    print("Running:", " ".join(cmd))
    if serve:
        # pygbag serves straight from the staging folder until stopped.
        return subprocess.call(cmd)
    result = subprocess.call(cmd)
    if result == 0:
        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        shutil.copytree(STAGE / "build" / "web", OUTPUT)
        print(f"Web build ready in {OUTPUT}")
    return result


if __name__ == "__main__":
    sys.exit(main())
