"""
config.py — Centralised credential and config loader for agent_body_lab.
All modules import from here. Never hardcode credentials elsewhere.

Reads from a .env file in the project root using python-dotenv.
If DRY_RUN=true, hardware credentials are not required.
"""

import os
from typing import Optional
from pathlib import Path

# Load .env if present (silently skipped if file doesn't exist)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; fall back to real env vars only


def get(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Retrieve an environment variable by name. Returns None if not set and no default."""
    value = os.environ.get(key, default)
    if required and not value:
        raise EnvironmentError(
            f"[config] Required environment variable '{key}' is not set.\n"
            f"  → Copy .env.example to .env and fill in your credentials."
        )
    return value


# ── Convenience accessors ─────────────────────────────────────────────────────

def dry_run() -> bool:
    """Returns True if DRY_RUN env var is set to 'true' (case-insensitive)."""
    val = get("DRY_RUN", default="false") or "false"
    return val.lower() == "true"


def prusa_api_key() -> Optional[str]:
    """Returns the Prusa API key, or raises EnvironmentError in live mode."""
    return get("PRUSA_API_KEY", required=not dry_run())


def prusa_printer_id() -> Optional[str]:
    """Returns the Prusa printer UUID, or raises EnvironmentError in live mode."""
    return get("PRUSA_PRINTER_ID", required=not dry_run())


def prusa_server_url() -> str:
    """Returns the Prusa Connect base URL, defaulting to the public endpoint."""
    return get("PRUSA_SERVER_URL", default="https://connect.prusa3d.com") or "https://connect.prusa3d.com"
