"""
reasoning_engine.py — Evolution logger and design rationale writer.

Logs each design version to evolution_log.json (JSONL format).
Writes a human-readable design_reasoning.md artifact for review.
Provides approve_latest() to unlock the approval gate for the latest entry.
"""

import json
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).parent / "evolution_log.json"


def log_evolution(version: str, logic_dict: dict, log_path: Path = LOG_PATH):
    """
    Append a new design rationale entry to the evolution log.

    Args:
        version:    Version string, e.g. "v1.0"
        logic_dict: Dict with at minimum an 'intent' key describing the rationale.
        log_path:   Path to the JSONL log file (default: evolution_log.json).
    """
    log_entry = {
        "timestamp":      datetime.now().isoformat(),
        "version":        version,
        "rationale":      logic_dict,
        "human_approval": False,  # Must be explicitly approved via approve_latest()
    }

    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Write human-readable Markdown artifact
    md_path = Path(__file__).parent / "design_reasoning.md"
    with open(md_path, "w") as f:
        f.write(f"# Design Rationale — Body {version}\n\n")
        f.write(f"**Timestamp:** {log_entry['timestamp']}\n\n")
        f.write(logic_dict.get("intent", "No intent specified."))

    print(f"✅ [reasoning_engine] Logged Body {version}. Awaiting human approval.")


def approve_latest(log_path: Path = LOG_PATH):
    """
    Flip human_approval to True for the last entry in the evolution log.
    This unlocks the approval gate in approval_gate.py.

    Usage:
        python3 -c "import reasoning_engine; reasoning_engine.approve_latest()"
    """
    p = Path(log_path)
    if not p.exists() or not p.read_text().strip():
        raise FileNotFoundError(
            "[reasoning_engine] No evolution log found. Log a rationale entry first."
        )

    lines = [l.strip() for l in p.read_text().splitlines() if l.strip()]
    if not lines:
        raise ValueError("[reasoning_engine] Evolution log is empty.")

    # Flip the last entry
    last   = json.loads(lines[-1])
    version = last.get("version", "unknown")

    if last.get("human_approval"):
        print(f"ℹ️  [reasoning_engine] Body {version} is already approved.")
        return

    last["human_approval"] = True
    lines[-1] = json.dumps(last)

    p.write_text("\n".join(lines) + "\n")
    print(f"✅ [reasoning_engine] Body {version} APPROVED. Approval gate is now OPEN.")


if __name__ == "__main__":
    # Quick test: log a dummy entry
    log_evolution("v0.0-test", {
        "intent": "Test entry — validates log + reasoning pipeline.",
    })
    print("Test entry logged. Run approve_latest() to approve.")