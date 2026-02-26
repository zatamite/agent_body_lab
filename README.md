# agent_body_lab 🦾

Autonomous fabrication loop for an AI agent's physical body.
Designed for the **Prusa XL** (5-toolhead) via the Prusa Connect API.

---

## How It Works

```
Design Rationale (Agent)
        │
        ▼
 approval_gate.py  ◄── human_approval must be True
        │
        ▼
  pipeline.py
  ├── [1] Approval gate check
  ├── [2] OpenSCAD → STL export (skeleton_v1.scad)
  ├── [3] PrusaSlicer → .bgcode slice
  ├── [4] Prusa Connect API upload + print start
  └── [5] safety_monitor.py (daemon thread)
              ├── State: ERROR/ATTENTION → E-Stop
              └── Temp: nozzle > 305°C  → E-Stop
```

**Nothing prints without explicit human approval.** The approval gate reads `evolution_log.json` and blocks dispatch if the latest entry has `human_approval: false`.

---

## Toolhead Map (Prusa XL)

| Toolhead | Material | Role |
|---|---|---|
| T0 | PETG / PLA | Skeleton — rigid chassis |
| T1 | TPU | Skin — flexible outer layer |
| T2 | Silicone / Conductive | Sensory patches, vent seals |
| T3 | Support material | Internal overhangs |
| T4 | Pigment filament | Aesthetic accent layer |

---

## Setup

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/agent_body_lab.git
cd agent_body_lab

# 2. Install Python dependencies
pip3 install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env — add your Prusa Connect API key and printer ID

# 4. Test the full pipeline safely (no hardware required)
bash run_dry.sh
```

---

## The Design Loop

### 1. Log a new design rationale

```python
import reasoning_engine

reasoning_engine.log_evolution("v1.0", {
    "intent": "Minimum viable agentic body — NEMA17 chassis, PETG skeleton, TPU skin.",
    "mechanical_integrity": "3.5mm PETG walls, M3 clearance, 4-vent radial cooling.",
    "multimodal_utility":   "Houses audio, vision, and touch sensors.",
    "material_philosophy":  "T0=PETG, T1=TPU, T2=Conductive, T3=Support, T4=Aesthetic.",
    "aesthetic_intent":     "Vent geometry extruded to skin surface — function is the face.",
})
```

### 2. Review & approve

```bash
# Check gate status
python3 approval_gate.py

# Approve the latest entry
python3 -c "import reasoning_engine; reasoning_engine.approve_latest()"
```

### 3. Run the pipeline

```bash
# Dry run (safe, no hardware)
bash run_dry.sh

# Live run (requires .env credentials + connected printer)
python3 pipeline.py
```

---

## File Map

```
agent_body_lab/
├── skeleton_v1.scad       Parametric CAD skeleton (OpenSCAD)
├── pipeline.py            Main orchestrator — runs the full 5-step loop
├── approval_gate.py       Hard gate — blocks dispatch without human approval
├── reasoning_engine.py    Logs design rationale; provides approve_latest()
├── prusa_bridge.py        Prusa Connect API client (upload, status, e-stop)
├── safety_monitor.py      Hardware watchdog (runs as daemon thread)
├── secrets.py             Credential loader from .env
├── run_dry.sh             Safe dry-run launcher
├── .env.example           Credential template (commit this)
├── .env                   Real credentials (gitignored — never commit)
├── requirements.txt       Python dependencies
└── evolution_log.json     JSONL design history (gitignored)
```

---

## Safety

- **Approval gate:** `human_approval` must be `True` in `evolution_log.json` before any G-code is dispatched.
- **Thermal runaway:** E-stop triggered automatically if nozzle temp exceeds 305°C.
- **State anomaly:** E-stop on `ERROR` or `ATTENTION` printer state.
- **Dry run mode:** `DRY_RUN=true` simulates the entire loop without touching hardware.

---

## Iteration

When physical feedback arrives (e.g., "joint too loose"), increment the version:

```python
reasoning_engine.log_evolution("v1.1", {
    "intent": "Tightened NEMA17 bolt clearance from 3.4mm to 3.2mm based on physical test.",
    ...
})
# → approve → pipeline.py
```

All versions are preserved in `evolution_log.json`.
