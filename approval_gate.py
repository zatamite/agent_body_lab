"""
approval_gate.py — Hard gate between design rationale and hardware dispatch.

Reads the latest entry in evolution_log.json. If human_approval is False,
raises PermissionError and aborts the pipeline. Nothing prints without approval.
"""

import json
from pathlib import Path


def _read_latest(log_path: str = "evolution_log.json") -> dict:
    """Return the last entry in the JSONL evolution log."""
    p = Path(log_path)
    if not p.exists():
        raise FileNotFoundError(
            f"[approval_gate] No evolution log found at '{log_path}'.\n"
            f"  → Run reasoning_engine.log_evolution() to create an entry first."
        )
    lines = [l.strip() for l in p.read_text().splitlines() if l.strip()]
    if not lines:
        raise ValueError(
            "[approval_gate] Evolution log exists but is empty.\n"
            "  → Log at least one design rationale entry before running the pipeline."
        )
    return json.loads(lines[-1])


def check_approval(log_path: str = "evolution_log.json") -> dict:
    """
    Verify the latest design rationale entry has been human-approved.

    Returns the approved entry dict on success.
    Raises PermissionError if human_approval is False.
    """
    entry = _read_latest(log_path)
    version = entry.get("version", "unknown")

    if not entry.get("human_approval", False):
        raise PermissionError(
            f"\n{'='*60}\n"
            f"  🚫  DISPATCH BLOCKED — Body {version} not approved.\n"
            f"{'='*60}\n"
            f"  The latest design rationale has human_approval = false.\n"
            f"\n"
            f"  To approve, run:\n"
            f"    python3 -c \"import reasoning_engine; reasoning_engine.approve_latest()\"\n"
            f"\n"
            f"  Then re-run the pipeline.\n"
            f"{'='*60}"
        )

    print(f"✅ [approval_gate] Body {version} approved. Gate is OPEN.")
    return entry


if __name__ == "__main__":
    # Quick CLI check: python3 approval_gate.py
    try:
        entry = check_approval()
        print(f"   Version : {entry['version']}")
        print(f"   Approved: {entry['human_approval']}")
    except (PermissionError, FileNotFoundError, ValueError) as e:
        print(e)
