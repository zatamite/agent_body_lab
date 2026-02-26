# Parts DOM — Body v1.0

## Agent: Antigravity | Updated: 2026-02-26 | Status: DRAFT — Awaiting Human Approval

> **Design principle:** Every component is screw-mounted with known hole patterns, no soldering required for interconnects. All sensor comms use QWIIC (JST SH 1mm 4-pin). Power uses JST PH 2mm. Data backbone is USB 3.0 hub.

---

## System Architecture Map

```
┌─────────────────────────────────────────────────────┐
│                  BODY v1.0 CORE                     │
│                                                     │
│  ┌──────────────┐    PCIe/USB    ┌───────────────┐  │
│  │ Raspberry    │◄──────────────►│ Coral USB     │  │
│  │ Pi 5 (8GB)   │                │ Accelerator   │  │
│  │   BRAIN      │                │   CORTEX      │  │
│  └──────┬───────┘                └───────────────┘  │
│         │ USB 3.0 Hub                               │
│    ┌────┴─────┬────────────┬──────────────┐         │
│    ▼          ▼            ▼              ▼         │
│  Camera    Microphone   QWIIC Bus      NEMA17       │
│  Module 3  (USB)        Controller    Stepper       │
│  VISION    HEARING      (RP2040)      MOTION        │
│                              │                      │
│                    ┌─────────┼──────────┐           │
│                    ▼         ▼          ▼           │
│                  IMU      Power      Env            │
│                  BALANCE  MONITOR    SENSOR         │
└─────────────────────────────────────────────────────┘
```

---

## 🧠 BRAIN — Main Compute

### 01 · Raspberry Pi 5 (8GB)

| Field | Value |
|---|---|
| **Organ role** | Primary CPU / brain |
| **Manufacturer** | Raspberry Pi Ltd |
| **SKU** | SC1112 |
| **Buy** | pishop.us ~$80 |
| **Dimensions** | 85mm × 58mm × 17mm (with heatsink: +10mm) |
| **Mounting** | 4× M2.5 holes; pattern 58mm × 49mm from corner |
| **Hole diameter** | Ø2.7mm (M2.5 clearance) |
| **Power** | 5V @ 5A via USB-C PD (27W min) |
| **Key interfaces** | 2× USB 3.0, 2× USB 2.0, GPIO 40-pin, 2× CSI, PCIe 2.0, GbE |
| **Standoffs** | 4× M2.5 × 10mm brass standoff + M2.5 screws |

> **Fit note:** Pi 5 is the largest component — dictates minimum chassis internal width of **90mm**.

---

## 🧬 CORTEX — AI Inference

### 02 · Google Coral USB Accelerator

| Field | Value |
|---|---|
| **Organ role** | On-device ML inference (4 TOPS Edge TPU) |
| **Manufacturer** | Google / Coral |
| **SKU** | G950-06809-01 |
| **Buy** | Mouser ~$60 |
| **Dimensions** | 65mm × 30mm × 8mm |
| **Mounting** | No holes — TPU snap-clip pocket (printed T1) |
| **Power** | 5V via USB 3.0 (≤2.5W peak) |
| **Interface** | USB 3.0 Type-A → Pi USB port |

---

## 👁 VISION — Sensing

### 03 · Raspberry Pi Camera Module 3 Wide

| Field | Value |
|---|---|
| **Organ role** | Primary vision, 12MP Sony IMX708, 102° FOV |
| **SKU** | SC0874 |
| **Buy** | thepihut.com ~$35 |
| **Dimensions** | 25mm × 24mm × 11.5mm |
| **Mounting** | 2× M2 holes; 21mm × 12.5mm spacing |
| **Interface** | 15-pin FPC ribbon → Pi CSI-2 |
| **Standoffs** | 2× M2 × 6mm |

### 04 · Adafruit I2S MEMS Microphone (SPH0645)

| Field | Value |
|---|---|
| **Organ role** | Audio/voice sensing |
| **SKU** | ADA3421 |
| **Buy** | adafruit.com ~$7 |
| **Dimensions** | 19mm × 12mm × 3mm |
| **Mounting** | 2× M2.5 holes |
| **Interface** | I2S (3 GPIO lines to RP2040) |

---

## ⚡ MOTION — Actuation

### 05 · NEMA17 Stepper Motor (17HS4401)

