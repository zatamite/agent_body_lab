"""
dashboard_server.py — Flask web server for the agent_body_lab design console.

Serves the dashboard HTML and provides REST API endpoints for live data.

Endpoints:
  GET /                     → dashboard HTML
  GET /api/status           → pipeline + approval gate status
  GET /api/evolution        → evolution_report.json (all 10 iterations)
  GET /api/config           → current skeleton_v1.scad parameters
  GET /api/parts            → parts DOM from parts_dom summary
  POST /api/approve         → approve latest evolution entry
  POST /api/run-evolution   → trigger design_evolver.py
"""

import json
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, send_from_directory, abort

ROOT = Path(__file__).parent
app  = Flask(__name__, static_folder=str(ROOT / "dashboard"))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def _load_evolution_log() -> list:
    p = ROOT / "evolution_log.json"
    if not p.exists():
        return []
    lines = [l.strip() for l in p.read_text().splitlines() if l.strip()]
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except Exception:
            pass
    return result


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(ROOT / "dashboard"), "index.html")


@app.route("/api/status")
def api_status():
    log_entries = _load_evolution_log()
    latest      = log_entries[-1] if log_entries else None

    approved  = latest.get("human_approval", False) if latest else False
    version   = latest.get("version", "—")          if latest else "—"

    report   = _load_json(ROOT / "evolution_report.json")
    winner   = report.get("winner", {})

    return jsonify({
        "time":           datetime.now().isoformat(),
        "version":        version,
        "approved":       approved,
        "gate_status":    "OPEN" if approved else "LOCKED",
        "evolution_done": bool(report),
        "winner_fitness": winner.get("metrics", {}).get("fitness"),
        "dry_run":        True,   # from config.py
        "prusa_online":   False,  # placeholder until real printer connected
    })


@app.route("/api/evolution")
def api_evolution():
    report = _load_json(ROOT / "evolution_report.json")
    if not report:
        abort(404, description="evolution_report.json not found — run design_evolver.py first.")
    return jsonify(report)


@app.route("/api/parts")
def api_parts():
    """Return the structured parts BOM."""
    parts = [
        {"id": "01", "organ": "BRAIN",      "part": "Raspberry Pi 5 8GB",          "cost": 80,  "dims": "85×58×17mm", "mount": "M2.5 (58×49mm)"},
        {"id": "02", "organ": "CORTEX",     "part": "Google Coral USB Accelerator", "cost": 60,  "dims": "65×30×8mm",  "mount": "TPU clip"},
        {"id": "03", "organ": "VISION",     "part": "Pi Camera Module 3 Wide",      "cost": 35,  "dims": "25×24×12mm", "mount": "M2 (21×12mm)"},
        {"id": "04", "organ": "HEARING",    "part": "Adafruit I2S MEMS Mic",        "cost":  7,  "dims": "19×12×3mm",  "mount": "M2.5"},
        {"id": "05", "organ": "MOTION",     "part": "NEMA17 Stepper 17HS4401",      "cost": 12,  "dims": "42×42×40mm", "mount": "M3 (31×31mm)"},
        {"id": "06", "organ": "MOTOR CTL",  "part": "TMC2209 Driver v1.3",          "cost":  8,  "dims": "20×15mm",    "mount": "Pololu socket"},
        {"id": "07", "organ": "NERVE HUB",  "part": "SparkFun QWIIC Pro Micro RP2040","cost": 12, "dims": "33×18mm",  "mount": "M2"},
        {"id": "08", "organ": "BALANCE",    "part": "Adafruit LSM6DSOX IMU",        "cost": 12,  "dims": "25.6×17.8mm","mount": "M2.5 QWIIC"},
        {"id": "09", "organ": "ENV",        "part": "Adafruit BME688",              "cost": 20,  "dims": "23×17.8mm",  "mount": "M2.5 QWIIC"},
        {"id": "10", "organ": "TELEMETRY",  "part": "Adafruit INA219",              "cost": 10,  "dims": "25.6×20.4mm","mount": "M2.5 QWIIC"},
        {"id": "11", "organ": "CHARGER",    "part": "Adafruit PowerBoost 1000C",    "cost": 20,  "dims": "36.5×23mm",  "mount": "M2.5"},
        {"id": "12", "organ": "ENERGY",     "part": "18650 Cells ×2 (NCR18650B)",   "cost": 18,  "dims": "Ø18.6×65mm", "mount": "PETG tray"},
        {"id": "13", "organ": "12V RAIL",   "part": "LM2596 Buck Converter",        "cost":  8,  "dims": "43×21×14mm", "mount": "M3"},
    ]
    total = sum(p["cost"] for p in parts) + 25  # + cables/hardware
    return jsonify({"parts": parts, "total_cost_usd": total})


@app.route("/api/approve", methods=["POST"])
def api_approve():
    try:
        import reasoning_engine
        reasoning_engine.approve_latest()
        return jsonify({"ok": True, "message": "Latest entry approved. Gate is OPEN."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


_evolver_running = False

@app.route("/api/run-evolution", methods=["POST"])
def api_run_evolution():
    global _evolver_running
    if _evolver_running:
        return jsonify({"ok": False, "message": "Evolution already running."}), 409

    def _run():
        global _evolver_running
        _evolver_running = True
        try:
            subprocess.run(
                [sys.executable, str(ROOT / "design_evolver.py")],
                cwd=ROOT, capture_output=False
            )
        finally:
            _evolver_running = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "Evolution started in background."})


if __name__ == "__main__":
    print("\n  🌐  agent_body_lab Dashboard")
    print("  Open: http://localhost:5050\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
