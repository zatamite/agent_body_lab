import bpy
import bmesh
import sys
import math
from mathutils import Vector

# --- Configuration & Component Data ---

# Component layout: name: {pos: (x,y,z), dims: (w,d,h)}
COMPONENTS = {
    "18650_x2":   {"pos": (0.0, 0.0, 50.5), "dims": (40.0, 20.0, 65.0)},
    "PowerBoost": {"pos": (0.0, 0.0, 21.0), "dims": (37.0, 23.0, 6.0)},
    "NEMA17":     {"pos": (0.0, 0.0, 39.0), "dims": (42.0, 42.0, 42.0)},
    "Pi 5":       {"pos": (0.0, 0.0, 26.5), "dims": (85.0, 58.0, 17.0)},
    "Coral":      {"pos": (0.0, 0.0, 22.0), "dims": (65.0, 30.0, 8.0)},
    "RP2040":     {"pos": (0.0, 0.0, 22.0), "dims": (33.0, 18.0, 8.0)},
    "LSM6DSOX":   {"pos": (0.0, 0.0, 20.5), "dims": (26.0, 18.0, 5.0)},
    "INA219":     {"pos": (0.0, 0.0, 20.5), "dims": (26.0, 21.0, 5.0)},
}

# Design Parameters
METABALL_INFLUENCE_FACTOR = 1.3
VOXEL_SIZE = 1.5  # Corresponds to ~0.0015m, good resolution
WALL_THICKNESS = 3.0
BOOLEAN_CLEARANCE = 1.5
GROUND_PLANE_Z = 15.0

# --- Utility Functions ---

