// =============================================================================
// skeleton_v1.scad — Body v1.0 Chassis
// Agent: Antigravity | Date: 2026-02-26
//
// AGENTIC PARAMETERS: Modify these to evolve the body.
// All mounting patterns are derived from real component datasheets.
//
// Outer envelope: 102mm × 75mm × 137mm
// Fits within Prusa XL 360×360×360mm build volume.
//
// Toolhead assignment:
//   T0 = PETG (rigid chassis walls, bosses, mounts)
//   T1 = TPU  (skin, snap-clip pockets for Coral, cable grommets)
//   T2 = Conductive (sensory patch traces on outer skin)
//   T3 = Support material (internal overhangs)
//   T4 = Accent pigment (vent/vein aesthetic traces)
// =============================================================================

// ── Agentic Parameters ────────────────────────────────────────────────────────
wall           = 5.50;   // mm — PETG wall thickness (≥3 perimeters at 0.4mm nozzle)
bolt_dia       = 3.4;   // mm — M3 clearance (3.4mm)
m25_dia        = 2.7;   // mm — M2.5 clearance
m2_dia         = 2.2;   // mm — M2 clearance
boss_od        = 7.0;   // mm — outer diameter of all standoff bosses
boss_h_m25     = 5.0;   // mm — boss raise height for M2.5 standoffs
boss_h_m2      = 4.0;   // mm — boss height for M2 standoffs
tpu_wall           = 5.50;   // mm — TPU skin thickness

// ── Mobility Parameters ─────────────────────────────────────────────────────
has_wheels     = 1;      // Boolean: 1 = rolling, 0 = stationary
wheel_dia      = 65.0;   // mm
wheel_width    = 26.0;   // mm
ground_clear   = 15.0;   // mm — distance from bottom of chassis to floor

// ── Layer Stack Heights (Z-offsets from bottom wall) ────────────────────────
Z_HUB     = wall + 0;        // Sensor hub layer
Z_PI      = Z_HUB + 40;     // Pi 5 layer
Z_BATT    = Z_PI + 30;      // Battery layer

// Derived dims
out_x     = int_x + wall * 2;
out_y     = int_y + wall * 2;
out_z     = int_z + wall;

// ── Rendering logic ──────────────────────────────────────────────────────────
$fn = 32;

module wheel(side="left") {
    color("black")
    rotate([0, 90, 0])
    cylinder(d=wheel_dia, h=wheel_width, center=true);
}

module caster() {
    color("silver")
    sphere(d=ground_clear + 5);
}

module rounded_box_2d(w, d, r) {
    offset(r=r) square([w-2*r, d-2*r], center=true);
}

module chassis_shell() {
    difference() {
        // Main extruded shell with filleted corners
        linear_extrude(height=out_z)
            rounded_box_2d(out_x, out_y, 4);
        
        // Inner cavity (hollowed out)
        translate([0, 0, wall])
            linear_extrude(height=int_z + 1)
                rounded_box_2d(int_x, int_y, 2);
        
        // Cable management channels (rear corners)
        for (x=[-1, 1], y=[-1, 1]) {
            translate([x * (int_x/2 - 5), y * (int_y/2 - 5), wall])
                cylinder(d=8, h=int_z, $fn=16);
        }
    }
}

module boss_pattern_pi5() {
    for (x = [0, 58], y = [0, 49]) {
        translate([x, y, 0])
        difference() {
            cylinder(d=boss_od, h=boss_h_m25);
            translate([0, 0, -1])
            cylinder(d=m25_dia, h=boss_h_m25 + 2);
        }
    }
}

// Final Assembly
translate([0, 0, ground_clear + (out_z/2)]) {
    chassis_base();
    
    if (has_wheels) {
        // Drive wheels
        translate([out_x/2 + wheel_width/2 + 2, 0, -out_z/2 + 10])
        wheel("right");
        translate([-out_x/2 - wheel_width/2 - 2, 0, -out_z/2 + 10])
        wheel("left");
        
        // Caster support
        translate([0, out_y/2 - 15, -out_z/2 - ground_clear/2])
        caster();
    }
}

// =============================================================================
// MODULE: Boss — a standoff mounting post with through-hole
// =============================================================================
module boss(dia, height, hole_dia) {
    difference() {
        cylinder(d=dia, h=height, $fn=24);
        cylinder(d=hole_dia, h=height + 1, $fn=16);
    }
}

// =============================================================================
// MODULE: NEMA17 mount — bottom face plate with 4× M3 holes + shaft clearance
// =============================================================================
module nema17_mount() {
    // NEMA17: 42×42mm face, M3 holes at ±15.5mm from centre, shaft Ø5mm
    half = 15.5;  // half bolt-circle radius (31mm / 2)
    
    difference() {
        // Base plate
        translate([-out_x/2, -out_y/2, 0])
            cube([out_x, out_y, wall]);
        
        // 4× M3 bolt holes
        for(x=[-half, half]) for(y=[-half, half])
            translate([x, y, -0.5]) cylinder(d=bolt_dia, h=wall+1, $fn=16);
        
        // Shaft clearance hole (Ø12mm for NEMA17 pilot boss)
        translate([0, 0, -0.5]) cylinder(d=12, h=wall+1, $fn=24);
    }
}

