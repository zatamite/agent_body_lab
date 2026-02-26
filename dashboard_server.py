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

from flask import Flask, jsonify, send_from_directory, abort, request

ROOT = Path(__file__).parent
app  = Flask(__name__, static_folder=str(ROOT / "dashboard"))

# ── Physics Engine ────────────────────────────────────────────────────────────
try:
    from physics_engine import (Component, WheelContact, DrivetrainConfig,
                                 evaluate_design, compute_cog, default_v2_layout)
    HAS_PHYSICS = True
except ImportError:
    HAS_PHYSICS = False

try:
    from blender_bridge import generate_chassis
    HAS_BLENDER = True
except ImportError:
    HAS_BLENDER = False

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
    total = sum(p["cost"] for p in parts) + 25
    return jsonify({"parts": parts, "total_cost_usd": total})

def _build_stl_params():
    # Load evolution report to get the latest optimized geometry
    evo_report = _load_json(ROOT / "evolution_report.json")
    wp = evo_report.get("winner", {}).get("params", {}) if evo_report else {"wall": 3.5, "int_x": 95, "int_y": 68, "int_z": 130, "vent_w": 12, "vent_h": 35, "n_vents": 12}
    
    wall = wp.get("wall", 3.5)
    int_x = wp.get("int_x", 95); int_y = wp.get("int_y", 68); int_z = wp.get("int_z", 130)
    vent_w = wp.get("vent_w", 12); vent_h = wp.get("vent_h", 35); n_vents = int(wp.get("n_vents", 12))
    out_x = int_x + 2*wall; out_y = int_y + 2*wall; out_z = int_z + wall
    gc = wp.get("ground_clear", 15)
    z_base = gc
    components = [
        {"label": "18650 ×2", "x": 0, "y": 0, "z": z_base + 34, "w": 40, "d": 20, "h": 65, "color": "#ffcc00"},
        {"label": "NEMA17", "x": 0, "y": 0, "z": z_base + 91, "w": 42, "d": 42, "h": 42, "color": "#ff8c00"},
        {"label": "Pi 5", "x": 0, "y": 0, "z": z_base + 121, "w": 85, "d": 58, "h": 17, "color": "#00c8ff"},
    ]
    if wp.get("has_wheels", 1):
        w_dia = wp.get("wheel_dia", 65); w_width = wp.get("wheel_width", 26)
        w_dist = out_x / 2 + w_width / 2 + 2; w_z = w_dia / 2
        components.append({"label": "Wheel R", "x": w_dist, "y": 0, "z": w_z, "w": w_width, "d": w_dia, "h": w_dia, "color": "#333333", "type": "cylinder"})
        components.append({"label": "Wheel L", "x": -w_dist, "y": 0, "z": w_z, "w": w_width, "d": w_dia, "h": w_dia, "color": "#333333", "type": "cylinder"})
        components.append({"label": "Caster", "x": 0, "y": out_y/2 - 15, "z": 5, "w": 20, "d": 20, "h": 20, "color": "#cccccc", "type": "sphere"})

    # Vent slot positions
    vents = []
    per_side = n_vents // 4
    if per_side > 0:
        x_spacing = int_x / (per_side + 1)
        for side_y in [out_y / 2, -out_y / 2]:
            for i in range(1, per_side + 1):
                cx = -int_x / 2 + i * x_spacing
                vents.append({"cx": cx, "cy": side_y, "cz": int_z / 2, "w": vent_w, "d": wall + 2, "h": vent_h})
        y_spacing = int_y / (per_side + 1)
        for side_x in [out_x / 2, -out_x / 2]:
            for i in range(1, per_side + 1):
                cy = -int_y / 2 + i * y_spacing
                vents.append({"cx": side_x, "cy": cy, "cz": int_z / 2, "w": wall + 2, "d": vent_w, "h": vent_h})

    return {
        "chassis": {"out_x": out_x, "out_y": out_y, "out_z": out_z, "int_x": int_x, "int_y": int_y, "int_z": int_z, "wall": wall},
        "components": components, "vents": vents, "params": wp, "ground_clear": gc
    }

@app.route("/api/stl-params")
def api_stl_params():
    """ Return chassis geometry data for the Three.js parametric renderer """
    return jsonify(_build_stl_params())

@app.route("/api/export-stl", methods=["POST"])
def api_export_stl():
    """Export STL via Blender (preferred) or OpenSCAD (fallback)."""
    if HAS_BLENDER:
        params = _build_stl_params()
        def _export():
            generate_chassis(params, output_stl=str(ROOT / "body_v2.stl"), output_render=str(ROOT / "body_v2_preview.png"))

        threading.Thread(target=_export, daemon=True).start()
        return jsonify({"ok": True, "message": "Blender STL export started — generating organic chassis with beveled edges. Ready in ~30s."})

    import shutil
    openscad_bin = shutil.which("openscad") or "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
    scad_path = ROOT / "skeleton_v1.scad"
    stl_path  = ROOT / "skeleton_v1.stl"

    def _export_scad():
        subprocess.run([openscad_bin, "-o", str(stl_path), str(scad_path)],
                       cwd=str(ROOT), capture_output=True, timeout=120)

    threading.Thread(target=_export_scad, daemon=True).start()
    return jsonify({"ok": True, "message": "OpenSCAD STL export started."})


@app.route("/api/stl-file")
def api_stl_file():
    """Serve the exported STL binary."""
    # Prefer Blender v2 STL
    for name in ["body_v2.stl", "skeleton_v1.stl"]:
        if (ROOT / name).exists():
            return send_from_directory(str(ROOT), name,
                                       mimetype="application/octet-stream")
    return jsonify({"error": "No STL generated yet. Click Export STL first."}), 404


@app.route("/api/physics-report")
def api_physics_report():
    """Run the full spatial reasoning pipeline and return results."""
    if not HAS_PHYSICS:
        return jsonify({"error": "physics_engine.py not found"}), 500

    layout = default_v2_layout()
    result = evaluate_design(
        layout["components"],
        layout["contacts"],
        layout["drivetrain"],
        chassis_mass_g=400,
    )
    return jsonify(result)


@app.route("/api/blender-render")
def api_blender_render():
    """Serve the Blender preview render if available."""
    render_path = ROOT / "body_v2_preview.png"
    if render_path.exists():
        return send_from_directory(str(ROOT), "body_v2_preview.png",
                                   mimetype="image/png")
    return jsonify({"error": "No render available. Export STL first."}), 404



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


@app.route("/api/components-db")
def api_components_db():
    route = ROOT / "components_db.json"
    return jsonify(_load_json(route) if route.exists() else {})

if __name__ == "__main__":
    print("\n  🌐  agent_body_lab Dashboard")
    print("  Open: http://localhost:5051\n")
    app.run(host="0.0.0.0", port=5051, debug=False)
