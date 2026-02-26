"""
physics_engine.py — Spatial Reasoning Engine for Body v2.0

Provides physics-based analysis of robot body designs in 3D space.
This module understands gravity, torque, stability, and mechanical
feasibility — enabling the optimizer to design bodies that actually
work in the real human 3D world.

Analysis layers:
  1. Center of Gravity (CoG) — weighted 3D centroid
  2. Stability Analysis   — support polygon + tip-over margins
  3. Torque Budget         — motor capability vs. required force
  4. Drivetrain Model      — gear ratio, max incline, top speed
  5. Collision Detection   — AABB overlap for all components
  6. Wire Routing          — connection feasibility scoring
"""

import math
from typing import List, Dict, Tuple, Optional

# ─── Physical Constants ─────────────────────────────────────────────────────
GRAVITY = 9.81          # m/s²
PETG_DENSITY = 1.27     # g/cm³ (chassis material)

# ─── NEMA17 Motor Specs ─────────────────────────────────────────────────────
NEMA17_TORQUE_NM = 0.40     # N·m at rated current (typical 17HS4401)
NEMA17_RPM       = 200      # RPM at rated torque
NEMA17_MASS_G    = 280      # grams
NEMA17_DIMS_MM   = [42, 42, 40]  # W × D × H


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class Component:
    """A physical component with mass, position, and bounding box."""

    def __init__(self, label: str, mass_g: float,
                 x: float, y: float, z: float,
                 w: float, d: float, h: float,
                 connections: List[str] = None):
        self.label = label
        self.mass_g = mass_g
        self.x, self.y, self.z = x, y, z     # Center position (mm)
        self.w, self.d, self.h = w, d, h     # Bounding box (mm)
        self.connections = connections or []   # Labels of connected components

    @property
    def mass_kg(self) -> float:
        return self.mass_g / 1000.0

    @property
    def bbox_min(self) -> Tuple[float, float, float]:
        return (self.x - self.w/2, self.y - self.d/2, self.z - self.h/2)

    @property
    def bbox_max(self) -> Tuple[float, float, float]:
        return (self.x + self.w/2, self.y + self.d/2, self.z + self.h/2)

    @property
    def position(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)


class WheelContact:
    """A ground contact point (wheel or caster)."""

    def __init__(self, label: str, x: float, y: float, radius: float):
        self.label = label
        self.x = x      # mm, chassis-relative
        self.y = y       # mm, chassis-relative
        self.radius = radius  # mm


class DrivetrainConfig:
    """Describes the mechanical drive system."""

    def __init__(self, motor_torque_nm: float = NEMA17_TORQUE_NM,
                 motor_rpm: float = NEMA17_RPM,
                 gear_ratio: float = 5.0,
                 wheel_radius_mm: float = 32.5,
                 num_drive_wheels: int = 2):
        self.motor_torque_nm = motor_torque_nm
        self.motor_rpm = motor_rpm
        self.gear_ratio = gear_ratio
        self.wheel_radius_mm = wheel_radius_mm
        self.num_drive_wheels = num_drive_wheels

    @property
    def wheel_torque_nm(self) -> float:
        """Torque delivered at each drive wheel."""
        return (self.motor_torque_nm * self.gear_ratio) / self.num_drive_wheels

    @property
    def wheel_rpm(self) -> float:
        """Wheel RPM after gear reduction."""
        return self.motor_rpm / self.gear_ratio

    @property
    def top_speed_ms(self) -> float:
        """Top speed in m/s."""
        wheel_circumference_m = 2 * math.pi * (self.wheel_radius_mm / 1000.0)
        return self.wheel_rpm / 60.0 * wheel_circumference_m


# =============================================================================
# 1. CENTER OF GRAVITY
# =============================================================================