def setup_scene():
    """Clears the scene and sets up units for 1 unit = 1 mm."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'NONE'
    # Purge all data
    for collection in bpy.data.collections:
        for obj in collection.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for block in bpy.data.meshes: bpy.data.meshes.remove(block)
    for block in bpy.data.materials: bpy.data.materials.remove(block)
    for block in bpy.data.textures: bpy.data.textures.remove(block)
    for block in bpy.data.images: bpy.data.images.remove(block)
    for block in bpy.data.metaballs: bpy.data.metaballs.remove(block)

def apply_all_modifiers(obj):
    """Applies all modifiers on a given object."""
    ctx = bpy.context.copy()
    ctx['object'] = obj
    for modifier in obj.modifiers:
        try:
            bpy.ops.object.modifier_apply(ctx, modifier=modifier.name)
        except RuntimeError:
            print(f"Warning: Could not apply modifier {modifier.name} to {obj.name}.")
            obj.modifiers.remove(modifier)

def add_boolean_modifier(main_obj, cutter_obj, operation='DIFFERENCE'):
    """Adds a boolean modifier to the main object."""
    bool_mod = main_obj.modifiers.new(name=f"Bool_{cutter_obj.name}", type='BOOLEAN')
    bool_mod.object = cutter_obj
    bool_mod.operation = operation
    bool_mod.solver = 'EXACT'
    return bool_mod

def create_component_cutters(components_data, clearance):
    """Creates cube objects for boolean subtraction based on component dimensions."""
    cutters = []
    for name, data in components_data.items():
        dims = Vector(data["dims"])
        pos = Vector(data["pos"])
        clearance_vec = Vector((clearance * 2, clearance * 2, clearance * 2))
        cutter_dims = dims + clearance_vec
        
        bpy.ops.mesh.primitive_cube_add(location=pos)
        cutter = bpy.context.active_object
        cutter.name = f"Cutter_{name}"
        cutter.dimensions = cutter_dims
        cutters.append(cutter)
    return cutters

def create_standoffs():
    """Generates and returns a single merged mesh for all mounting standoffs."""
    all_standoff_parts = []

    # --- Pi 5 Standoffs (M2.5) ---
    pi_data = COMPONENTS["Pi 5"]
    pi_center = Vector(pi_data["pos"])
    pi_dims = Vector(pi_data["dims"])
    standoff_od = 5.0
    hole_id = 2.7
    standoff_height = pi_dims.z + 2 * WALL_THICKNESS + 20 # Ensure it penetrates
    
    # Relative hole positions from Pi 5 center
    hole_coords = [
        (-39.0, -25.5), ( 19.0, -25.5),
        (-39.0,  23.5), ( 19.0,  23.5)
    ]
    
    for x_rel, y_rel in hole_coords:
        pos = pi_center + Vector((x_rel, y_rel, -pi_dims.z / 2 - standoff_height / 2 + 1.0))
        
        # Outer pillar
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=standoff_od / 2, depth=standoff_height, location=pos)
        pillar = bpy.context.active_object
        
        # Inner hole
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=hole_id / 2, depth=standoff_height + 2, location=pos)
        hole_cutter = bpy.context.active_object
        
        # Subtract hole from pillar
        add_boolean_modifier(pillar, hole_cutter, 'DIFFERENCE')
        apply_all_modifiers(pillar)
        bpy.data.objects.remove(hole_cutter)
        all_standoff_parts.append(pillar)

    # --- NEMA17 Standoffs (M3) ---
    nema_data = COMPONENTS["NEMA17"]
    nema_center = Vector(nema_data["pos"])
    nema_dims = Vector(nema_data["dims"])
    standoff_od = 6.0
    hole_id = 3.2
    standoff_length = nema_dims.y + 2 * WALL_THICKNESS + 20 # Mounts along Y-axis
    
    # 31mm square pattern
    hole_dist = 31.0 / 2
    hole_coords_nema = [
        (-hole_dist, -hole_dist), ( hole_dist, -hole_dist),
        (-hole_dist,  hole_dist), ( hole_dist,  hole_dist)
    ]
    
    for x_rel, z_rel in hole_coords_nema:
        pos = nema_center + Vector((x_rel, -nema_dims.y / 2 - standoff_length / 2 + 1.0, z_rel))
        
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=standoff_od / 2, depth=standoff_length, location=pos)
        pillar = bpy.context.active_object
        pillar.rotation_euler[0] = math.radians(90) # Rotate to face Y-axis
        
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=hole_id / 2, depth=standoff_length + 2, location=pos)
        hole_cutter = bpy.context.active_object
        hole_cutter.rotation_euler[0] = math.radians(90)
        
        add_boolean_modifier(pillar, hole_cutter, 'DIFFERENCE')
        apply_all_modifiers(pillar)
        bpy.data.objects.remove(hole_cutter)
        all_standoff_parts.append(pillar)

    # --- 18650 Battery Cradle ---
    batt_data = COMPONENTS["18650_x2"]
    batt_center = Vector(batt_data["pos"])
    batt_dims = Vector(batt_data["dims"])
    cradle_radius = 12.0
    cradle_height = 20.0
    
    cradle_positions = [
        batt_center + Vector((-batt_dims.x / 4, 0, -batt_dims.z / 2 - cradle_height / 2 + 1.0)),
        batt_center + Vector(( batt_dims.x / 4, 0, -batt_dims.z / 2 - cradle_height / 2 + 1.0))
    ]
    
    for pos in cradle_positions:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=cradle_radius, depth=cradle_height, location=pos)
        cradle = bpy.context.active_object
        all_standoff_parts.append(cradle)

    # Join all parts into one object
    if not all_standoff_parts:
        return None
        
    bpy.ops.object.select_all(action='DESELECT')
    for part in all_standoff_parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = all_standoff_parts[0]
    bpy.ops.object.join()
    
    standoffs_obj = bpy.context.active_object
    standoffs_obj.name = "Standoffs_Combined"
    return standoffs_obj

# --- Main Generation Script ---

def main():
    # 1. Setup
    setup_scene()

    # 2. Organic Growth (Phase A)
    mball_obj = bpy.data.metaballs.new('MetaBall')
    obj = bpy.data.objects.new('MetaBallObject', mball_obj)
    bpy.context.scene.collection.objects.link(obj)
    
    for name, data in COMPONENTS.items():
        dims = Vector(data["dims"])
        pos = Vector(data["pos"])
        diagonal = dims.length
        radius = (diagonal / 2) * METABALL_INFLUENCE_FACTOR
        
        element = mball_obj.elements.new()
        element.co = pos
        element.radius = radius
        element.stiffness = 1.0

    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    proto_body = bpy.context.active_object
    proto_body.name = "Proto_Body"

    # 3. Sculpting & Remeshing (Phase B)
    remesh_mod = proto_body.modifiers.new(name="VoxelRemesh", type='REMESH')
    remesh_mod.mode = 'VOXEL'
    remesh_mod.voxel_size = VOXEL_SIZE
    remesh_mod.use_smooth_shade = True
    apply_all_modifiers(proto_body)

    smooth_mod = proto_body.modifiers.new(name="Smooth", type='SMOOTH')
    smooth_mod.factor = 1.0
    smooth_mod.iterations = 8
    apply_all_modifiers(proto_body)

    # 4. Internal Cavity (Phase C)
    solidify_mod = proto_body.modifiers.new(name="Solidify", type='SOLIDIFY')
    solidify_mod.thickness = WALL_THICKNESS
    solidify_mod.offset = -1.0
    apply_all_modifiers(proto_body)
    
    chassis_body = proto_body
    chassis_body.name = "Hollow_Body"

    # 5. Component Cutouts (Phase D)
    cutters = create_component_cutters(COMPONENTS, BOOLEAN_CLEARANCE)
    for cutter in cutters:
        add_boolean_modifier(chassis_body, cutter, 'DIFFERENCE')
    
    apply_all_modifiers(chassis_body)
    
    # Cleanup cutters
    bpy.ops.object.select_all(action='DESELECT')
    for cutter in cutters:
        cutter.select_set(True)
    bpy.ops.object.delete()

    # 6. Mounting Standoffs (Phase E)
    standoffs_obj = create_standoffs()
    if standoffs_obj:
        add_boolean_modifier(chassis_body, standoffs_obj, 'UNION')
        apply_all_modifiers(chassis_body)
        bpy.data.objects.remove(standoffs_obj)

    # 7. Finalize Geometry & Positioning
    chassis_body.name = "Chassis"
    
    # Ensure manifold geometry by remeshing one last time
    final_remesh = chassis_body.modifiers.new(name="FinalRemesh", type='REMESH')
    final_remesh.mode = 'VOXEL'
    final_remesh.voxel_size = VOXEL_SIZE / 2 # Higher detail for final pass
    apply_all_modifiers(chassis_body)

    # Position above ground plane
    min_z = min(v.co.z for v in chassis_body.data.vertices)
    translation_z = GROUND_PLANE_Z - min_z
    chassis_body.location.z += translation_z
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    # 8. Export
    bpy.ops.object.select_all(action='DESELECT')
    chassis_body.select_set(True)
    bpy.context.view_layer.objects.active = chassis_body
    
    output_path = sys.argv[-1]
    if not output_path.lower().endswith('.stl'):
        output_path += ".stl"

    bpy.ops.wm.stl_export(
        filepath=output_path,
        export_selected_objects=True,
        global_scale=1.0
    )

if __name__ == "__main__":
    main()