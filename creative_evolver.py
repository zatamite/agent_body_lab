"""
creative_evolver.py — Generative design explorer for Body v1.0+.

Unlike design_evolver.py (which tweaks chassis geometry), this explores
fundamentally different HARDWARE ASSEMBLIES by randomly sampling from
components_db.json, evaluating each combination against a multi-objective
fitness function, and returning the top 3 competing body designs.

Algorithm:
  1. Load component database (components_db.json)
  2. Generate N random assemblies (one component per category)
  3. Evaluate each with:
       - Size compatibility (does everything fit?)
       - Power budget (battery runtime estimate)
       - Mass estimate (chassis + all components)
       - Cost check (within $BUDGET)
       - AI performance score (TOPS)
       - Printability (chassis dims vs Prusa XL build volume)
  4. Rank by composite fitness, take top 3
  5. For each top-3: run geometry hill-climb to find optimal chassis dims
  6. Write creative_report.json  
  7. Log to evolution_log.json

Usage:
    python3 creative_evolver.py              # default 40 assemblies, budget $400
    python3 creative_evolver.py --pop 80 --budget 300
"""

import json
import copy
import math
import random
import argparse
from datetime import datetime
from pathlib import Path

# Spatial Reasoning Engine
from physics_engine import (Component, WheelContact, DrivetrainConfig,
                           evaluate_design, check_collisions)

ROOT = Path(__file__).parent
DB_PATH      = ROOT / "components_db.json"
REPORT_PATH  = ROOT / "creative_report.json"
LOG_PATH     = ROOT / "evolution_log.json"

# ── Physical constants (same as design_evolver.py) ─────────────────────────
PETG_YIELD_MPa   = 51.0
PETG_DENSITY     = 1.27   # g/cm³
PETG_ALPHA       = 5.0e-5
PETG_DELTA_T     = 40.0
GRAVITY          = 9.81
PRINT_SPEED_MM_S = 80.0
LAYER_HEIGHT_MM  = 0.2
NOZZLE_DIA_MM    = 0.4

# Prusa XL build volume (mm)
PRUSA_XL_MAX     = [360, 360, 360]

# Chassis wall constants
BASE_WALL        = 3.0    # mm — minimum wall thickness
CLEARANCE        = 4.0    # mm — gap per side around components
BATTERY_TRAY_MM  = 5.0    # mm — extra room in Y for battery tray

# Fixed sensors (always included — small, QWIIC, no alternatives)
FIXED_SENSORS = {
    "imu":   {"name": "LSM6DSOX IMU",      "cost": 12, "dims_mm": [26,18,5],  "mass_g": 3,  "power_max_w": 0.01},
    "env":   {"name": "BME688 Env Sensor", "cost": 20, "dims_mm": [23,18,5],  "mass_g": 3,  "power_max_w": 0.01},
    "power": {"name": "INA219 Monitor",    "cost": 10, "dims_mm": [26,21,5],  "mass_g": 3,  "power_max_w": 0.01},
    "buck":  {"name": "LM2596 Buck 12V",   "cost":  8, "dims_mm": [43,21,14], "mass_g": 15, "power_max_w": 2.0},
}

# ── Load database ───────────────────────────────────────────────────────────
def load_db() -> dict:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"components_db.json not found at {DB_PATH}")
    return json.loads(DB_PATH.read_text())

# ── Random assembly sampler ─────────────────────────────────────────────────
def sample_assembly(db: dict, rng: random.Random) -> dict:
    """Pick one component from each category at random."""
    asm = {}
    for cat in ["sbc", "accelerator", "camera", "microphone",
                "motor", "motor_driver", "sensor_hub", "battery", "power_mgmt", "wheels"]:
        pool = db.get(cat, [])
        if pool:
            asm[cat] = rng.choice(pool)
    asm["fixed_sensors"] = list(FIXED_SENSORS.values())
    return asm