// =============================================================================
// MODULE: Raspberry Pi 5 mounts — 4× M2.5 bosses in 58×49mm pattern
// Pi origin: bottom-left corner of PCB centred in XY
// =============================================================================
module pi5_mounts(z_base) {
    // RPi 5 mounting holes: offsets from PCB centre
    // Pattern: 58mm wide × 49mm tall, holes inset 3.5mm from edges
    holes = [
        [-25, -21.5],   // Bottom-left
        [ 25, -21.5],   // Bottom-right
        [-25,  21.5],   // Top-left
        [ 25,  21.5]    // Top-right
    ];
    translate([0, 0, z_base])
        for(pos = holes)
            translate([pos[0], pos[1], 0])
                boss(boss_od, boss_h_m25, m25_dia);
}

// =============================================================================
// MODULE: Camera Module 3 mount — 2× M2 bosses, 21×12.5mm spacing
// Positioned at front-centre of chassis, mid-height (Z_PI layer)
// =============================================================================
module camera_mount(z_base) {
    // Camera centred on front wall at mid-layer
    // 2 holes: ±10.5mm in X, ±6.25mm in Y
    holes = [
        [-10.5,  0],
        [ 10.5,  0]
    ];
    translate([0, out_y/2 - wall - 2, z_base + 25])
        for(pos = holes)
            translate([pos[0], 0, 0])
                rotate([90, 0, 0])  // bosses face forward (Y direction)
                    boss(6.0, boss_h_m2 + wall, m2_dia);
}

// =============================================================================
// MODULE: Sensor bay mounts — RP2040 + QWIIC boards at Z_HUB layer
// Board mount uses 2× M2 holes per board, stacked in Y axis
// =============================================================================
module sensor_bay_mounts(z_base) {
    translate([0, 0, z_base]) {
        // RP2040 Pro Micro (33×18mm) — centre-left
        for(pos = [[-8, 0], [8, 0]])
            translate([pos[0], -15, 0])
                boss(6.0, boss_h_m2, m2_dia);
        
        // LSM6DSOX IMU (25.6×17.8mm) — right side
        for(pos = [[-6, 0], [6, 0]])
            translate([pos[0], 18, 0])
                boss(6.0, boss_h_m2, m2_dia);
        
        // INA219 Power Monitor (25.6×20.4mm) — left side
        for(pos = [[-6, 0], [6, 0]])
            translate([pos[0] - 28, 3, 0])
                boss(6.0, boss_h_m2, m2_dia);
    }
}

// =============================================================================
// MODULE: Battery tray — 2× 18650 cells side-by-side
// Cell Ø18.6mm × 65.1mm long, oriented along Z axis
// =============================================================================
module battery_tray(z_base) {
    // Two cells side by side, centred in chassis
    cell_r  = 9.5;    // radius + clearance
    spacing = 21;     // centre-to-centre

    translate([0, 0, z_base]) {
        difference() {
            // Outer tray body
            cube([spacing + cell_r*3, cell_r*2 + 4, 68], center=true);
            // Cell bore left
            translate([-spacing/2, 0, 0]) cylinder(r=cell_r, h=70, center=true, $fn=32);
            // Cell bore right
            translate([ spacing/2, 0, 0]) cylinder(r=cell_r, h=70, center=true, $fn=32);
        }
    }
}

// =============================================================================
// MODULE: Cooling vents — 4× radial on each long face
// Inherited from v1.0, now scaled for new chassis size
// =============================================================================
module cooling_vents() {
    vent_w = 20;
    vent_h = 55;
    vent_d  = wall + 2;
    y_pos   = out_y / 2;
    
    // Front + back vents
    for(side = [-1, 1]) {
        // 3 vents across width
        for(i = [-1, 0, 1]) {
            translate([i * 28, side * (y_pos - wall/2), int_z/2])
                cube([vent_w, vent_d, vent_h], center=true);
        }
    }
    // Side vents
    x_pos = out_x / 2;
    for(side = [-1, 1]) {
        for(i = [-1, 0, 1]) {
            translate([side * (x_pos - wall/2), i * 20, int_z/2])
                cube([vent_d, vent_w, vent_h], center=true);
        }
    }
}

// =============================================================================
// MODULE: Camera aperture — rectangular hole in front wall
// =============================================================================
module camera_aperture() {
    // 26mm × 26mm window centred at camera mount Z position
    translate([0, out_y/2 - wall/2, Z_PI + 25])
        cube([26, wall + 2, 26], center=true);
}

// =============================================================================
// MAIN ASSEMBLY
// =============================================================================
module mechanical_core() {
    difference() {
        chassis_shell();
        
        // ── Cooling vents (using dynamic loop) ──────────────────────────
        cooling_vents();
        
        // ── Camera aperture ──────────────────────────────────────────
        camera_aperture();

        // ── Axle holes ───────────────────────────────────────────────
        if (has_wheels) {
            translate([0, 0, 10])
            rotate([0, 90, 0])
            cylinder(d=8, h=out_x + 10, center=true);
        }
    }
    
    // ── NEMA17 bottom mount plate ─────────────────
    nema17_mount();
    
    // ── Components Stacks ──────────────────────────────────────────
    pi5_mounts(Z_PI);
    camera_mount(Z_PI);
    sensor_bay_mounts(Z_HUB);
    
    translate([0, 0, Z_BATT + 34])
        battery_tray(0);
}

// ── Render ────────────────────────────────────────────────────────────────────
mechanical_core();

// ── Debug: show component outlines (comment out for final export) ─────────────
// %translate([0, 0, Z_PI + wall + boss_h_m25])  // Pi 5 outline
//     color("green", 0.3) cube([85, 58, 2], center=true);
// %translate([0, -10, Z_HUB + wall + boss_h_m2]) // RP2040 outline
//     color("blue", 0.3) cube([33, 18, 2], center=true);