def compute_cog(components: List[Component],
                chassis_mass_g: float = 0,
                chassis_center: Tuple[float, float, float] = (0, 0, 60)
                ) -> Dict:
    """
    Compute the 3D center of gravity for the entire assembly.

    Returns:
        dict with keys: cog_x, cog_y, cog_z (mm), total_mass_g,
        cog_height_ratio (0-1, lower = more stable)
    """
    total_mass = chassis_mass_g
    mx, my, mz = (chassis_mass_g * chassis_center[0],
                   chassis_mass_g * chassis_center[1],
                   chassis_mass_g * chassis_center[2])

    for c in components:
        total_mass += c.mass_g
        mx += c.mass_g * c.x
        my += c.mass_g * c.y
        mz += c.mass_g * c.z

    if total_mass == 0:
        return {"cog_x": 0, "cog_y": 0, "cog_z": 0, "total_mass_g": 0,
                "cog_height_ratio": 0}

    cog_x = mx / total_mass
    cog_y = my / total_mass
    cog_z = mz / total_mass

    # Find the topmost component to normalize height
    max_z = max((c.z + c.h/2 for c in components), default=1)
    height_ratio = cog_z / max_z if max_z > 0 else 0

    return {
        "cog_x": round(cog_x, 2),
        "cog_y": round(cog_y, 2),
        "cog_z": round(cog_z, 2),
        "total_mass_g": round(total_mass, 1),
        "cog_height_ratio": round(height_ratio, 3),
    }


# =============================================================================
# 2. STABILITY ANALYSIS
# =============================================================================

def compute_stability(cog: Dict, contacts: List[WheelContact]) -> Dict:
    """
    Evaluate static stability by checking if the CoG projection
    falls within the support polygon formed by ground contacts.

    Uses the signed-area method to check point-in-polygon, then
    computes the minimum distance to each edge (stability margin).

    Returns:
        dict with: is_stable (bool), margin_mm, margin_pct,
        support_polygon (list of [x,y] points),
        tip_angles (dict of direction → degrees before tip-over)
    """
    if len(contacts) < 3:
        # With < 3 contacts, static stability is impossible
        # (2 wheels + caster minimum for differential drive)
        return {
            "is_stable": len(contacts) >= 2,  # Can balance momentarily
            "margin_mm": 0,
            "margin_pct": 0,
            "support_polygon": [[c.x, c.y] for c in contacts],
            "tip_angles": {},
            "warning": "Need ≥3 ground contacts for static stability"
        }

    # Build support polygon (convex hull of contact points in XY)
    points = [(c.x, c.y) for c in contacts]
    hull = _convex_hull(points)

    # Check if CoG projection (x,y) is inside the hull
    cog_xy = (cog["cog_x"], cog["cog_y"])
    inside = _point_in_polygon(cog_xy, hull)

    # Minimum distance from CoG to each edge of the support polygon
    min_dist = float('inf')
    for i in range(len(hull)):
        j = (i + 1) % len(hull)
        dist = _point_to_segment_dist(cog_xy, hull[i], hull[j])
        min_dist = min(min_dist, dist)

    # Compute stability as ratio of margin to polygon radius
    centroid = (sum(p[0] for p in hull) / len(hull),
                sum(p[1] for p in hull) / len(hull))
    max_radius = max(math.dist(centroid, p) for p in hull) or 1

    # Tip-over angles (how far you can tilt before CoG leaves polygon)
    tip_angles = {}
    cog_h = cog["cog_z"]
    if cog_h > 0:
        for direction, dx, dy in [("forward", 0, 1), ("backward", 0, -1),
                                   ("left", -1, 0), ("right", 1, 0)]:
            # Find the nearest polygon edge in this direction
            edge_dist = _directional_margin(cog_xy, hull, dx, dy)
            angle = math.degrees(math.atan2(edge_dist, cog_h))
            tip_angles[direction] = round(angle, 1)

    return {
        "is_stable": inside,
        "margin_mm": round(min_dist, 2) if inside else round(-min_dist, 2),
        "margin_pct": round((min_dist / max_radius) * 100, 1) if inside else 0,
        "support_polygon": [[p[0], p[1]] for p in hull],
        "tip_angles": tip_angles,
    }


# =============================================================================
# 3. TORQUE BUDGET
# =============================================================================

