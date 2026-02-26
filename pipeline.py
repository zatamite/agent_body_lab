"""
pipeline.py — Main orchestrator for the autonomous body fabrication loop.

Execution order:
  1. Load secrets from .env
  2. Check approval gate (abort if human_approval is False)
  3. Export STL from skeleton_v1.scad via openscad CLI
  4. Slice STL to .bgcode via prusa-slicer CLI
  5. Upload & start print via Prusa Connect API
  6. Launch safety_monitor as daemon thread
  7. Poll print status until FINISHED or E-STOP

Set DRY_RUN=true in .env (or environment) to simulate all hardware steps
safely without a connected printer.
"""

import sys
import time
import threading
from pathlib import Path

import config as cfg
import approval_gate
from prusa_bridge import PrusaXLBridge
from safety_monitor import run_safety_watch

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT          = Path(__file__).parent
SCAD_FILE     = ROOT / "skeleton_v1.scad"
STL_OUTPUT    = ROOT / "skeleton_v1.stl"
BGCODE_OUTPUT = ROOT / "skeleton_v1.bgcode"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _log(msg: str):
    prefix = "[DRY RUN] " if cfg.dry_run() else ""
    print(f"  {prefix}{msg}")


def step_export_stl():
    """Run OpenSCAD CLI to export .stl from .scad parametric model."""
    import subprocess
    _log(f"Exporting STL: {SCAD_FILE.name} → {STL_OUTPUT.name}")
    if cfg.dry_run():
        return  # Skip hardware in dry-run

    result = subprocess.run(
        ["openscad", "--export-format", "stl", str(SCAD_FILE), "-o", str(STL_OUTPUT)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"OpenSCAD failed:\n{result.stderr}")
    _log(f"STL exported → {STL_OUTPUT}")


def step_slice_stl():
    """Run PrusaSlicer CLI to convert .stl → .bgcode with XL profile."""
    import subprocess
    _log(f"Slicing {STL_OUTPUT.name} → {BGCODE_OUTPUT.name}")
    if cfg.dry_run():
        return

    # Adjust --printer-profile to your saved XL config name in PrusaSlicer
    result = subprocess.run(
        [
            "prusa-slicer",
            "--slice",
            "--output", str(BGCODE_OUTPUT),
            str(STL_OUTPUT),
        ],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"PrusaSlicer failed:\n{result.stderr}")
    _log(f"Sliced → {BGCODE_OUTPUT}")


def step_dispatch(bridge: PrusaXLBridge):
    """Upload .bgcode to Prusa Connect and start the print."""
    _log(f"Dispatching {BGCODE_OUTPUT.name} to printer {cfg.prusa_printer_id()}")
    if cfg.dry_run():
        return

    if not BGCODE_OUTPUT.exists():
        raise FileNotFoundError(f"G-code file not found: {BGCODE_OUTPUT}")

    ok = bridge.upload_and_print(str(BGCODE_OUTPUT))
    if not ok:
        raise RuntimeError("Prusa Connect rejected the upload. Check API key and printer ID.")
    _log("Print job dispatched ✅")


def step_monitor(bridge: PrusaXLBridge, stop_event: threading.Event):
    """Poll printer status until print completes or safety monitor triggers e-stop."""
    _log("Safety monitor started (daemon thread).")
    if cfg.dry_run():
        _log("Simulating 10-second print job...")
        time.sleep(10)
        _log("Simulated print complete ✅")
        stop_event.set()
        return

    while not stop_event.is_set():
        try:
            status = bridge.get_status()
            state  = status.get("state", "UNKNOWN")
            _log(f"Printer state: {state}")

            if state == "FINISHED":
                _log("Print complete ✅")
                stop_event.set()
            elif state in ("ERROR", "ATTENTION", "STOPPED"):
                _log(f"⚠️  Abnormal state '{state}' — e-stop triggered.")
                bridge.emergency_stop()
                stop_event.set()
        except Exception as e:
            _log(f"Status poll error: {e}")

        time.sleep(20)


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print("\n" + "="*60)
    print("  🦾  agent_body_lab — Fabrication Pipeline")
    print("="*60)

    # ── Step 0: Validate environment ──────────────────────────────
    is_dry = cfg.dry_run()
    mode_label = "DRY RUN (no hardware)" if is_dry else "LIVE — hardware active"
    print(f"\n  Mode : {mode_label}")

    # ── Step 1: Approval gate ─────────────────────────────────────
    print("\n[1/5] Checking design approval...")
    try:
        approved = approval_gate.check_approval()
        print(f"      Body {approved['version']} approved ✅")
    except (PermissionError, FileNotFoundError, ValueError) as e:
        print(e)
        sys.exit(1)

    # ── Step 2: Export STL ────────────────────────────────────────
    print("\n[2/5] Exporting STL from parametric model...")
    try:
        step_export_stl()
    except Exception as e:
        print(f"  ❌  STL export failed: {e}")
        sys.exit(1)

    # ── Step 3: Slice ─────────────────────────────────────────────
    print("\n[3/5] Slicing for Prusa XL...")
    try:
        step_slice_stl()
    except Exception as e:
        print(f"  ❌  Slicing failed: {e}")
        sys.exit(1)

    # ── Step 4: Dispatch ──────────────────────────────────────────
    print("\n[4/5] Dispatching to Prusa Connect...")
    bridge = PrusaXLBridge()  # Reads credentials from secrets.py
    try:
        step_dispatch(bridge)
    except Exception as e:
        print(f"  ❌  Dispatch failed: {e}")
        sys.exit(1)

    # ── Step 5: Monitor ───────────────────────────────────────────
    print("\n[5/5] Monitoring print...")
    stop_event = threading.Event()

    # Safety monitor runs as a daemon — killed automatically if pipeline exits
    monitor_thread = threading.Thread(
        target=run_safety_watch,
        args=(bridge, stop_event),
        daemon=True,
        name="safety-monitor"
    )
    monitor_thread.start()

    # Main thread drives the status polling loop
    step_monitor(bridge, stop_event)
    monitor_thread.join(timeout=5)

    print("\n" + "="*60)
    print("  ✅  Pipeline complete.")
    print("="*60 + "\n")


if __name__ == "__main__":
    run()