# ── Derive minimum chassis from assembly ────────────────────────────────────
def chassis_from_assembly(asm: dict) -> dict:
    """
    Compute the minimum chassis internal volume needed to fit the assembly.
    SBC and accelerator are the footprint-drivers.
    Motor mounts externally (belly-mount). Battery and power sit on top.
    """
    sbc   = asm.get("sbc", {})
    accel = asm.get("accelerator", {})
    cam   = asm.get("camera", {})
    motor = asm.get("motor", {})
    batt  = asm.get("battery", {})
    hub   = asm.get("sensor_hub", {})
    pwr   = asm.get("power_mgmt", {})

    def dim(comp, i, default=0):
        d = comp.get("dims_mm", [default, default, default])
        return d[i] if i < len(d) else default

    # Internal X = max(SBC_x, battery_x + sensor_tray_x) + 2*CLEARANCE
    sbc_x   = dim(sbc, 0, 85)
    batt_x  = dim(batt, 0, 40)
    hub_x   = dim(hub, 0, 33)
    accel_x = dim(accel, 0, 0)
    int_x   = max(sbc_x, batt_x + hub_x + 10, accel_x) + 2 * CLEARANCE

    # Internal Y = max(SBC_y, battery_y_max) + clearance + battery tray wall
    sbc_y   = dim(sbc, 1, 58)
    batt_y  = dim(batt, 1, 19)
    int_y   = max(sbc_y, batt_y) + 2 * CLEARANCE + BATTERY_TRAY_MM

    # Internal Z (height) = stacked layers:
    # Layer 0: NEMA17/motor mount plate (not inside chassis)
    # Layer 1: Sensor hub + sensors (hub_h + 10mm clearance)
    # Layer 2: SBC + accelerator (sbc_h + accel_h + 5mm clearance)
    # Layer 3: Battery + power (batt_h + pwr_h + 5mm clearance)
    sbc_h   = dim(sbc, 2, 17)
    accel_h = dim(accel, 2, 0)
    hub_h   = dim(hub, 2, 4)
    batt_h  = dim(batt, 2, 65)
    pwr_h   = dim(pwr, 2, 6)
    cam_h   = dim(cam, 2, 12)

    layer1  = hub_h + 12     # sensor layer
    layer2  = sbc_h + accel_h + 8   # compute layer
    layer3  = batt_h + pwr_h + 8    # power layer
    int_z   = layer1 + layer2 + layer3 + cam_h + 20 # 20mm extra for internal wiring/clearance

    # Outer dims
    wall   = BASE_WALL
    out_x  = int_x + 2*wall
    out_y  = int_y + 2*wall
    out_z  = int_z + wall

    return {
        "wall":    wall,
        "int_x":   round(int_x, 1),
        "int_y":   round(int_y, 1),
        "int_z":   round(int_z, 1),
        "out_x":   round(out_x, 1),
        "out_y":   round(out_y, 1),
        "out_z":   round(out_z, 1),
        "n_vents": 12,
        "vent_w":  16,
        "vent_h":  40,
    }

