"""
design_evolver.py — Iterative design optimizer for Body v1.0 chassis.

Runs 10+ iterations of a physics-based fitness function using real material
properties and geometry. Uses coordinate-descent hill climbing to find the
optimal set of parametric SCAD values. Writes the winning design back into
skeleton_v1.scad and logs every iteration to evolution_report.json.

Physics models used:
  - Von Mises wall stress + PETG compressive safety factor
  - PETG mass from density (1.27 g/cm³)
  - Thermal vent ratio (target ≥ 20% of surface)
  - PETG warp risk: δ = α × ΔT × L  (α=5e-5 /°C, ΔT=40°C)
  - Bed adhesion: first-layer footprint area
  - Prusa XL print time estimate (80mm/s, 0.2mm layers)
  - Component clearance margins
  - Overhang angle risk (45° rule)
"""

import os
import sys
import json
import re
import math
import copy
from datetime import datetime
from pathlib import Path

# Spatial Reasoning Engine
from physics_engine import (Component, WheelContact, DrivetrainConfig,
                           evaluate_design, default_v2_layout)

# ── Try numpy; fall back to math-only if not installed ───────────────────────
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

ROOT = Path(__file__).parent

# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL & PRINTER CONSTANTS  (all values from published datasheets)
# ─────────────────────────────────────────────────────────────────────────────
PETG_YIELD_MPa      = 51.0      # MPa — compressive yield (Formfutura datasheet)
PETG_DENSITY        = 1.27      # g/cm³
PETG_ALPHA          = 5.0e-5    # /°C — thermal expansion coefficient
PETG_DELTA_T        = 40.0      # °C — residual ΔT from bed to ambient
GRAVITY             = 9.81      # m/s²

# Component weights (grams, from manufacturer data / typical values)
PAYLOAD_G = {
    "pi5":       43,    # Raspberry Pi 5 PCB + heatsink
    "coral":     25,    # Coral USB Accelerator
    "camera":     8,    # Camera Module 3
    "nema17":   280,    # NEMA17 stepper motor
    "batteries": 184,   # 2× Panasonic NCR18650B (92g each)
    "pcbs_misc": 120,   # RP2040, INA219, LSM6DSOX, BME688, buck, powerboost
    "hardware":   50,   # Standoffs, M2.5/M3 screws, USB hub, cables
}
TOTAL_PAYLOAD_G = sum(PAYLOAD_G.values())   # 710 g
TOTAL_PAYLOAD_N = TOTAL_PAYLOAD_G * 1e-3 * GRAVITY  # Newtons (6.97 N)

# Prusa XL print profile
PRINT_SPEED_MM_S  = 80.0    # mm/s perimeter speed
LAYER_HEIGHT_MM   = 0.2     # mm
NOZZLE_DIA_MM     = 0.4     # mm

# Required component fit minimums (from parts_dom.md)
PI5_MIN_X    = 85.0   # mm  (Pi 5 PCB width)
PI5_MIN_Y    = 58.0   # mm  (Pi 5 PCB depth)
NEMA17_FACE  = 42.0   # mm  (NEMA17 faceplate side length)
MIN_WALL     = 3.0    # mm  (structural minimum — 3 perimeters at 0.4mm nozzle)
MIN_CLEARANCE = 3.0   # mm  (minimum gap between component and wall)

# ─────────────────────────────────────────────────────────────────────────────
# INITIAL DESIGN PARAMETERS  (sourced from skeleton_v1.scad v1.0 or active design)
# ─────────────────────────────────────────────────────────────────────────────

