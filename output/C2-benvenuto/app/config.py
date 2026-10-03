"""Runtime configuration: paths, .env loading, demo-mode detection."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
INDEX_DIR = DATA_DIR / "index"
CACHE_DIR = DATA_DIR / "cache"
FIXTURES_DIR = ROOT / "fixtures"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
STATIC_DIR = ROOT / "static"

# Load the nearest .env walking up from the current working directory first,
# then from the project folder (so a parent folder's .env is found too).
# Existing environment variables are never overridden.
load_dotenv(find_dotenv(usecwd=True), override=False)
_p = ROOT
for _ in range(4):
    if (_p / ".env").exists():
        load_dotenv(_p / ".env", override=False)
        break
    _p = _p.parent

os.environ.setdefault("MILANO_CACHE_DIR", str(CACHE_DIR))
os.environ.setdefault("MILANO_INDEX_DIR", str(INDEX_DIR))

import app.core  # noqa: E402,F401  (puts app/core on sys.path)
import milano_tools as mt  # noqa: E402

mt.configure(cache_dir=CACHE_DIR, index_dir=INDEX_DIR)

DEMO_BANNER_IT = ("Modalità demo offline: risposte registrate da Claude il 3/10/2026. "
                  "Aggiungi ANTHROPIC_API_KEY nel .env per l'uso reale.")
DEMO_BANNER_EN = ("Offline demo mode: answers recorded from Claude on 3 Oct 2026. "
                  "Add ANTHROPIC_API_KEY to .env for real use.")

RETRIEVED_ON = "2026-10-03"  # date the local index and fixtures were captured


def has_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip() or os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip())


def demo_mode() -> bool:
    """Offline demo when there is no key, or when DEMO_MODE=1 forces it."""
    forced = os.environ.get("DEMO_MODE", "0").strip().lower() in ("1", "true", "yes", "on")
    return forced or not has_key()


def model() -> str:
    return os.environ.get("CLAUDE_MODEL", "").strip() or "claude-opus-5-5"


def effort() -> str:
    return os.environ.get("CLAUDE_EFFORT", "").strip() or "medium"


def interview_effort() -> str:
    # Interview turns are short and need to feel snappy.
    return os.environ.get("CLAUDE_EFFORT_INTERVISTA", "").strip() or "low"


def today() -> date:
    """Today's date; OGGI=YYYY-MM-DD pins it (used to replay the demo consistently)."""
    v = os.environ.get("OGGI", "").strip()
    return date.fromisoformat(v) if v else date.today()