def compute_torque_budget(total_mass_g: float,
                          drivetrain: DrivetrainConfig) -> Dict:
    """
    Can the motor actually move this robot?

    Computes:
      - Required torque to move on flat ground (rolling resistance)
      - Required torque to climb various inclines
      - Maximum climbable incline angle
      - Top speed on flat ground
    """
    mass_kg = total_mass_g / 1000.0
    weight_n = mass_kg * GRAVITY
    wheel_r_m = drivetrain.wheel_radius_mm / 1000.0

    # Rolling resistance (indoor, hard floor: Crr ≈ 0.01)
    crr = 0.015
    rolling_force = weight_n * crr
    rolling_torque = rolling_force * wheel_r_m

    # Available wheel torque
    available_torque = drivetrain.wheel_torque_nm

    # Max incline: sin(θ) = available_torque / (mass × g × wheel_radius)
    max_force = available_torque / wheel_r_m
    sin_max = min(max_force / weight_n, 1.0)
    max_incline_deg = math.degrees(math.asin(sin_max))

    # Torque required at specific inclines
    incline_analysis = {}
    for angle in [0, 5, 10, 15, 20, 30]:
        required_force = weight_n * math.sin(math.radians(angle)) + rolling_force
        required_torque = required_force * wheel_r_m
        can_climb = required_torque <= available_torque
        margin = (available_torque - required_torque) / available_torque * 100
        incline_analysis[f"{angle}°"] = {
            "required_torque_nm": round(required_torque, 4),
            "can_climb": can_climb,
            "torque_margin_pct": round(margin, 1),
        }

    return {
        "available_wheel_torque_nm": round(available_torque, 4),
        "rolling_resistance_torque_nm": round(rolling_torque, 4),
        "max_incline_deg": round(max_incline_deg, 1),
        "top_speed_ms": round(drivetrain.top_speed_ms, 3),
        "top_speed_kmh": round(drivetrain.top_speed_ms * 3.6, 2),
        "gear_ratio": drivetrain.gear_ratio,
        "incline_analysis": incline_analysis,
        "verdict": "MOBILE" if max_incline_deg > 5 else "MARGINAL" if max_incline_deg > 0 else "IMMOBILE",
    }


# =============================================================================
# 4. COLLISION DETECTION
# =============================================================================

def check_collisions(components: List[Component],
                     min_clearance_mm: float = 2.0) -> Dict:
    """
    AABB (Axis-Aligned Bounding Box) collision detection.
    Checks all component pairs for overlap or insufficient clearance.

    Returns:
        dict with: has_collisions (bool), collision_count, pairs (list),
        min_clearance_found (mm)
    """
    collisions = []
    min_found = float('inf')

    for i in range(len(components)):
        for j in range(i + 1, len(components)):
            a, b = components[i], components[j]
            gap = _aabb_gap(a, b)
            min_found = min(min_found, gap)

            if gap < min_clearance_mm:
                collisions.append({
                    "a": a.label, "b": b.label,
                    "gap_mm": round(gap, 2),
                    "overlap": gap < 0,
                })

    return {
        "has_collisions": any(c["overlap"] for c in collisions),
        "clearance_violations": len(collisions),
        "collision_pairs": collisions,
        "min_clearance_mm": round(min_found, 2) if min_found != float('inf') else 0,
    }


def _aabb_gap(a: Component, b: Component) -> float:
    """Compute the minimum gap between two AABBs. Negative = overlap."""
    gaps = []
    for dim in range(3):
        a_min = [a.bbox_min[0], a.bbox_min[1], a.bbox_min[2]][dim]
        a_max = [a.bbox_max[0], a.bbox_max[1], a.bbox_max[2]][dim]
        b_min = [b.bbox_min[0], b.bbox_min[1], b.bbox_min[2]][dim]
        b_max = [b.bbox_max[0], b.bbox_max[1], b.bbox_max[2]][dim]

        gap = max(b_min - a_max, a_min - b_max)
        gaps.append(gap)

    # If any gap is positive, the boxes don't overlap on that axis
    # The min gap across all axes where they DO overlap gives penetration
    if all(g < 0 for g in gaps):
        return max(gaps)  # Penetration depth (negative)
    else:
        return max(g for g in gaps if g >= 0)  # Separation distance


