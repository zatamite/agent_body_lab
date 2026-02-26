
"""Blender parametric chassis generator — runs headless inside Blender."""
import bpy
import bmesh
import json
import sys
import math

# Read parameters from stdin/argv
params_file = sys.argv[sys.argv.index("--") + 1]
with open(params_file) as f:
    P = json.load(f)

# Clear default scene
bpy.ops.wm.read_factory_settings(use_empty=True)

# ── Materials ─────────────────────────────────────────────────────────────
def make_material(name, color, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1:
        mat.blend_method = 'BLEND'
    return mat

mat_chassis = make_material("PETG", (0.12, 0.25, 0.4), 0.7)
mat_motor   = make_material("Motor", (1.0, 0.55, 0.0))
mat_pcb     = make_material("PCB", (0.0, 0.78, 1.0))
mat_battery = make_material("Battery", (1.0, 0.8, 0.0))
mat_wheel   = make_material("Wheel", (0.15, 0.15, 0.15))
mat_sensor  = make_material("Sensor", (0.0, 0.9, 0.46))

MATERIAL_MAP = {
    "NEMA17": mat_motor, "Pi 5": mat_pcb, "Coral": mat_pcb,
    "18650": mat_battery, "PowerBoost": mat_battery,
    "RP2040": mat_sensor, "LSM6DSOX": mat_sensor, "INA219": mat_sensor,
    "Wheel": mat_wheel, "Caster": mat_wheel,
}

def get_material(label):
    for key, mat in MATERIAL_MAP.items():
        if key in label:
            return mat
    return mat_pcb

# ── Chassis Shell ─────────────────────────────────────────────────────────
def make_chassis(out_x, out_y, out_z, wall, ground_clear):
    """Create a hollow chassis box with beveled edges."""
    # Outer shell
    bpy.ops.mesh.primitive_cube_add(size=1,
        location=(0, 0, ground_clear + out_z/2))
    outer = bpy.context.active_object
    outer.name = "Chassis"
    outer.scale = (out_x/1000, out_y/1000, out_z/1000)
    bpy.ops.object.transform_apply(scale=True)

    # Bevel modifier for rounded edges
    bevel = outer.modifiers.new("Bevel", 'BEVEL')
    bevel.width = 0.004  # 4mm radius
    bevel.segments = 4
    bevel.limit_method = 'ANGLE'

    # Solidify to create hollow shell
    solidify = outer.modifiers.new("Solidify", 'SOLIDIFY')
    solidify.thickness = -wall / 1000.0
    solidify.use_even_offset = True

    outer.data.materials.append(mat_chassis)
    return outer

# ── Components ────────────────────────────────────────────────────────────
def make_component(label, x, y, z, w, d, h, comp_type="box"):
    """Create a component representation."""
    # Convert mm to meters (Blender default unit)
    loc = (x/1000, y/1000, z/1000)

    if comp_type == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(
            radius=d/2000, depth=w/1000, location=loc)
        obj = bpy.context.active_object
        obj.rotation_euler = (0, math.pi/2, 0)  # Horizontal
    elif comp_type == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=w/2000, location=loc)
        obj = bpy.context.active_object
    else:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
        obj = bpy.context.active_object
        obj.scale = (w/1000, d/1000, h/1000)
        bpy.ops.object.transform_apply(scale=True)

        # Subtle bevel on component boxes
        bevel = obj.modifiers.new("Bevel", 'BEVEL')
        bevel.width = 0.001
        bevel.segments = 2

    obj.name = label
    mat = get_material(label)
    obj.data.materials.append(mat)
    return obj

# ── Ground Plane ──────────────────────────────────────────────────────────
def make_ground():
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "Ground"
    ground.scale = (0.5, 0.5, 1)
    mat = make_material("Ground", (0.03, 0.05, 0.08))
    ground.data.materials.append(mat)

# ── Camera & Lighting ─────────────────────────────────────────────────────
def setup_scene():
    # Camera
    bpy.ops.object.camera_add(location=(0.35, -0.35, 0.25))
    cam = bpy.context.active_object
    cam.rotation_euler = (math.radians(65), 0, math.radians(45))
    bpy.context.scene.camera = cam

    # Key light
    bpy.ops.object.light_add(type='SUN', location=(0.2, -0.1, 0.5))
    sun = bpy.context.active_object
    sun.data.energy = 3.0

    # Fill light
    bpy.ops.object.light_add(type='AREA', location=(-0.2, 0.3, 0.3))
    fill = bpy.context.active_object
    fill.data.energy = 50
    fill.data.size = 0.3

    # Environment
    bpy.context.scene.world = bpy.data.worlds.new("World")
    bpy.context.scene.world.use_nodes = True
    bg = bpy.context.scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.02, 0.03, 0.05, 1)

# ── Build Assembly ────────────────────────────────────────────────────────
out_x = P["chassis"]["out_x"]
out_y = P["chassis"]["out_y"]
out_z = P["chassis"]["out_z"]
wall  = P["chassis"]["wall"]
gc    = P.get("ground_clear", 15)

make_ground()
make_chassis(out_x, out_y, out_z, wall, gc/1000.0)

for c in P.get("components", []):
    z_offset = gc / 1000.0
    make_component(
        c["label"],
        c["x"], c["y"], c["z"] + gc,
        c.get("w", 10), c.get("d", 10), c.get("h", 10),
        c.get("type", "box")
    )

setup_scene()

# ── Export ────────────────────────────────────────────────────────────────
output_path = P.get("output_stl", "/tmp/body_v2.stl")
render_path = P.get("output_render", "/tmp/body_v2_preview.png")

# STL export (chassis only for printing)
bpy.ops.object.select_all(action='DESELECT')
chassis = bpy.data.objects.get("Chassis")
if chassis:
    # Apply modifiers before export
    bpy.context.view_layer.objects.active = chassis
    chassis.select_set(True)
    for mod in chassis.modifiers:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.wm.stl_export(filepath=output_path, export_selected_objects=True)
    print(f"STL exported: {output_path}")

# Render preview
bpy.context.scene.render.resolution_x = 1280
bpy.context.scene.render.resolution_y = 720
bpy.context.scene.render.engine = 'BLENDER_EEVEE_NEXT'
bpy.context.scene.render.filepath = render_path
bpy.ops.render.render(write_still=True)
print(f"Render saved: {render_path}")

print("\n✅ Blender chassis generation complete")
