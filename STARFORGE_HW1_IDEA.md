# STARFORGE 2026 — HW-1: Bandwidth-Capped Teleoperation
**Realistic 24-Hour Build Plan & Round 1 Blueprint**

---

## 1. Hackathon & Problem Statement Summary

- **Event:** STARFORGE — 24-Hour National Level Space-Themed Hackathon (BMSIT&M, Bengaluru)
- **Track:** Hardware Track (`HW-1 | Bandwidth-Capped Teleoperation`)
- **Dates:**
  - **Round 1 (PPT Screening):** Deadline **27 Nov 2026, 11:59 PM IST** (Unstop)
  - **Round 2 (24-Hour Offline Finale):** **12–13 Dec 2026** at BMSIT&M, Bengaluru
- **Team Rules:** 3–4 members, **at least 1 female member mandatory**, free registration.
- **Prizes (₹65,000 Pool):** Overall Winner (₹25,000), Hardware Track Winner (₹15,000), Software Track Winner (₹15,000), Best Innovation (₹10,000).

### Exact HW-1 Deliverables
1. **Working Rover Hardware:** Motor control, onboard camera, and wireless link.
2. **Real-Time Bandwidth Meter:** Live display of total data usage (**video + telemetry + commands**) against a fixed cap set by the organizers *(exceeding the cap lowers the score)*.
3. **Dynamic Bandwidth Management:** Automatically adapt video resolution, FPS, compression, or telemetry rate to stay under the cap.
4. **Course Completion + Safe Stop:** Navigate a marked obstacle course via live camera with minimal collisions, and **stop safely if the wireless link drops**.

---

## 2. Build Scope & Priority Tiers (24-Hour Execution Plan)

> **Execution Gate:** Do **not** touch Tier 2 until **Tier 1** passes a full obstacle-course run **and** a live Wi-Fi-cut safe-stop test.

### Tier 1 — Must-Have (Core 24-Hour Build)
- **Dedicated UDP Socket for 4-Byte Binary Commands & Heartbeat:**
  - Commands and heartbeats travel on their **own UDP socket**, completely separate from video—eliminating TCP/WebSocket head-of-line blocking behind video frames.
  - Commands get **Priority #1** in the bandwidth budget; video only uses leftover bandwidth (`Cap - Commands - Telemetry`).
- **Adaptive Video Controller with Hysteresis:**
  - Automatically steps **Resolution** (`640×480` → `320×240` → `160×120`), **FPS** (`15` → `8` → `3`), and **JPEG Quality** (`70` → `35` → `15`), plus a **drop-the-frame guard** if a frame would breach the cap.
  - **Hysteresis prevents oscillation:** Step **down fast** when utilization crosses `> 85%`, and step **up slowly** only after sustained headroom (`< 55%` for 1.5–2 s).