def _get_active_payload_and_params():
    # Base defaults
    payload = {
        "pi5":       43,    # Raspberry Pi 5 PCB + heatsink
        "coral":     25,    # Coral USB Accelerator
        "camera":     8,    # Camera Module 3
        "nema17":   280,    # NEMA17 stepper motor
        "batteries": 184,   # 2× Panasonic NCR18650B (92g each)
        "pcbs_misc": 120,   # RP2040, INA219, LSM6DSOX, BME688, buck, powerboost
        "hardware":   50,   # Standoffs, M2.5/M3 screws, USB hub, cables
    }
    
    params = {
        "wall":    3.5,    # mm
        "int_x":  95.0,   # mm — internal width
        "int_y":  68.0,   # mm — internal depth
        "int_z": 130.0,   # mm — internal height
        "vent_w": 12.0,   # mm — vent slot width
        "vent_h": 35.0,   # mm — vent slot height
        "n_vents": 12,    # count — total cooling vents (all 4 sides)
        "boss_od":  7.0,  # mm — standoff boss outer diameter
        "boss_h":   5.0,  # mm — standoff boss height
        "has_wheels": 1,  # 1 = true, 0 = false
        "wheel_dia": 65.0, # mm
        "wheel_width": 26.0, # mm
        "ground_clear": 15.0, # mm
        "gear_ratio": 5.0,    # mm
    }
    
    cre_file = ROOT / "creative_report.json"
    if cre_file.exists():
        try:
            cre_report = json.loads(cre_file.read_text())
            if cre_report and "top3" in cre_report and cre_report["top3"]:
                best = cre_report["top3"][0]
                # Override payload base
                payload = {"components": best["metrics"]["total_mass_g"] - best["metrics"]["chassis_mass_g"]}
                # Override params
                ch = best["metrics"]["chassis"]
                params["wall"] = ch.get("wall", 3.5)
                params["int_x"] = ch.get("int_x", 95.0)
                params["int_y"] = ch.get("int_y", 68.0)
                params["int_z"] = ch.get("int_z", 130.0)
                params["vent_w"] = ch.get("vent_w", 12.0)
                params["vent_h"] = ch.get("vent_h", 35.0)
                params["n_vents"] = ch.get("n_vents", 12)
                params["ground_clear"] = ch.get("ground_clear", 15.0)
                asm = best.get("assembly", {})
                wheels = asm.get("wheels", {})
                if wheels and wheels.get("id") != "none":
                    params["has_wheels"] = 1
                    params["wheel_dia"] = wheels.get("diameter_mm", 65.0)
                    params["wheel_width"] = wheels.get("width_mm", 26.0)
                else:
                    params["has_wheels"] = 0
                print("🧬 Initializing design_evolver from generative design winner...")
        except Exception:
            pass
            
    return payload, params

PAYLOAD_G, INITIAL_PARAMS = _get_active_payload_and_params()
TOTAL_PAYLOAD_G = sum(PAYLOAD_G.values())
TOTAL_PAYLOAD_N = TOTAL_PAYLOAD_G * 1e-3 * GRAVITY

PI5_MIN_X    = 85.0   # minimum internal width constraints
PI5_MIN_Y    = 58.0
NEMA17_FACE  = 42.0

# Tunable parameter search space: {name: (min, max, step)}
SEARCH_SPACE = {
    "wall":    (MIN_WALL, 5.5,  0.25),
    "int_x":  (PI5_MIN_X + MIN_CLEARANCE*2, 115.0, 2.0),
    "int_y":  (PI5_MIN_Y + MIN_CLEARANCE*2, 88.0,  2.0),
    "int_z":  (118.0, 165.0, 5.0),
    "vent_w": (8.0,   20.0,  2.0),
    "vent_h": (25.0,  55.0,  5.0),
    "n_vents":(8,     20,    2),
    "wheel_dia": (40.0, 90.0, 5.0),
    "ground_clear": (10.0, 30.0, 2.0),
    "gear_ratio": (1.0, 15.0, 1.0),
}


