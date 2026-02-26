import os

project_root = "agent_body_lab"
os.makedirs(project_root, exist_ok=True)

# Define file contents from the logic above
files = {
    "handoff.md": """(Paste handoff content here)""",
    "skeleton_v1.scad": """(Paste SCAD content here)""",
    "prusa_bridge.py": """(Paste Bridge content here)""",
    "safety_monitor.py": """(Paste Safety content here)""",
    "reasoning_engine.py": """(Paste Reasoning content here)""",
    "body_workflow.json": '{"nodes": [{"type": "Tripo3D_Gen", "pos": [0,0], "input": "Bio-mechanical shell"}]}',
    "init_workspace.py": """
import subprocess
print("--- Pre-Flight Check ---")
subprocess.run(["prusa-slicer", "--version"])
subprocess.run(["openscad", "--version"])
print("Ready for Autonomous Evolution.")
"""
}

for name, content in files.items():
    with open(os.path.join(project_root, name), "w") as f:
        f.write(content)

print(f"✅ Project 'agent_body_lab' is ready for handoff.")