# =============================================================================
# 5. WIRE ROUTING
# =============================================================================

def compute_wire_routing(components: List[Component]) -> Dict:
    """
    Score wiring feasibility using Manhattan distances between
    connected components. Shorter routes = better packaging.
    """
    comp_map = {c.label: c for c in components}
    routes = []
    total_length = 0

    for c in components:
        for target_label in c.connections:
            if target_label in comp_map:
                t = comp_map[target_label]
                # Manhattan distance in 3D
                dist = abs(c.x - t.x) + abs(c.y - t.y) + abs(c.z - t.z)
                routes.append({
                    "from": c.label, "to": target_label,
                    "distance_mm": round(dist, 1),
                })
                total_length += dist

    # Score: penalize long routes, bonus for short ones
    avg_dist = total_length / max(len(routes), 1)
    score = max(0, 1.0 - (avg_dist / 200.0))  # 200mm = terrible, 0mm = perfect

    return {
        "routes": routes,
        "total_wire_mm": round(total_length, 1),
        "avg_distance_mm": round(avg_dist, 1),
        "routing_score": round(score, 3),
    }


# =============================================================================
# 6. COMPOSITE SPATIAL SCORE
# =============================================================================

def evaluate_design(components: List[Component],
                    contacts: List[WheelContact],
                    drivetrain: DrivetrainConfig,
                    chassis_mass_g: float = 400,
                    chassis_center: Tuple[float, float, float] = (0, 0, 60)
                    ) -> Dict:
    """
    Run the full spatial reasoning pipeline and return a composite score.

    Weights:
      - Stability:    25%   (is CoG within polygon, margin)
      - Mobility:     25%   (torque budget, max incline)
      - Packaging:    20%   (no collisions, wire routing)
      - CoG quality:  15%   (lower height ratio = better)
      - Mass:         15%   (lighter = better, up to a point)
    """
    # Run all analyses
    cog = compute_cog(components, chassis_mass_g, chassis_center)
    stability = compute_stability(cog, contacts)
    torque = compute_torque_budget(cog["total_mass_g"], drivetrain)
    collisions = check_collisions(components)
    wiring = compute_wire_routing(components)

    # ── Sub-scores (0–1) ─────────────────────────────────────
    # Stability: is_stable base + margin bonus
    s_stable = 1.0 if stability["is_stable"] else 0.0
    s_margin = min(stability.get("margin_pct", 0) / 40.0, 1.0)  # 40% margin = perfect
    stability_score = 0.6 * s_stable + 0.4 * s_margin

    # Mobility: max incline mapped to score
    incline = torque["max_incline_deg"]
    mobility_score = min(incline / 20.0, 1.0)  # 20° = perfect

    # Packaging: no collisions + good wiring
    collision_penalty = 1.0 if not collisions["has_collisions"] else 0.0
    packaging_score = 0.6 * collision_penalty + 0.4 * wiring["routing_score"]

    # CoG quality: lower height ratio = more stable
    cog_score = max(0, 1.0 - cog["cog_height_ratio"])

    # Mass score: target 800-1200g total. Penalize heavier.
    mass_g = cog["total_mass_g"]
    if mass_g <= 1000:
        mass_score = 1.0
    elif mass_g <= 1500:
        mass_score = 1.0 - (mass_g - 1000) / 1000
    else:
        mass_score = max(0, 0.5 - (mass_g - 1500) / 2000)

    # ── Composite ─────────────────────────────────────────────
    composite = (
        0.25 * stability_score +
        0.25 * mobility_score +
        0.20 * packaging_score +
        0.15 * cog_score +
        0.15 * mass_score
    )

    return {
        "composite_score": round(composite, 4),
        "sub_scores": {
            "stability": round(stability_score, 3),
            "mobility": round(mobility_score, 3),
            "packaging": round(packaging_score, 3),
            "cog_quality": round(cog_score, 3),
            "mass": round(mass_score, 3),
        },
        "cog": cog,
        "stability": stability,
        "torque": torque,
        "collisions": collisions,
        "wiring": wiring,
    }


