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


@app.route("/api/stl-params")
def api_stl_params():
    """
    Return chassis geometry data for the Three.js parametric renderer.
    Includes layer stack, component bounding boxes, and vent slot positions.
    """
    report = _load_json(ROOT / "evolution_report.json")
    if not report:
        # Fall back to initial design
        wp = {"wall": 3.5, "int_x": 95, "int_y": 68, "int_z": 130,
              "vent_w": 12, "vent_h": 35, "n_vents": 12}
    else:
        wp = report["winner"]["params"]

    wall  = wp["wall"]
    int_x = wp["int_x"]; int_y = wp["int_y"]; int_z = wp["int_z"]
    vent_w = wp["vent_w"]; vent_h = wp["vent_h"]; n_vents = int(wp["n_vents"])
    out_x = int_x + 2 * wall
    out_y = int_y + 2 * wall
    out_z = int_z + wall

    # Component bounding boxes [x, y, z_bottom, w, d, h, color_hex, label]
    # Positions relative to chassis centre (0,0), z from bottom
    components = [
        # NEMA17 base (below chassis, external)
        {"label": "NEMA17",    "x": 0,   "y": 0,   "z": -40, "w": 42, "d": 42, "h": 40, "color": "#ff8c00"},
        # Sensor hub bay (Z=40)
        {"label": "RP2040",    "x": -8,  "y": -15, "z": 42,  "w": 33, "d": 18, "h": 8,  "color": "#00c8ff"},
        {"label": "LSM6DSOX",  "x":  8,  "y":  18, "z": 42,  "w": 26, "d": 18, "h": 5,  "color": "#00e676"},
        {"label": "INA219",    "x": -28, "y":   3, "z": 42,  "w": 26, "d": 21, "h": 5,  "color": "#00e676"},
        # Pi 5 bay (Z=80)
        {"label": "Pi 5",      "x": 0,   "y": 0,   "z": 82,  "w": 85, "d": 58, "h": 17, "color": "#00c8ff"},
        {"label": "Coral",     "x": 0,   "y": 24,  "z": 101, "w": 65, "d": 30, "h": 8,  "color": "#9c64ff"},
        # Battery tray (Z=110)
        {"label": "18650 ×2",  "x": 0,   "y": 0,   "z": 112, "w": 40, "d": 20, "h": 65, "color": "#ffcc00"},
        {"label": "PowerBoost","x":-20,  "y":-18,  "z": 112, "w": 37, "d": 23, "h": 6,  "color": "#ff8c00"},
    ]

    # Vent slot positions [cx, cy, cz, w, d, h] for each vent
    vents = []
    per_side = n_vents // 4
    # Front/back vents (along X, on Y faces)
    x_spacing = int_x / (per_side + 1)
    for side_y in [out_y / 2, -out_y / 2]:
        for i in range(1, per_side + 1):
            cx = -int_x / 2 + i * x_spacing
            vents.append({"cx": cx, "cy": side_y, "cz": int_z / 2,
                          "w": vent_w, "d": wall + 2, "h": vent_h})
    # Side vents (along Y, on X faces)
    y_spacing = int_y / (per_side + 1)
    for side_x in [out_x / 2, -out_x / 2]:
        for i in range(1, per_side + 1):
            cy = -int_y / 2 + i * y_spacing
            vents.append({"cx": side_x, "cy": cy, "cz": int_z / 2,
                          "w": wall + 2, "d": vent_w, "h": vent_h})

    return jsonify({
        "chassis": {
            "out_x": out_x, "out_y": out_y, "out_z": out_z,
            "int_x": int_x, "int_y": int_y, "int_z": int_z,
            "wall":  wall
        },
        "components": components,
        "vents":      vents,
        "params":     wp,
    })


@app.route("/api/export-stl", methods=["POST"])
def api_export_stl():
    """Try to export STL via OpenSCAD. Returns instructions if not installed."""
    import shutil
    openscad_paths = [
        shutil.which("openscad"),
        "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD",
        "/usr/local/bin/openscad",
    ]
    openscad_bin = next((p for p in openscad_paths if p), None)

    if not openscad_bin:
        return jsonify({
            "ok": False,
            "message": "OpenSCAD not found. Install from openscad.org, then click Export STL again.",
            "install_url": "https://openscad.org/downloads.html"
        }), 200

    scad_path = ROOT / "skeleton_v1.scad"
    stl_path  = ROOT / "skeleton_v1.stl"

    def _export():
        subprocess.run(
            [openscad_bin, "-o", str(stl_path), str(scad_path)],
            cwd=ROOT, capture_output=True, timeout=120
        )

    threading.Thread(target=_export, daemon=True).start()
    return jsonify({"ok": True, "message": "STL export started — will be available at /api/stl-file in ~30s."})


@app.route("/api/stl-file")
def api_stl_file():
    """Serve the exported STL binary for Three.js STLLoader."""
    stl_path = ROOT / "skeleton_v1.stl"
    if not stl_path.exists():
        return jsonify({"error": "STL not yet generated. POST /api/export-stl first."}), 404
    return send_from_directory(str(ROOT), "skeleton_v1.stl",
                               mimetype="application/octet-stream")




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


_creative_running = False

@app.route("/api/creative-report")
def api_creative_report():
    """Return creative_report.json (top-3 competing body designs)."""
    report = _load_json(ROOT / "creative_report.json")
    if not report:
        return jsonify({"ok": False, "message": "No creative report yet. Click 🎨 Explore Designs."}), 404
    return jsonify(report)


@app.route("/api/components-db")
def api_components_db():
    """Return the full components database."""
    db = _load_json(ROOT / "components_db.json")
    return jsonify(db)


@app.route("/api/run-creative", methods=["POST"])
def api_run_creative():
    """Trigger creative_evolver.py in a background thread."""
    global _creative_running
    if _creative_running:
        return jsonify({"ok": False, "message": "Creative exploration already running."}), 409

    import flask
    data   = flask.request.get_json(silent=True) or {}
    pop    = int(data.get("population", 40))
    budget = float(data.get("budget", 400.0))

    def _run():
        global _creative_running
        _creative_running = True
        try:
            subprocess.run(
                [sys.executable, str(ROOT / "creative_evolver.py"),
                 "--pop", str(pop), "--budget", str(budget)],
                cwd=ROOT, capture_output=False
            )
        finally:
            _creative_running = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({
        "ok": True,
        "message": f"Creative exploration started ({pop} assemblies, ${budget:.0f} budget). Refresh in ~5s."
    })


if __name__ == "__main__":
    print("\n  🌐  agent_body_lab Dashboard")
    print("  Open: http://localhost:5050\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
