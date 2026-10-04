"""Desktop launcher, kept so `python alien_invasion.py` still works.

The game itself lives in the invasion/ package; main.py is the shared
entry point that Pygbag also uses for the browser build.
"""
import asyncio

from invasion.app import main

if __name__ == "__main__":
    asyncio.run(main())