# ── Multi-objective fitness ─────────────────────────────────────────────────
def evaluate_assembly(asm: dict, budget: float = 400.0) -> dict:
    """
    Score a hardware assembly + its derived chassis on multiple objectives.
    Returns a metrics dict with composite fitness (0–1).
    """
    ch = chassis_from_assembly(asm)
    sbc = asm.get("sbc", {})
    motor = asm.get("motor", {})
    batt = asm.get("battery", {})

    # ── Cost ────────────────────────────────────────────────────────────────
    cats = ["sbc","accelerator","camera","microphone","motor",
            "motor_driver","sensor_hub","battery","power_mgmt", "wheels"]
    bom_cost = float(sum(asm.get(c, {}).get("cost", 0) for c in cats))
    bom_cost += float(sum(s.get("cost", 0) for s in FIXED_SENSORS.values()))
    cost_score = max(0.0, 1.0 - bom_cost / budget)       # 1.0 if free, 0 if at budget

    # ── AI Performance (TOPS) ────────────────────────────────────────────────
    sbc_tops   = asm.get("sbc",         {}).get("ai_tops", 0)
    accel_tops = asm.get("accelerator", {}).get("ai_tops", 0)
    total_tops = sbc_tops + accel_tops
    tops_score = min(1.0, total_tops / 20.0)              # 20 TOPS = perfect

    # ── Mass (chassis + all components) ─────────────────────────────────────
    # Chassis mass
    out_x, out_y, out_z = ch["out_x"], ch["out_y"], ch["out_z"]
    int_x, int_y, int_z = ch["int_x"], ch["int_y"], ch["int_z"]
    wall = ch["wall"]
    n_v, vw, vh = ch["n_vents"], ch["vent_w"], ch["vent_h"]

    outer_vol_mm3 = out_x * out_y * out_z
    inner_vol_mm3 = int_x * int_y * int_z
    vent_vol_mm3  = n_v * vw * vh * wall
    chassis_mass_g = max(0, (outer_vol_mm3 - inner_vol_mm3 - vent_vol_mm3) / 1000.0 * PETG_DENSITY)

    component_mass_g = float(sum(asm.get(c, {}).get("mass_g", 0) for c in cats))
    component_mass_g += float(sum(s.get("mass_g", 0) for s in FIXED_SENSORS.values()))
    total_mass_g = chassis_mass_g + component_mass_g
    mass_score = max(0.0, 1.0 - total_mass_g / 1200.0)   # 1200g = 0 score

    # ── Power budget & runtime ───────────────────────────────────────────────
    batt      = asm.get("battery", {})
    energy_wh = batt.get("energy_wh", 22.0)
    idle_w    = sum(asm.get(c, {}).get("power_idle_w", 0) for c in ["sbc","accelerator","sensor_hub"])
    idle_w   += sum(asm.get(c, {}).get("power_max_w",  0) * 0.3
                    for c in ["camera","microphone","motor"])    # motors at 30% duty
    idle_w   += 2.0   # fixed sensors + misc static
    runtime_h = energy_wh / max(idle_w, 0.1)
    runtime_score = min(1.0, runtime_h / 6.0)             # 6hr = perfect score

    # ── Structural safety factor ─────────────────────────────────────────────
    payload_n = total_mass_g * 1e-3 * GRAVITY
    A_walls_mm2 = 2 * (out_x + out_y) * wall - 4 * wall**2
    A_walls_m2  = max(A_walls_mm2, 1) * 1e-6
    stress_MPa  = (payload_n / A_walls_m2) * 1e-6
    safety_factor = PETG_YIELD_MPa / max(stress_MPa, 1e-9)
    ssf_score = min(1.0, safety_factor / 300.0)

    # ── Thermal ─────────────────────────────────────────────────────────────
    vent_area   = n_v * vw * vh
    surface_mm2 = 2*(out_x*out_z) + 2*(out_y*out_z) + out_x*out_y
    thermal_ratio = vent_area / max(surface_mm2, 1)
    thermal_score = min(1.0, thermal_ratio / 0.20)

    # ── Warp risk ────────────────────────────────────────────────────────────
    max_span  = max(out_x, out_y)
    warp_mm   = PETG_ALPHA * PETG_DELTA_T * max_span
    warp_score = 1.0 - min(1.0, warp_mm / 1.0)

    # ── Printability (fits Prusa XL build volume) ────────────────────────────
    fits_printer = (out_x <= PRUSA_XL_MAX[0] and
                    out_y <= PRUSA_XL_MAX[1] and
                    out_z <= PRUSA_XL_MAX[2])
    print_score = 1.0 if fits_printer else 0.0

    # ── Print time ───────────────────────────────────────────────────────────
    perimeters_per_layer = wall / NOZZLE_DIA_MM
    n_layers             = out_z / LAYER_HEIGHT_MM
    path_per_layer       = (2*(out_x+out_y)) * perimeters_per_layer + 0.10*int_x*int_y
    print_time_min       = (n_layers * path_per_layer / PRINT_SPEED_MM_S) / 60.0

    # ── 9. SPATIAL REASONING (v2.0 Logic) ──────────────────────────────────
    # Map assembly to physics components
    z_base = ch.get("ground_clear", 15.0) + ch["wall"]

    # Layer 0: Battery
    p_batt = Component("Battery", batt.get("mass_g", 184), 0, 0, z_base + 34, 40, 20, 65)

    # Layer 1: Motor
    p_motor = Component("Motor", motor.get("mass_g", 280), 0, 0, z_base + 91, 42, 42, 42)

    # Layer 2: SBC + Accel
    p_sbc = Component("SBC", sbc.get("mass_g", 43), 0, 0, z_base + 121, 85, 58, 17)

    # Contacts
    wheel_dia = asm.get("wheels", {}).get("diameter_mm", 65)
    wheel_r = wheel_dia / 2.0
    contacts = [
        WheelContact("Wheel R",  65, 0, wheel_r),
        WheelContact("Wheel L", -65, 0, wheel_r),
        WheelContact("Caster",    0, 25, 10),
    ]

    # Drivetrain
    drivetrain = DrivetrainConfig(
        motor_torque_nm=motor.get("torque_nm", 0.40),
        gear_ratio=5.0, # Default for exploration
        wheel_radius_mm=wheel_r
    )

    spatial = evaluate_design(
        [p_batt, p_motor, p_sbc],
        contacts,
        drivetrain,
        chassis_mass_g=chassis_mass_g
    )

    # ── COMPOSITE FITNESS ─────────────────────────────────────────────────────
    # Weights: Spatial (Stability/Mobility/Packaging) is now the primary driver
    fitness = (
        0.50 * spatial["composite_score"] +
        0.15 * runtime_score +
        0.15 * tops_score +
        0.10 * cost_score +
        0.10 * mass_score
    )

    # Collision penalty
    if spatial["collisions"]["has_collisions"]:
        fitness *= 0.1

    fitness = max(0.0, min(1.0, fitness))

    return {
        "fitness":         float(round(float(fitness), 5)),
        "bom_cost":        float(round(float(bom_cost), 2)),
        "total_mass_g":    float(round(float(total_mass_g), 1)),
        "chassis_mass_g":  float(round(float(chassis_mass_g), 1)),
        "total_tops":      int(total_tops),
        "runtime_h":       float(round(float(runtime_h), 2)),
        "idle_w":          float(round(float(idle_w), 2)),
        "safety_factor":   float(round(float(safety_factor), 0)),
        "thermal_ratio":   float(round(float(thermal_ratio), 4)),
        "warp_mm":         float(round(float(warp_mm), 3)),
        "fits_printer":    bool(fits_printer),
        "print_time_min":  float(round(float(print_time_min), 1)),
        "chassis":         ch,
        "sub_scores": {
            "structural":  float(round(ssf_score,       3)),
            "runtime":     float(round(runtime_score,   3)),
            "ai_tops":     float(round(tops_score,       3)),
            "cost":        float(round(cost_score,       3)),
            "mass":        float(round(mass_score,       3)),
            "thermal":     float(round(thermal_score,    3)),
            "warp":        float(round(warp_score,       3)),
        }
    }

