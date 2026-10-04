"""Entry point for both desktop Python and the browser (Pygbag).

    python main.py                 play on desktop
    python main.py --seed 1234     play a repeatable run
    python build_web.py --serve    build and serve the browser version
"""
import asyncio

# Pygbag decides which packages to load by scanning this file's imports,
# so pygame must be imported here, not only inside the invasion package.
import pygame  # noqa: F401

from invasion.app import main

if __name__ == "__main__":
    asyncio.run(main())
