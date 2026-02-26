"""
safety_monitor.py — Hardware watchdog for the Prusa XL.

Runs as a daemon thread launched by pipeline.py.
In dry-run mode (DRY_RUN=true), the status poll is skipped entirely.
Monitors printer telemetry every 20 seconds.
Triggers emergency stop on ERROR state or over-temperature (>305°C).

Uses a threading.Event for clean shutdown — set stop_event to signal exit.
"""

import time
import threading
import config as cfg


def run_safety_watch(bridge, stop_event: threading.Event, fail_threshold: float = 0.9):
    """
    Monitor printer status in a loop until stop_event is set or an anomaly is detected.

    Args:
        bridge:         PrusaXLBridge instance for status queries and e-stop.
        stop_event:     threading.Event — set this from the main thread to stop monitoring.
        fail_threshold: Reserved for future vision-based confidence scoring (0–1).
    """
    print("  🛡  Safety Monitor Active (polling every 20s)...")

    while not stop_event.is_set():
        # Skip all hardware polling in dry-run mode
        if not cfg.dry_run():
            try:
                status = bridge.get_status()
                state  = status.get("state", "UNKNOWN")
                temp   = status.get("telemetry", {}).get("temp_nozzle", 0)

                # ── State check ───────────────────────────────────────────────
                if state in ("ERROR", "ATTENTION"):
                    print(f"  🚨 [safety_monitor] Hardware anomaly: state='{state}'. Initiating E-Stop.")
                    bridge.emergency_stop()
                    stop_event.set()
                    break

                # ── Thermal runaway check ─────────────────────────────────────
                if temp > 305:
                    print(f"  🚨 [safety_monitor] Thermal runaway: nozzle temp={temp}°C (limit: 305°C). E-Stop.")
                    bridge.emergency_stop()
                    stop_event.set()
                    break

            except Exception as e:
                # Network/API errors should not kill the monitor — log and continue
                print(f"  ⚠️  [safety_monitor] Poll error (non-fatal): {e}")

        # Wait 20s, but wake immediately if stop_event is set externally
        stop_event.wait(timeout=20)

    print("  🛡  Safety Monitor stopped.")


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from prusa_bridge import PrusaXLBridge
    import secrets as cfg

    print("Running safety monitor in standalone mode (DRY RUN).")
    print("Press Ctrl+C to stop.\n")

    stop = threading.Event()
    bridge = PrusaXLBridge()

    t = threading.Thread(target=run_safety_watch, args=(bridge, stop), daemon=True)
    t.start()

    try:
        while not stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop.set()
        t.join(timeout=5)