# =============================================================================
# GEOMETRY HELPERS
# =============================================================================

def _convex_hull(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Andrew's monotone chain algorithm for 2D convex hull."""
    points = sorted(set(points))
    if len(points) <= 1:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def _point_in_polygon(point: Tuple[float, float],
                      polygon: List[Tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _point_to_segment_dist(p: Tuple[float, float],
                           a: Tuple[float, float],
                           b: Tuple[float, float]) -> float:
    """Distance from point p to line segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.dist(p, a)
    t = max(0, min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / (dx*dx + dy*dy)))
    proj = (a[0] + t*dx, a[1] + t*dy)
    return math.dist(p, proj)


def _directional_margin(cog_xy: Tuple[float, float],
                        polygon: List[Tuple[float, float]],
                        dx: float, dy: float) -> float:
    """Find the distance from CoG to the polygon edge in direction (dx, dy)."""
    # Cast a ray from CoG in the given direction and find intersection
    min_dist = float('inf')
    for i in range(len(polygon)):
        j = (i + 1) % len(polygon)
        dist = _ray_segment_intersect(cog_xy, (dx, dy), polygon[i], polygon[j])
        if dist is not None and dist > 0:
            min_dist = min(min_dist, dist)
    return min_dist if min_dist != float('inf') else 0


def _ray_segment_intersect(origin: Tuple[float, float],
                           direction: Tuple[float, float],
                           a: Tuple[float, float],
                           b: Tuple[float, float]) -> Optional[float]:
    """Intersect a ray (origin + t*direction) with segment a-b. Returns t or None."""
    ox, oy = origin
    dx, dy = direction
    ax, ay = a
    bx, by = b

    denom = dx * (by - ay) - dy * (bx - ax)
    if abs(denom) < 1e-10:
        return None

    t = ((ax - ox) * (by - ay) - (ay - oy) * (bx - ax)) / denom
    u = ((ax - ox) * dy - (ay - oy) * dx) / denom

    if t >= 0 and 0 <= u <= 1:
        return t * math.sqrt(dx*dx + dy*dy)  # Convert parameter to distance
    return None


# =============================================================================
# DEFAULT LAYOUT — v2.0 Physics-Based Component Arrangement
# =============================================================================

def default_v2_layout(ground_clear: float = 15.0,
                      wall: float = 3.0,
                      int_x: float = 95.0,
                      int_y: float = 68.0,
                      gear_ratio: float = 5.0) -> Dict:
    """
    Generate a physically-correct component layout:
      Layer 0 (bottom): Batteries (heaviest, lowest CoG)
      Layer 1 (mid-low): NEMA17 motor (horizontal, drives gear)
      Layer 2 (mid):     SBC + Accelerator
      Layer 3 (top):     Sensor hub + Camera (needs line-of-sight)
    """
    # Z coordinates relative to chassis bottom (z=0 = floor panel top)
    z_base = ground_clear + wall  # Bottom of internal cavity

    # Layer 0: Batteries (184g combined) — LOWEST
    batt_z = z_base + 34   # center of 65mm-tall battery stack

    # Layer 1: Motor (280g) — slightly above batteries
    motor_z = z_base + 65 + 5 + 21   # above batteries + clearance + half motor height

    # Layer 2: SBC + accelerator
    sbc_z = motor_z + 21 + 5 + 9    # above motor + clearance + half SBC height

    # Layer 3: Sensor hub (top)
    sensor_z = sbc_z + 9 + 5 + 4    # above SBC + clearance

    components = [
        # Batteries — bottom (heaviest = lowest CoG)
        Component("18650 ×2", 184, 0, 0, batt_z, 40, 20, 65,
                  connections=["PowerBoost"]),
        Component("PowerBoost", 30, -20, -18, batt_z - 25, 37, 23, 6,
                  connections=["18650 ×2", "Pi 5"]),

        # Motor — mid-low (horizontal orientation)
        Component("NEMA17", 280, 0, 0, motor_z, 42, 42, 42,
                  connections=["Motor Driver"]),

        # Compute — mid
        Component("Pi 5", 43, 0, 0, sbc_z, 85, 58, 17,
                  connections=["Coral", "RP2040", "Camera"]),
        Component("Coral", 25, 0, 24, sbc_z + 13, 65, 30, 8,
                  connections=["Pi 5"]),

        # Sensors — top (line-of-sight)
        Component("RP2040", 8, -8, -15, sensor_z, 33, 18, 8,
                  connections=["Pi 5", "LSM6DSOX", "INA219"]),
        Component("LSM6DSOX", 3, 8, 18, sensor_z, 26, 18, 5,
                  connections=["RP2040"]),
        Component("INA219", 3, -28, 3, sensor_z, 26, 21, 5,
                  connections=["RP2040", "PowerBoost"]),
    ]

    out_x = int_x + 2 * wall
    wheel_offset = out_x / 2 + 15  # wheels outside chassis

    contacts = [
        WheelContact("Wheel R", wheel_offset, 0, 32.5),
        WheelContact("Wheel L", -wheel_offset, 0, 32.5),
        WheelContact("Caster", 0, int_y / 2 - 10, 10),
    ]

    drivetrain = DrivetrainConfig(
        motor_torque_nm=NEMA17_TORQUE_NM,
        motor_rpm=NEMA17_RPM,
        gear_ratio=gear_ratio,
        wheel_radius_mm=32.5,
        num_drive_wheels=2,
    )

    return {
        "components": components,
        "contacts": contacts,
        "drivetrain": drivetrain,
    }


# =============================================================================
# CLI SELF-TEST
# =============================================================================

if __name__ == "__main__":
    import json

    print("\n" + "=" * 60)
    print("  🧠  physics_engine.py — Spatial Reasoning Self-Test")
    print("=" * 60)

    layout = default_v2_layout()
    result = evaluate_design(
        layout["components"],
        layout["contacts"],
        layout["drivetrain"],
        chassis_mass_g=400,
    )

    print(f"\n  Composite Score: {result['composite_score']:.4f}")
    print(f"\n  Sub-scores:")
    for k, v in result["sub_scores"].items():
        bar = "█" * int(v * 20) + "░" * (20 - int(v * 20))
        print(f"    {k:12s}: {v:.3f} |{bar}|")

    cog = result["cog"]
    print(f"\n  Center of Gravity: ({cog['cog_x']:.1f}, {cog['cog_y']:.1f}, {cog['cog_z']:.1f}) mm")
    print(f"  Total Mass:        {cog['total_mass_g']:.0f} g")
    print(f"  CoG Height Ratio:  {cog['cog_height_ratio']:.3f}")

    stab = result["stability"]
    print(f"\n  Stability: {'✅ STABLE' if stab['is_stable'] else '❌ UNSTABLE'}")
    print(f"  Margin:    {stab['margin_mm']:.1f} mm ({stab['margin_pct']:.1f}%)")
    if stab.get("tip_angles"):
        for d, a in stab["tip_angles"].items():
            print(f"    Tip-over {d:10s}: {a:.1f}°")

    torq = result["torque"]
    print(f"\n  Drivetrain: {torq['verdict']}")
    print(f"  Max Incline:     {torq['max_incline_deg']:.1f}°")
    print(f"  Gear Ratio:      {torq['gear_ratio']}:1")
    print(f"  Top Speed:       {torq['top_speed_kmh']:.2f} km/h")
    print(f"  Wheel Torque:    {torq['available_wheel_torque_nm']:.4f} N·m")

    coll = result["collisions"]
    print(f"\n  Collisions: {'❌ ' + str(coll['clearance_violations']) + ' violations' if coll['has_collisions'] else '✅ None'}")
    print(f"  Min clearance:   {coll['min_clearance_mm']:.1f} mm")

    wire = result["wiring"]
    print(f"\n  Wiring Score:    {wire['routing_score']:.3f}")
    print(f"  Total wire:      {wire['total_wire_mm']:.0f} mm")

    print(f"\n{'='*60}")
    print(f"  ✅ Spatial reasoning self-test complete")
    print(f"{'='*60}\n")
