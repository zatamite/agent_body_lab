# Creative Design Explorer

## Phase 1: Component Database [x]

- [x] Write components_db.json (~40 real parts, 8 categories)
  - SBCs: Pi5, Pi4, Jetson Orin Nano, Rock 5B, Orange Pi 5
  - AI Accelerators: Coral USB, Coral Mini PCIe, Hailo-8, none
  - Cameras: Camera Module 3 Wide, OV9782 global shutter, IMX477 HQ
  - Microphones: I2S MEMS, USB array, analog MEMS
  - Motors: NEMA17 40mm, NEMA17 60mm, NEMA11, servo MG996R
  - Sensor hubs: QWIIC Pro Micro, Teensy 4.0, Arduino Nano
  - Batteries: 2x18650, 4x18650, LiPo 3000mAh, LiPo 5000mAh
  - Power mgmt: PowerBoost 1000C, TP4056+boost, PiJuice

## Phase 2: Creative Evolver Engine [x]

- [x] Write creative_evolver.py
  - Random population of 20 assemblies (1 component per category)
  - Fitness: cost budget check + size compatibility + power budget + physics
  - Sort, take top 3
  - Run 10-iteration hill-climb on geometry for each top-3
  - Output creative_report.json with 3 competing designs
  - Log to evolution_log.json

## Phase 3: Dashboard Integration [x]

- [x] Add POST /api/run-creative endpoint to dashboard_server.py
- [x] Add GET /api/creative-report endpoint
- [x] Add "🎨 Explore Designs" button to sidebar
- [x] Add "Top 3 Designs" comparison panel to dashboard
  - Component grid per design
  - Key metrics side-by-side (cost, mass, AI TOPS, print time, fitness)
- [x] Commit + push

## Phase 4: Verify [x]

- [x] Run creative_evolver.py manually
- [x] Check dashboard shows top-3 panel
