
import subprocess
print("--- Pre-Flight Check ---")
subprocess.run(["prusa-slicer", "--version"])
subprocess.run(["openscad", "--version"])
print("Ready for Autonomous Evolution.")