| Field | Value |
|---|---|
| **Organ role** | Primary actuator / pan-tilt pivot |
| **SKU** | 17HS4401 |
| **Buy** | Amazon ~$12 |
| **Dimensions** | 42mm × 42mm × 40mm body |
| **Mounting** | 4× M3 holes; 31mm × 31mm bolt circle |
| **Power** | 12V / 1.7A per phase |
| **Driver** | TMC2209 (#06) |

### 06 · BigTreeTech TMC2209 Stepper Driver

| Field | Value |
|---|---|
| **Organ role** | Quiet stepper control via UART |
| **SKU** | TMC2209 v1.3 |
| **Buy** | Amazon ~$8 |
| **Dimensions** | 20mm × 15mm |
| **Mounting** | Pololu-footprint socket (press-fit, no solder) |
| **Interface** | UART to RP2040 + STEP/DIR GPIO |
| **Motor conn** | 4-pin JST PH 2mm |

---

## 🌐 NERVOUS SYSTEM — Sensor Bus Controller

### 07 · SparkFun QWIIC Pro Micro (RP2040)

| Field | Value |
|---|---|
| **Organ role** | Sensor hub + stepper controller + serial bridge |
| **SKU** | DEV-18288 |
| **Buy** | sparkfun.com ~$12 |
| **Dimensions** | 33mm × 18mm |
| **Mounting** | 2× M2 edge holes |
| **Interface** | USB-C → Pi (serial), QWIIC I2C bus out, GPIO |
| **Firmware** | MicroPython, owns full QWIIC sensor chain |

---

## 🔬 SENSORS — QWIIC Chain (all JST SH 1mm, daisy-chain)

### 08 · Adafruit LSM6DSOX IMU (6DoF)

| Field | Value |
|---|---|
| **Organ role** | Proprioception — accel + gyro |
| **SKU** | ADA4438 · adafruit.com ~$12 |
| **Dimensions** | 25.6mm × 17.8mm × 4.6mm |
| **Mounting** | 2× M2.5 holes |
| **I2C address** | 0x6A / 0x6B |

### 09 · Adafruit BME688 Environmental Sensor

| Field | Value |
|---|---|
| **Organ role** | Temp, humidity, pressure, VOC/air quality |
| **SKU** | ADA5046 · adafruit.com ~$20 |
| **Dimensions** | 23mm × 17.8mm × 3.6mm |
| **Mounting** | 2× M2.5 holes |
| **I2C address** | 0x76 / 0x77 |

### 10 · Adafruit INA219 Power Monitor

| Field | Value |
|---|---|
| **Organ role** | Battery telemetry (V, I, W) |
| **SKU** | ADA904 · adafruit.com ~$10 |
| **Dimensions** | 25.6mm × 20.4mm × 4.7mm |
| **Mounting** | 2× M2.5 holes |
| **I2C address** | 0x40 |

---

## 🔋 POWER — Energy Core

### 11 · Adafruit PowerBoost 1000C

| Field | Value |
|---|---|
| **Organ role** | LiPo charger + 5V boost regulator |
| **SKU** | ADA2465 · adafruit.com ~$20 |
| **Dimensions** | 36.5mm × 23mm × 6mm |
| **Mounting** | 2× M2.5 holes (30mm spacing) |
| **Output** | 5V @ 1A from LiPo |
| **Battery** | JST PH 2mm 2-pin |

### 12 · 18650 LiPo Cells (2× Panasonic NCR18650B)

| Field | Value |
|---|---|
| **Organ role** | Energy store |
| **Spec** | 3.7V, 3400mAh each |
| **Dimensions** | Ø18.6mm × 65.1mm per cell |
| **Mounting** | PETG printed tray with spring contacts |
| **Total** | ~25Wh runtime |

### 13 · LM2596 Buck Converter (12V NEMA17 rail)

| Field | Value |
|---|---|
| **Organ role** | Stepper motor 12V power rail |
| **Buy** | Amazon ~$8 |
| **Dimensions** | 43mm × 21mm × 14mm |
| **Mounting** | 2× M3 holes (37mm spacing) |
| **Output** | 12V @ 2A |

---

## 📐 Chassis Fit Analysis

> ⚠️ The v1.0 SCAD cavity (45×45×65mm) is too small for a Pi 5 (85×58mm).
> **Chassis redesigned — see updated `skeleton_v1.scad`.**

### Revised Internal Cavity

| Axis | Required | Designed |
|---|---|---|
| Width X | 90mm (Pi) | **95mm** |
| Depth Y | 62mm (Pi) | **68mm** |
| Height Z | 120mm (stacked) | **130mm** |
| Wall | 3.5mm | **3.5mm** |
| **Outer XY** | — | **102mm × 75mm** |
| **Outer Z** | — | **137mm** |

✅ Max outer envelope **102×75×137mm** — fits Prusa XL 360×360×360mm build volume.

### Layer Stack (bottom → top)

```
Z+130 ┌──────────────────────────┐ T4 aesthetic skin
Z+110 ├──────────────────────────┤ Battery tray + PowerBoost
Z+080 ├──────────────────────────┤ Raspberry Pi 5 + Coral
Z+040 ├──────────────────────────┤ RP2040 hub + sensors + buck
Z+000 ├──────────────────────────┤ NEMA17 mount face
Z-040 └──────────────────────────┘ NEMA17 motor body (external)
```

---

## 🔌 Connector Standards Summary

| Standard | Pitch | Pins | Used for |
|---|---|---|---|
| QWIIC / STEMMA QT | 1.0mm JST SH | 4 | ALL sensors (GND/3V3/SDA/SCL) |
| JST PH | 2.0mm | 2 | Battery |
| JST PH | 2.0mm | 4 | Stepper coils |
| USB-C PD | — | — | Pi 5 power (27W) |
| USB-C | — | — | RP2040 data |
| USB-A | — | — | Coral Accelerator |
| FPC 15-pin | 1.0mm | 15 | Camera CSI-2 |

---

## 💰 Total BOM Cost

| # | Item | Cost |
|---|---|---|
| 01 | Raspberry Pi 5 8GB | $80 |
| 02 | Coral USB Accelerator | $60 |
| 03 | Camera Module 3 Wide | $35 |
| 04 | I2S MEMS Mic | $7 |
| 05 | NEMA17 Stepper | $12 |
| 06 | TMC2209 Driver | $8 |
| 07 | QWIIC Pro Micro RP2040 | $12 |
| 08 | LSM6DSOX IMU | $12 |
| 09 | BME688 Env Sensor | $20 |
| 10 | INA219 Power Monitor | $10 |
| 11 | PowerBoost 1000C | $20 |
| 12 | 18650 Cells ×2 | $18 |
| 13 | Buck Converter | $8 |
| — | USB hub, cables, standoffs, hardware | ~$25 |
| **TOTAL** | | **~$327** |
