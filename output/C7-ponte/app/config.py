# -*- coding: utf-8 -*-
"""Paths, environment and run mode (live Claude vs offline demo) for Ponte."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
CORE_DIR = APP_DIR / "core"
PROMPTS_DIR = APP_DIR / "prompts"
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
FIXTURES_DIR = ROOT / "fixtures"
DEMO_FIXTURE = FIXTURES_DIR / "demo_ahmed.json"

# The shared core modules import each other as top-level modules (e.g. "import local_index").
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))


def _load_env() -> None:
    """Load the nearest .env walking up from the project folder (and from the cwd).

    The project .env wins over variables inherited from the shell: when the app is launched
    from inside Claude Code the environment may already contain CLAUDE_EFFORT=high.
    """
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:  # pragma: no cover
        return
    candidates = []
    for base in [ROOT, *ROOT.parents]:
        f = base / ".env"
        if f.is_file():
            candidates.append(f)
            break
    found = find_dotenv(usecwd=True)
    if found:
        candidates.append(Path(found))
    for f in candidates:
        load_dotenv(f, override=True)
        break


_load_env()

os.environ.setdefault("MILANO_INDEX_DIR", str(DATA_DIR / "index"))
os.environ.setdefault("MILANO_CACHE_DIR", str(DATA_DIR / "cache"))

import claude_client as cc  # noqa: E402  (needs sys.path above)
import local_index  # noqa: E402
import milano_tools as mt  # noqa: E402

local_index.set_index_dir(DATA_DIR / "index")
mt.configure(cache_dir=DATA_DIR / "cache")

TODAY_IT = "3 ottobre 2026"
RETRIEVED_ON = "2026-10-03"
SESSION_TTL_SECONDS = int(os.environ.get("PONTE_TTL_SECONDS", str(2 * 60 * 60)))

DEMO_BANNER = ("Modalità demo offline: risposte registrate da Claude il 3/10/2026. "
               "Aggiungi ANTHROPIC_API_KEY nel .env per l'uso reale.")


def model() -> str:
    return cc.default_model()


def effort() -> str:
    return cc.default_effort()


def correction_effort() -> str:
    # The correction step is a short translation: a lower effort keeps the operator loop fast.
    return os.environ.get("CLAUDE_EFFORT_CORREZIONE", "").strip() or "low"


def run_mode() -> str:
    """'live' when credentials exist (unless PONTE_MODE=demo), otherwise 'demo'."""
    forced = os.environ.get("PONTE_MODE", "auto").strip().lower()
    if forced == "demo":
        return "demo"
    if forced == "live":
        return "live" if cc.has_credentials() else "demo"
    return "live" if cc.has_credentials() else "demo"
