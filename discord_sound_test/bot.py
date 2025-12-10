"""Package shim that re-exports the project's top-level `bot` module.

This file intentionally avoids duplicating implementation. Edit the
top-level `bot.py` (the canonical source) and this shim will expose the
same symbols under `discord_sound_test.bot` for tests and tooling.
"""

import importlib

# Import the top-level module and re-export its public symbols. Avoid using
# `from bot import *` so static analyzers can reason about the shim.
_bot = importlib.import_module("bot")
for _name in dir(_bot):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_bot, _name)

__all__ = [n for n in dir(_bot) if not n.startswith("_")]
