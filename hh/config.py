"""Settings. Everything is optional: with no keys the whole pipeline runs offline on sample data.

Bring your own keys (BYOK) by copying .env.example to .env. Nothing is ever billed to us.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"
PRIVATE = DATA / "private"  # raw resumes live here; git-ignored, never leaves the box


def _load_env():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

DB_PATH = Path(os.getenv("HH_DB", str(OUT / "hh.sqlite")))

# Resume parsing. "rules" = free, offline. "anthropic" or "openai" (any OpenAI-compatible
# server, including a local Ollama at http://localhost:11434/v1, which is also free).
LLM_PROVIDER = os.getenv("HH_LLM_PROVIDER", "rules")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("HH_ANTHROPIC_MODEL", "claude-haiku-5-5")
OPENAI_BASE_URL = os.getenv("HH_OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_API_KEY = os.getenv("HH_OPENAI_API_KEY", "ollama")
OPENAI_MODEL = os.getenv("HH_OPENAI_MODEL", "llama3.1:8b")

# treg: one login, 30+ data providers, cheapest first. Your own account (`treg login`).
TREG_BIN = os.getenv("HH_TREG_BIN", "treg")
TREG_MAX_SPEND_USD = float(os.getenv("HH_TREG_MAX_SPEND_USD", "0.50"))  # hard cap per run

# Privacy thresholds (slide 10). Do not lower these.
TEAM_SIGNAL_MIN_APPLICANTS = 3
TEAM_SIGNAL_WINDOW_DAYS = 30
