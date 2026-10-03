"""Shared core copied from the team's tested toolkit (comments in Italian, kept as-is).

The core modules import each other with absolute imports (e.g. `import local_index`),
so this package puts its own folder on sys.path before anything else imports them.
"""
import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