# ─────────────────────────────────────────────────────────────────────────────
# PHYSICS FITNESS FUNCTION
# ─────────────────────────────────────────────────────────────────────────────
def compute_fitness(p: dict) -> dict:
    """
    Evaluate a parameter set using real material physics.
    Returns a dict with all sub-scores and a composite fitness (0–1).
    """
    wall   = p["wall"]
    int_x  = p["int_x"];  int_y = p["int_y"];  int_z = p["int_z"]
    vent_w = p["vent_w"]; vent_h = p["vent_h"]; n_vents = p["n_vents"]
    boss_od = p.get("boss_od", 7.0)
    boss_h  = p.get("boss_h",  5.0)

    out_x = int_x + 2 * wall
    out_y = int_y + 2 * wall
    out_z = int_z + wall        # open top for lid

    # ── 1. STRUCTURAL SAFETY FACTOR ──────────────────────────────────────────
    # Payload compresses the 4 outer walls in the Z axis.
    # Treat as uniform axial compression: σ = F / A_walls
    # A_walls = perimeter of shell cross-section × wall thickness
    perimeter = 2 * (out_x + out_y)                    # mm
    A_walls_mm2 = perimeter * wall - 4 * wall**2        # subtract corners (counted twice)
    A_walls_m2  = A_walls_mm2 * 1e-6                   # m²
    stress_Pa   = TOTAL_PAYLOAD_N / A_walls_m2          # Pa
    stress_MPa  = stress_Pa * 1e-6                      # MPa
    safety_factor = PETG_YIELD_MPa / stress_MPa         # dimensionless (higher = safer)
    ssf_score     = min(1.0, safety_factor / 20.0)      # safety factor of 20 = 1.0

    # ── 2. THERMAL VENT RATIO ─────────────────────────────────────────────────
    # Vent slots cut through all 4 walls. We have n_vents split across 4 sides.
    total_vent_area_mm2  = n_vents * vent_w * vent_h    # total vent open area mm²
    chassis_surface_mm2  = (                            # all exterior faces
        2 * (out_x * out_z) +
        2 * (out_y * out_z) +
        out_x * out_y                                   # bottom (top is open/lid)
    )
    thermal_ratio = total_vent_area_mm2 / chassis_surface_mm2
    thermal_score = min(1.0, thermal_ratio / 0.15)  # 15% vent-to-surface ratio = 1.0

    # ── 3. PETG MASS ──────────────────────────────────────────────────────────
    # Shell volume = outer box − inner cavity − vent volumes + boss volumes
    outer_vol_mm3  = out_x * out_y * out_z
    inner_vol_mm3  = int_x * int_y * int_z
    vent_vol_mm3   = n_vents * vent_w * vent_h * wall   # through-wall cutouts
    n_bosses       = 14                                  # counted in SCAD (Pi4 + camera2 + sensor6 + NEMA4-holes≈not material)
    boss_vol_mm3   = n_bosses * math.pi * (boss_od/2)**2 * boss_h
    shell_vol_mm3  = outer_vol_mm3 - inner_vol_mm3 - vent_vol_mm3 + boss_vol_mm3
    shell_vol_cm3  = max(0, shell_vol_mm3) / 1000.0
    mass_g         = shell_vol_cm3 * PETG_DENSITY       # grams
    if p.get("has_wheels", 0):
        # 2 rubber wheels + caster + motors estimate
        mass_g += 80 * 2 + 15 + 280   # 160g wheels + 15g caster + 280g NEMA17(base)
    mass_score = max(0.0, 1.0 - mass_g / 1500.0)  # 1.5kg = zero score

    # ── 4. PRINT TIME ─────────────────────────────────────────────────────────
    # Prusa XL: perimeter passes + top/bottom solid layers + sparse infill (15%)
    perimeters_per_layer = wall / NOZZLE_DIA_MM           # number of perimeter loops
    n_layers             = out_z / LAYER_HEIGHT_MM
    # Path length per layer: perimeter loop × number of perimeters + infill estimate
    path_per_layer_mm    = (2 * (out_x + out_y)) * perimeters_per_layer + 0.15 * int_x * int_y
    total_path_mm        = n_layers * path_per_layer_mm
    print_time_s         = total_path_mm / PRINT_SPEED_MM_S
    print_time_min       = print_time_s / 60.0

    # ── 5. PETG WARP RISK ─────────────────────────────────────────────────────
    # Linear shrinkage formula: δ = α × ΔT × L
    # PETG: α = 5×10⁻⁵ /°C, ΔT = 40°C (glass→ambient for residual stress zone)
    max_span      = max(out_x, out_y)                   # mm — longest unsupported span
    warp_mm       = PETG_ALPHA * PETG_DELTA_T * max_span  # mm displacement at corners
    # Risk score 0–1: 0.1mm acceptable, 1.0mm = serious problem
    warp_risk     = min(1.0, warp_mm / 1.0)

    # ── 6. BED ADHESION ───────────────────────────────────────────────────────
    # PETG bonds well to PEI sheet. First-layer footprint must be >4000mm² for
    # good adhesion without brim. Formula: adhesion_score based on footprint area.
    bed_area_mm2  = out_x * out_y                       # first-layer footprint
    adhesion_score = min(1.0, bed_area_mm2 / 4000.0)   # normalised (4000mm² = 1.0)

    # ── 7. COMPONENT CLEARANCE MARGINS ────────────────────────────────────────
    # Margin = (cavity − component) / 2 per side
    pi5_margin_x  = (int_x - PI5_MIN_X) / 2.0
    pi5_margin_y  = (int_y - PI5_MIN_Y) / 2.0
    nema_margin_x = (int_x - NEMA17_FACE) / 2.0
    nema_margin_y = (int_y - NEMA17_FACE) / 2.0
    min_margin    = min(pi5_margin_x, pi5_margin_y, nema_margin_x, nema_margin_y)
    clearance_score = min(1.0, max(0.0, min_margin / 12.0))  # 12mm = perfect score

    # ── 8. OVERHANG RISK ──────────────────────────────────────────────────────
    # Standoff bosses: horizontal ratio = (boss_od/2) / boss_h
    # At 45° rule: ratio ≤ 1.0 is safe (tan45° = 1)
    boss_overhang_ratio = (boss_od / 2.0) / boss_h     # ≤ 1.0 = safe
    overhang_risk       = max(0.0, boss_overhang_ratio - 1.0)  # 0 = safe

    # ── 9. SPATIAL REASONING SCORE (v2.0 Logic) ──────────────────────────────
    # Initialize component layout with current params
    layout = default_v2_layout(
        ground_clear=p.get("ground_clear", 15.0),
        wall=wall,
        int_x=int_x,
        int_y=int_y,
        gear_ratio=p.get("gear_ratio", 5.0)
    )

    spatial = evaluate_design(
        layout["components"],
        layout["contacts"],
        layout["drivetrain"],
        chassis_mass_g=mass_g
    )

    # ── 10. COMPOSITE FITNESS ──────────────────────────────────────────────────
    # Weights re-balanced for engineering intelligence
    # Spatial score (includes stability, mobility, packaging, CoG) accounts for 60%
    fitness = (
        0.60 * spatial["composite_score"] +
        0.10 * ssf_score +
        0.10 * thermal_score +
        0.10 * mass_score +
        0.10 * print_time_min / 720.0 # printability weight
    )

    # Penetration penalty: massive hit for overlapping components
    if spatial["collisions"]["has_collisions"]:
        fitness *= 0.1

    return {
        "fitness":        round(fitness, 5),
        "safety_factor":  round(safety_factor, 1),
        "stress_mpa":     round(stress_MPa, 5),
        "thermal_ratio":  round(thermal_ratio, 4),
        "mass_g":         round(mass_g, 1),
        "print_time_min": round(print_time_min, 1),
        "warp_mm":        round(warp_mm, 3),
        "warp_risk":      round(warp_risk, 4),
        "bed_area_mm2":   round(bed_area_mm2, 1),
        "adhesion_score": round(adhesion_score, 3),
        "shell_vol_cm3":  round(shell_vol_cm3, 3), # Needed for simulate_print_pull
        "min_clearance_mm": round(min_margin, 2),  # Needed for simulate_print_pull
        "clearance_score":  round(clearance_score, 3),
        "outer_dims_mm":  [round(out_x, 1), round(out_y, 1), round(out_z, 1)],
        "spatial":        spatial, # Full physics breakdown
        "sub_scores": {
            "spatial":     round(spatial["composite_score"], 3),
            "structural":  round(ssf_score, 3),
            "thermal":     round(thermal_score, 3),
            "mass":        round(mass_score, 3),
            "print":       round(print_time_min / 720.0, 3)
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# HILL-CLIMBING OPTIMIZER
# ─────────────────────────────────────────────────────────────────────────────
def is_valid(p: dict) -> bool:
    """Enforce hard physical constraints."""
    if p["wall"]  < MIN_WALL:                       return False
    if p["int_x"] < PI5_MIN_X + MIN_CLEARANCE * 2: return False
    if p["int_y"] < PI5_MIN_Y + MIN_CLEARANCE * 2: return False
    if p["int_z"] < 118.0:                          return False
    if p["vent_w"] <= 0 or p["vent_h"] <= 0:       return False
    if p["n_vents"] < 4:                            return False
    return True


def simulate_print_pull(params: dict, metrics: dict, iteration: int) -> dict:
    """
    Simulate a print cycle:
     - Estimate filament length (Prusa slicer approximation)
     - Assess bed removal stress (warp displacement vs footprint ratio)
     - Report pass/fail + recommendations
    """
    out_x, out_y, out_z = metrics["outer_dims_mm"]
    warp      = metrics["warp_mm"]
    mass      = metrics["mass_g"]
    bed_area  = metrics["bed_area_mm2"]

    # Filament length (Prusa XL, 0.4mm nozzle, 1.75mm filament)
    # volume = shell_vol_cm3 in cm³; filament cross-section area = π(0.175/2)² cm²
    fil_cross_cm2  = math.pi * (0.175 / 2) ** 2    # = 0.02405 cm²
    fil_length_cm  = metrics["shell_vol_cm3"] / fil_cross_cm2
    fil_length_m   = fil_length_cm / 100.0

    # Bed removal stress: if warp > 0.5mm and bed_area < 5000mm² → risk
    removal_risk   = "LOW"
    if warp > 0.5 and bed_area < 5000:
        removal_risk = "HIGH"
    elif warp > 0.3:
        removal_risk = "MEDIUM"

    # Part quality verdict
    verdict     = "PASS" if metrics["fitness"] > 0.70 else ("REVIEW" if metrics["fitness"] > 0.55 else "FAIL")
    sf          = metrics["safety_factor"]

    # Recommendations for next iteration
    recs = []
    if metrics["thermal_ratio"] < 0.18:
        recs.append("Increase vent area (n_vents or vent dimensions)")
    if metrics["mass_g"] > 300:
        recs.append("Reduce wall thickness or int_z to lower mass")
    if metrics["min_clearance_mm"] > 15.0:
        recs.append("Internal cavity oversized — can reduce int_x/int_y slightly")
    if sf > 800:
        recs.append(f"Safety factor {sf}x is excessive — reduce wall to save mass")
    if metrics["warp_mm"] > 0.4:
        recs.append("Warp risk: reduce max chassis span or add chamfered footprint")
    if not recs:
        recs.append("No structural issues detected — marginal refinements only")

    return {
        "iteration":       iteration,
        "verdict":         verdict,
        "filament_length_m": round(fil_length_m, 2),
        "removal_risk":    removal_risk,
        "recommendations": recs,
    }


def hill_climb(iterations: int = 10) -> tuple:
    """
    Coordinate-descent hill climbing over SEARCH_SPACE.
    Returns (best_params, full_history).
    """
    best_params  = copy.deepcopy(INITIAL_PARAMS)
    best_metrics = compute_fitness(best_params)
    best_fitness = best_metrics["fitness"]

    history = []

    for i in range(iterations):
        improved     = False
        best_delta   = None
        best_cand    = None
        best_m_cand  = None

        # Try every parameter × every direction
        for pname, (p_min, p_max, step) in SEARCH_SPACE.items():
            for multiplier in [1, -1, 2, -2, 0.5, -0.5]:
                delta = step * multiplier
                candidate = copy.deepcopy(best_params)
                new_val   = candidate[pname] + delta

                # Clamp and coerce int params
                new_val = max(p_min, min(p_max, new_val))
                if pname == "n_vents":
                    new_val = int(round(new_val))
                candidate[pname] = new_val

                if not is_valid(candidate):
                    continue

                m = compute_fitness(candidate)
                if m["fitness"] > best_fitness + 1e-4:
                    best_fitness = m["fitness"]
                    best_delta   = (pname, delta)
                    best_cand    = copy.deepcopy(candidate)
                    best_m_cand  = m
                    improved     = True

        if improved:
            best_params  = best_cand
            best_metrics = best_m_cand

        print_analysis = simulate_print_pull(best_params, best_metrics, i + 1)

        prev_fitness = history[-1]["metrics"]["fitness"] if history else INITIAL_PARAMS.copy()
        delta_fitness = best_metrics["fitness"] - (history[-1]["metrics"]["fitness"] if history else compute_fitness(INITIAL_PARAMS)["fitness"])

        entry = {
            "iteration":     i + 1,
            "timestamp":     datetime.now().isoformat(),
            "params":        copy.deepcopy(best_params),
            "metrics":       best_metrics,
            "print_sim":     print_analysis,
            "improved":      improved,
            "delta_fitness": round(delta_fitness, 5),
            "changed_param": best_delta[0] if best_delta else None,
            "changed_by":    best_delta[1] if best_delta else 0,
        }
        history.append(entry)

        # Live console output
        v = best_metrics
        print(f"\n{'='*60}")
        print(f"  Iteration {i+1:2d}/{iterations}  |  Fitness: {v['fitness']:.4f}"
              f"  ({'+' if delta_fitness>=0 else ''}{delta_fitness:.4f})")
        print(f"  Changed:   {entry['changed_param']} by {entry['changed_by']:+.2f}" if improved else "  No improvement found")
        print(f"  Safety:    {v['safety_factor']:.0f}x  (σ={v['stress_mpa']:.4f} MPa)")
        print(f"  Thermal:   {v['thermal_ratio']*100:.1f}%  vent/surface")
        print(f"  Mass:      {v['mass_g']:.0f} g  |  Print: {v['print_time_min']:.0f} min")
        print(f"  Warp δ:    {v['warp_mm']:.3f} mm  |  Clearance: {v['min_clearance_mm']:.1f} mm")
        print(f"  Verdict:   {print_analysis['verdict']}  |  Removal: {print_analysis['removal_risk']}")
        for r in print_analysis["recommendations"]:
            print(f"    ➤ {r}")

    return best_params, history


# ─────────────────────────────────────────────────────────────────────────────
# SCAD PARAMETER WRITER
# ─────────────────────────────────────────────────────────────────────────────
def write_scad_params(params: dict, scad_path: Path):
    """
    Update the tunable parameter block in skeleton_v1.scad with winning values.
    """
    text = scad_path.read_text()

    replacements = {
        "wall":   f"wall           = {params['wall']:.2f};",
        "int_x":  f"int_x     = {params['int_x']:.0f};",
        "int_y":  f"int_y     = {params['int_y']:.0f};",
        "int_z":  f"int_z     = {params['int_z']:.0f};",
        "vent_w": f"vent_w = {params['vent_w']:.0f};",
        "vent_h": f"vent_h = {params['vent_h']:.0f};",
        "n_vents":f"n_vents = {int(params['n_vents'])};",
        "has_wheels":   f"has_wheels     = {int(params['has_wheels'])};",
        "wheel_dia":    f"wheel_dia      = {params['wheel_dia']:.1f};",
        "wheel_width":  f"wheel_width    = {params['wheel_width']:.1f};",
        "ground_clear": f"ground_clear   = {params['ground_clear']:.1f};",
    }

    patterns = {
        "wall":    r"wall\s+=\s+[\d.]+;",
        "int_x":   r"int_x\s+=\s+[\d.]+;",
        "int_y":   r"int_y\s+=\s+[\d.]+;",
        "int_z":   r"int_z\s+=\s+[\d.]+;",
        "vent_w":  r"vent_w\s+=\s+[\d.]+;",
        "vent_h":  r"vent_h\s+=\s+[\d.]+;",
        "n_vents": r"n_vents\s+=\s+[\d]+;",
        "has_wheels":   r"has_wheels\s+=\s+[\d]+;",
        "wheel_dia":    r"wheel_dia\s+=\s+[\d.]+;",
        "wheel_width":  r"wheel_width\s+=\s+[\d.]+;",
        "ground_clear": r"ground_clear\s+=\s+[\d.]+;",
    }

    for key, pattern in patterns.items():
        replacement = replacements[key]
        new_text    = re.sub(pattern, replacement, text)
        if new_text != text:
            text = new_text
            print(f"  Updated SCAD: {replacement.strip()}")

    scad_path.write_text(text)
    print(f"\n✅ skeleton_v1.scad updated with winning parameters.")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run(iterations: int = 10):
    global INITIAL_PARAMS
    
    # ── Resume Logic ──────────────────────────────────────────────────────────
    report_path = ROOT / "evolution_report.json"
    start_iter = 0
    if report_path.exists():
        try:
            old_report = json.loads(report_path.read_text())
            p = old_report["winner"]["params"]
            if "gear_ratio" not in p: p["gear_ratio"] = 5.0
            if "ground_clear" not in p: p["ground_clear"] = 15.0
            INITIAL_PARAMS.update(p)
            start_iter = old_report.get("iterations", 10)
            print(f"♻️  Resuming from existing winner (Iter {start_iter})...")
        except Exception as e:
            print(f"⚠️  Could not load existing report for resume: {e}")

    print("\n" + "=" * 60)
    print(f"  🧬  design_evolver.py — Body v1.0 Optimizer [Iter {start_iter+1}–{start_iter+iterations}]")
    print("=" * 60)
    print(f"\n  Payload mass:  {TOTAL_PAYLOAD_G}g ({TOTAL_PAYLOAD_N:.2f}N)")
    print(f"  PETG yield:    {PETG_YIELD_MPa} MPa")
    print(f"  PETG density:  {PETG_DENSITY} g/cm³")
    print(f"  Warp model:    α={PETG_ALPHA}/°C, ΔT={PETG_DELTA_T}°C")
    print(f"  Iterations:    {iterations}")

    # For local scope visibility in reasoning_engine log call later
    globals()["start_iter"] = start_iter

    # Baseline
    baseline = compute_fitness(INITIAL_PARAMS)
    print(f"\n  Baseline fitness: {baseline['fitness']:.4f}")
    print(f"  Baseline mass:    {baseline['mass_g']:.0f}g")
    print(f"  Baseline safety:  {baseline['safety_factor']:.0f}x")

    # Evolve
    best_params, history = hill_climb(iterations)
    best_metrics         = history[-1]["metrics"]

    # Summary
    print("\n" + "=" * 60)
    print("  📊  EVOLUTION COMPLETE")
    print("=" * 60)
    delta = best_metrics["fitness"] - baseline["fitness"]
    print(f"\n  Fitness:  {baseline['fitness']:.4f} → {best_metrics['fitness']:.4f}  ({'+' if delta>=0 else ''}{delta:.4f})")
    print(f"  Mass:     {baseline['mass_g']:.0f}g → {best_metrics['mass_g']:.0f}g")
    print(f"  Safety:   {baseline['safety_factor']:.0f}x → {best_metrics['safety_factor']:.0f}x")
    print(f"  Thermal:  {baseline['thermal_ratio']*100:.1f}% → {best_metrics['thermal_ratio']*100:.1f}%")
    print(f"  Warp δ:   {baseline['warp_mm']:.3f}mm → {best_metrics['warp_mm']:.3f}mm")

    print("\n  Winning parameters:")
    for k, v in best_params.items():
        orig = INITIAL_PARAMS.get(k, "—")
        changed = "←" if v != orig else ""
        print(f"    {k:12s}: {orig} → {v} {changed}")

    # Write report
    report = {
        "generated":   datetime.now().isoformat(),
        "iterations":  start_iter + iterations,
        "baseline":    {"params": INITIAL_PARAMS, "metrics": baseline},
        "winner":      {"params": best_params,    "metrics": best_metrics},
        "history":     history,
        "payload_summary": PAYLOAD_G,
        "total_payload_g": TOTAL_PAYLOAD_G,
        "material": {
            "yield_mpa":  PETG_YIELD_MPa,
            "density":    PETG_DENSITY,
            "alpha":      PETG_ALPHA,
            "delta_t":    PETG_DELTA_T,
        },
    }
    report_path = ROOT / "evolution_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n📄 Report saved → {report_path.name}")

    # Update SCAD
    scad_path = ROOT / "skeleton_v1.scad"
    if scad_path.exists():
        print("\n📝 Writing winning params to skeleton_v1.scad...")
        write_scad_params(best_params, scad_path)
    else:
        print("  ⚠️  skeleton_v1.scad not found — skipping SCAD update")

    # Log to evolution_log.json via reasoning_engine pattern
    try:
        import reasoning_engine
        reasoning_engine.log_evolution(
            f"v1.0-evolved-iter{start_iter + iterations}",
            {
                "intent": (
                    f"Chassis further optimized from Iter {start_iter} to {start_iter + iterations}. "
                    f"Fitness improved {delta:+.4f} to {best_metrics['fitness']:.4f}. "
                    f"Mass: {best_metrics['mass_g']:.0f}g, "
                    f"Safety: {best_metrics['safety_factor']:.0f}x, "
                    f"Thermal: {best_metrics['thermal_ratio']*100:.1f}%."
                ),
                "winning_params": best_params,
                "winning_metrics": best_metrics,
            }
        )
        print("📝 Evolution entry logged to evolution_log.json")
    except Exception as e:
        print(f"  ⚠️  Could not log to reasoning_engine: {e}")

    return report


if __name__ == "__main__":
    run(iterations=10)