- **Honest On-the-Wire Bandwidth Meter:**
  - Counts **application socket bytes + IP/UDP/TCP header overhead** (or measures on a dedicated demo interface with SSH/background traffic isolated so OS chatter doesn't distort the reading).
  - *Organizer Cap Note:* Confirm whether the cap is enforced by a router/Wi-Fi throttle or software measurement—the adaptive controller handles both using self-measured wire rate + RTT/loss feedback.
- **3-Stage Safe-Stop Watchdog Chain (Target Stop: under ~0.7–0.8 s):**
  1. **Laptop:** Sends UDP heartbeat at `10 Hz`.
  2. **Pi Link Monitor:** While laptop heartbeats arrive, Pi forwards commands/pings to ESP32-S3 at `20 Hz` (every 50 ms). If no laptop heartbeat arrives for `> 300 ms`, Pi **stops sending** to the ESP32-S3.
  3. **ESP32-S3 Hardware Watchdog:** Timeout set to **`450–500 ms`** (ample margin for UART/Python jitter to avoid false stops while driving). On timeout, ESP32-S3 **cuts all motor PWMs to 0**.

### Tier 2 — Nice-to-Have (Only After Tier 1 Checkpoint Passes)
- **Grayscale Fallback Mode:** Switch to 1-channel grayscale under severe caps to save bandwidth while keeping obstacle edges readable.
- **Smooth PWM Ramping & Speed Gears:** `Crawl / Normal / Boost` limits + smooth acceleration ramping on ESP32-S3.
- **Active Braking:** Driver-verified braking on stop (see Hardware Risks below).
- **Pre-Encode Peripheral Blur:** Fast Gaussian blur on outer edges before JPEG encoding so the center corridor stays sharper at lower byte sizes.

### Tier 3 — Stretch / Planned Enhancement
- **ExecuTorch Edge-AI Co-Pilot (`MobileNetV3-Small` → `.pte`):** Runs locally on the Pi to provide **collision-warning alerts** between low-FPS frames *(strictly a human-driving co-pilot, not autonomous driving)*.
- **MPU6050 Gyro Straight-Line Assist:** PID yaw correction on ESP32-S3.

---

## 3. System Architecture & Hardware Notes

```text
[Ground Station Laptop]  <-- UDP (4B Cmds + 10Hz HB) -->  [Raspberry Pi 4 / Pi 5]  <-- USB/UART (20Hz) -->  [ESP32-S3]  -->  [Motor Driver]  -->  [4x 12V Motors]
                         <-- Video + Telemetry ------->    • Camera Capture                                  • 20 kHz PWM
 • Live Video + Meter                                      • Adaptive JPEG + Hysteresis                      • 450-500 ms Watchdog
 • Wire-Level Byte Counter                                 • 300 ms Wi-Fi Link Monitor                       • Safe-Stop (PWM = 0)
```

### Hardware Sizing & Safety Checks (Critical for 4×12V Motors)
- **Stall Current Check:** Two 12V DC motors in parallel per side double current draw. Verify stall current before choosing the driver:
  - **L298N** (~2A max/channel) risks overheating/tripping on high-torque 12V geared motors under stall.
  - **BTS7960 (43A)** or **Cytron MDD10A (10A/ch)** is strongly preferred.
- **Braking Compatibility:** Verify your driver's truth table before implementing active braking (`IN1=1, IN2=1` works on L298N/TB6612, whereas BTS7960 uses `RPWM/LPWM` + `R_EN/L_EN`).
- **Power Isolation:** Use a 12V LiPo / 3S pack with a dedicated **5V buck converter (≥ 3A)** for the Pi 4/5 and ESP32-S3 to prevent brownouts on motor startup.

### Reusable Assets from `LunaBot` Repo
From [`DK-A/team_techtonics_lunabot_smart_horizon_2026`](https://github.com/DK-A/team_techtonics_lunabot_smart_horizon_2026):
- **`tools/web_dashboard/` (FastAPI + HTML/CSS/JS):** Repurpose the UI shell for the Teleop + Bandwidth Meter HUD.
- **`edge_pi/edge_agent.py`:** Reuse Pi CPU temp/RAM/load telemetry (throttled under tight caps).

---

## 4. Pipe Rover Mechanical Design

- **Compact Square PVC Frame:** Wheelbase ≈ track width for crisp 4-wheel skid-steer turns without tire scrub.
- **Braced Elevated Camera Mast (~30 cm):** Add a **diagonal pipe brace / triangle gusset** so the mast does not wobble on bumps (wobble ruins JPEG compression).
- **Curved Front Pipe Bumper & Centered Low Battery:** Protects hardware and equalizes traction across all 4 wheels.

---

## 5. Day 2 Live Demo Script

1. **Normal Teleop & Wire-Level Meter:** Set the organizer's cap (e.g., `250 kbps`), drive through obstacles via live camera, and show the meter staying green under the cap.
2. **Dynamic Bandwidth Adaptation (with Hysteresis):** Drop the cap live (e.g., to `80 kbps`). Show smooth step-down of resolution/FPS/quality without oscillation while UDP commands remain instant.
3. **Complete Obstacle Course:** Finish the course cleanly with minimal collisions.
4. **Safe Stop on Link Drop:** Cut Wi-Fi while driving—the Pi detects the missing laptop heartbeat (`300 ms`), stops pinging the ESP32-S3, and the **ESP32-S3 watchdog halts all 4 motors in under ~0.7–0.8 s**.

---

## 6. Tonight's Round 1 PPT Strategy (`STARFORGE_TEMPLATE.pptx`)

Lead with the 4 strongest engineering points:
1. **Command-First UDP Slicing** (4-byte binary commands on a separate UDP socket from video—zero head-of-line blocking).
2. **Honest On-the-Wire Metering** (socket + header bytes).
3. **Adaptive Video with Hysteresis** (step down fast, step up slowly + drop-frame guard).
4. **3-Stage Watchdog Safe Stop** (Laptop `10 Hz` → Pi `300 ms` monitor → ESP32-S3 `450–500 ms` watchdog, total stop `< 0.8 s`).
5. Present **ExecuTorch Edge-AI Co-Pilot** clearly as a **Planned Enhancement (Tier 3)**.
