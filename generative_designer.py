"""
generative_designer.py — AI-driven CAD generator.
Prompts the LLM with the current component layout and asks it to write
a Blender Python script that generates an organic chassis.
"""
import sys
from pathlib import Path

import json
import llm_client
from physics_engine import generate_dynamic_layout

ROOT = Path(__file__).parent

# The prompt template we send to the LLM
PROMPT_TEMPLATE = """
You are an elite mechanical engineer, industrial designer, and a master of the Blender Python API (bpy).
I need you to write a complete Python script that will be executed in headless Blender (v4.5).
Your objective is to generate a functional, highly-optimized, 3D printable robot chassis that "grows" 
organically around the provided component layout.

Here are the components that must fit inside, with their XYZ centers and bounding box dimensions (W,D,H) in mm:
{components_json}

The chassis must rest entirely above the ground plane at Z = {ground_clearance}mm.

CRITICAL MECHANICAL REQUIREMENTS & WORKFLOW:
1. Setup: 
   - Start with `bpy.ops.wm.read_factory_settings(use_empty=True)`.
   - SET UNITS TO NONE: `bpy.context.scene.unit_settings.system = 'NONE'`.
   - USE RAW NUMBERS: Use the raw mm values from the layout directly as Blender units (e.g., 20mm -> 20.0 units). 
   - This ensures that 1.0 Blender Unit = 1.0 Millimeter in the exported STL.
2. Organic Growth (Phase A):
   - For every component, create a 'Metaball' at its center. 
   - Set the metaball 'influence' radius slightly larger than the component's diagonal.
   - The result should be a single, blobby "Proto-Body" that encapsulates all internal organs.
   - Convert Metaball to Mesh.
3. Sculpting & Remeshing (Phase B):
   - Add a 'Voxel Remesh' modifier (voxel size ~0.003m) to the mesh to unify the blobs into a smooth, manifold surface.
   - Add a 'Smooth' modifier to refine the flow.
4. Internal Cavity (Phase C):
   - Hollow the body by creating a 'Solidify' modifier (offset -1.0, thickness 0.003m for 3mm walls).
   - Apply the modifier.
5. Component Cutouts (Phase D):
   - Create boolean 'Difference' objects for every component + 1.5mm clearance. 
   - Subtract these from the body to ensure they fit inside.
6. Mounting Standoffs (Phase E):
   - For components 'Pi 5', 'Motor', and 'Battery', generate internal cylindrical pillars that connect the body's inner wall to the component's mounting holes (or base).
   - These pillars MUST be joined ('Union') with the main body.
7. Merge & Export:
   - Ensure the final object is one manifold mesh named "Chassis".
   - Export syntax: `bpy.ops.wm.stl_export(filepath=sys.argv[-1], export_selected_objects=True, global_scale=1.0)`
   - NO markdown, NO explanations, ONLY Python code.
"""

def design_organic_chassis(output_stl: str = str(ROOT / "ai_chassis.stl")):
    # 1. Load evolved parameters if they exist
    report_path = ROOT / "evolution_report.json"
    params = {}
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text())
            if "winner" in report:
                params = report["winner"]
                print("🧬 Loading evolved design parameters from evolution_report.json...")
        except Exception:
            pass
            
    # 2. Generate the layout from these parameters
    layout = generate_dynamic_layout(params)
    comps = layout["components"]
    
    # Format components for the prompt
    c_list = []
    for c in comps:
        c_list.append(f"- {c.label}: pos=({c.x:.1f}, {c.y:.1f}, {c.z:.1f}), dims=({c.w:.1f}, {c.d:.1f}, {c.h:.1f})")
        
    c_text = "\n".join(c_list)
    prompt = PROMPT_TEMPLATE.format(
        components_json=c_text,
        ground_clearance=params.get("ground_clear", 15.0)
    )
    
    print("🤖 Requesting generative CAD script from LLM...")
    try:
        script_code = llm_client.generate_blender_script(prompt)
    except Exception as e:
        print(f"❌ LLM error: {e}")
        return False
        
    # Clean up markdown if LLM disobeyed
    if script_code.startswith("```"):
        lines = script_code.split("\n")
        if lines[0].startswith("```"): lines = lines[1:]
        if lines[-1].startswith("```"): lines = lines[:-1]
        script_code = "\n".join(lines).strip()
        
    script_path = ROOT / "blender_scripts" / "ai_generated_chassis.py"
    script_path.parent.mkdir(exist_ok=True)
    script_path.write_text(script_code)
    
    print(f"✅ LLM generated script saved to: {script_path.relative_to(ROOT)}")
    print(f"🔨 Running Blender to compile STL to {output_stl}...")
    
    import subprocess
    cmd = [
        "/Applications/Blender.app/Contents/MacOS/Blender",
        "--background",
        "--python", str(script_path),
        "--", output_stl
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and Path(output_stl).exists():
        print(f"✨ Success! Organically generated chassis saved to {output_stl}")
        return True
    else:
        print("❌ Blender script execution failed.")
        print("Blender Output:")
        print(result.stdout)
        print(result.stderr)
        return False

if __name__ == "__main__":
    design_organic_chassis()