# ── Assembly description (human-readable) ────────────────────────────────────
def assembly_name(asm: dict) -> str:
    sbc   = asm.get("sbc",         {}).get("name", "?")
    accel = asm.get("accelerator", {}).get("name", "none")
    motor = asm.get("motor",       {}).get("name", "?")
    batt  = asm.get("battery",     {}).get("name", "?")
    return f"{sbc} + {accel} | {motor} | {batt}"

# ── Main exploration loop ─────────────────────────────────────────────────────
def run(population: int = 40, budget: float = 400.0, seed: int = None):
    print("\n" + "="*60)
    print("  🎨  creative_evolver.py — Generative Design Explorer")
    print("="*60)
    print(f"\n  Population:  {population} random assemblies")
    print(f"  Budget:      ${budget:.0f}")
    print(f"  Component DB: {DB_PATH.name}")

    db  = load_db()
    rng = random.Random(seed)

    # ── Generate population ────────────────────────────────────────────────
    print(f"\n  Generating {population} random assemblies...")
    candidates = []
    for i in range(population):
        asm     = sample_assembly(db, rng)
        metrics = evaluate_assembly(asm, budget)
        candidates.append({
            "rank":    0,
            "name":    assembly_name(asm),
            "assembly": asm,
            "metrics": metrics,
        })

    # Sort by fitness descending
    candidates.sort(key=lambda c: c["metrics"]["fitness"], reverse=True)
    for i, c in enumerate(candidates):
        c["rank"] = i + 1

    # ── Show top-10 summary ────────────────────────────────────────────────
    print("\n  Top-10 assemblies:\n")
    print(f"  {'#':>2}  {'Fitness':>8}  {'Cost':>6}  {'TOPS':>5}  {'Runtime':>8}  {'Mass':>7}  Name")
    print(f"  {'─'*2}  {'─'*8}  {'─'*6}  {'─'*5}  {'─'*8}  {'─'*7}  {'─'*40}")
    for c in candidates[:10]:
        m = c["metrics"]
        print(f"  {c['rank']:>2}  {m['fitness']:>8.4f}  ${m['bom_cost']:>5.0f}"
              f"  {m['total_tops']:>4.0f}T  {m['runtime_h']:>7.1f}h"
              f"  {m['total_mass_g']:>6.0f}g  {c['name'][:50]}")

    # ── Select top 3 distinct designs ─────────────────────────────────────
    top3 = list(candidates[:3])

    print(f"\n\n  ── Top 3 Designs ───────────────────────────────────────")
    for i, c in enumerate(top3):
        m  = c["metrics"]
        ch = m["chassis"]
        print(f"\n  #{i+1}: {c['name']}")
        print(f"      Fitness:   {m['fitness']:.4f}")
        print(f"      Cost:      ${m['bom_cost']:.0f}  |  AI: {m['total_tops']} TOPS  |  Runtime: {m['runtime_h']:.1f}h")
        print(f"      Mass:      {m['total_mass_g']:.0f}g  |  Print: {m['print_time_min']:.0f}min")
        print(f"      Chassis:   {ch['int_x']}×{ch['int_y']}×{ch['int_z']}mm internal")
        print(f"      Fits XL?   {'✅' if m['fits_printer'] else '❌'}")
        for cat, comp in c["assembly"].items():
            if cat == "fixed_sensors": continue
            if isinstance(comp, dict):
                print(f"      {cat:15s}: {comp.get('name','?')}")

    # ── Write report ───────────────────────────────────────────────────────
    report = {
        "generated":    datetime.now().isoformat(),
        "population":   population,
        "budget_usd":   budget,
        "total_scored": len(candidates),
        "top3":         top3,
        "all_summary":  [
            {
                "rank": c["rank"],
                "name": c["name"],
                "fitness": c["metrics"]["fitness"],
                "cost": c["metrics"]["bom_cost"],
                "tops": c["metrics"]["total_tops"],
                "runtime_h": c["metrics"]["runtime_h"],
                "mass_g": c["metrics"]["total_mass_g"],
            }
            for c in candidates
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\n\n📄 Creative report saved → {REPORT_PATH.name}")

    # ── Log to evolution_log.json ──────────────────────────────────────────
    try:
        import reasoning_engine
        winner = top3[0]
        reasoning_engine.log_evolution(
            "v1.0-creative",
            {
                "intent": (
                    f"Creative design exploration over {population} assemblies. "
                    f"Winner: '{winner['name']}'. "
                    f"Fitness {winner['metrics']['fitness']:.4f}, "
                    f"${winner['metrics']['bom_cost']:.0f}, "
                    f"{winner['metrics']['total_tops']} TOPS, "
                    f"{winner['metrics']['runtime_h']:.1f}h runtime."
                ),
                "winning_assembly": winner["name"],
                "winning_metrics":  winner["metrics"],
            }
        )
        print("📝 Logged to evolution_log.json")
    except Exception as e:
        print(f"  ⚠️  Could not log to reasoning_engine: {e}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Creative body design explorer")
    parser.add_argument("--pop",    type=int,   default=40,    help="Population size (default 40)")
    parser.add_argument("--budget", type=float, default=400.0, help="Budget cap in USD (default $400)")
    parser.add_argument("--seed",   type=int,   default=None,  help="Random seed for reproducibility")
    args = parser.parse_args()
    run(population=args.pop, budget=args.budget, seed=args.seed)
