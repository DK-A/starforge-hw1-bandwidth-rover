# STARFORGE 2026 — Technical Project Report
## Track: Hardware Track | Problem Statement: `HW-1 — Bandwidth-Capped Teleoperation`

---

## 1. Event & Problem Statement Overview

- **Hackathon:** STARFORGE — 24-Hour National Level Space-Themed Hackathon
- **Host Institution:** BMS Institute of Technology & Management (BMSIT&M), Avalahalli, Yelahanka, Bengaluru
- **Track & Code:** Hardware Track — **`HW-1 | Bandwidth-Capped Teleoperation`**
- **Timeline:**
  - **Round 1 (Online Screening PPT):** Submission deadline **27 Nov 2026, 11:59 PM IST** (Unstop)
  - **Round 2 (24-Hour Offline Finale):** **12–13 Dec 2026** (`12 Dec, 8:00 AM IST` – `13 Dec, 3:30 PM IST`)
- **Eligibility & Team Rules:** Teams of **3–4 college students** with **at least 1 female member mandatory**. Free registration.
- **Prize Pool (₹65,000):** Overall Winner (₹25,000), Hardware Track Winner (₹15,000), Software Track Winner (₹15,000), Best Innovation (₹10,000).

### Official HW-1 Challenge Statement
> *"A rover on the Moon or Mars is driven over a slow, limited link shared by video, telemetry and commands. Build a teleoperated rover that a person drives using a live camera feed, with all communication, video included, kept within a fixed bandwidth budget set by the organisers. A live meter shows usage against the cap. The rover must finish a marked obstacle course, and exceeding the cap lowers the score."*

---

## 2. Official Requirements & Traceability Matrix

| # | Official HW-1 Expected Outcome | Engineering Design | Verification Method (Day 2 Demo) |
| :--- | :--- | :--- | :--- |
| **1** | **Rover with motor control, a camera, and a wireless link** | 4 × 12V DC geared motors driven by a stall-current-rated dual H-bridge controlled by **ESP32-S3** over USB/UART from a **Raspberry Pi 4/5** with CSI/USB camera over a dedicated **Laptop Hotspot Wi-Fi link**. | Rover drives smoothly via `W/A/S/D` using only the live wireless camera feed. |
| **2** | **Real-time measurement & display of data usage** | **IP-Layer / Interface-Level Bandwidth Meter** measuring actual transmitted + received bytes on the dedicated demo interface (or socket bytes + IP/UDP headers, validated against packet capture), broken down into **Commands + Telemetry + Video** vs. the organizer's cap (`kbps`). | Live meter updates every second during driving; measurement boundary is explicitly stated and validated. |
| **3** | **Dynamic bandwidth management (adjusting resolution/FPS, compression, or reducing telemetry)** | **Central Traffic Budget Scheduler** + **Per-Frame Adaptive Video** (in-memory `cv2.resize` + JPEG quality + FPS + hysteresis) so resolution/quality switch seamlessly without restarting the stream, and frames are dropped/deferred when the second's byte budget is exhausted. | Force cap down across stages (e.g., `250 → 150 → 80 kbps`) and record measured bitrate, FPS, resolution, dropped frames, and steering latency. |
| **4** | **Completing the course with few collisions, and stopping safely if the link drops** | **Braced elevated camera mast** + controlled demo speed (`~0.3–0.5 m/s`) + **3-Stage Safe-Stop Watchdog Chain** (Laptop combined command/heartbeat → Pi link monitor → ESP32-S3 hardware watchdog). | Complete obstacle course; cut Wi-Fi and measure **(a) timeout**, **(b) motor PWM cutoff**, and **(c) physical stopping distance** on the course surface. |

---

## 3. System & Network Architecture

```text
┌──────────────────────────┐        Wi-Fi (Dedicated Hotspot)     ┌──────────────────────────┐       USB / UART (20 Hz)       ┌──────────────────────────┐
│  Ground Station Laptop   │ ══ UDP Port 9000 (Cmd + HB) ═══════> │   Raspberry Pi 4 / Pi 5  │ ─────────────────────────────> │        ESP32-S3          │
│  • FastAPI + Web HUD     │    4B payload + 28B IP/UDP = 32B/pkt │   • Fixed Camera Capture │   ("M,L,R\n" / "PING\n")       │   • 20 kHz Motor PWM     │
│  • Bandwidth Meter       │    @ 10–20 Hz = 2.56–5.12 kbps (IP)  │   • In-Memory Resize/JPG │                                │   • Hardware Watchdog    │
│  • WASD + E-Stop         │ <══ Port 8000 (Video + Telemetry) ══ │   • Traffic Budget Sched │                                │   • Safe-Stop (PWM = 0)  │
└──────────────────────────┘                                      │   • Wi-Fi Link Monitor   │                                └────────────┬─────────────┘
                                                                  └──────────────────────────┘                                             │
                                                                                                                               ┌───────────▼─────────────┐
                                                                                                                               │  Dual H-Bridge Driver   │
                                                                                                                               │  (Sized to Motor Stall) │
                                                                                                                               │  + 4× 12V DC Motors     │
                                                                                                                               └─────────────────────────┘
```

### 3.1 Socket Isolation & Realistic Command Latency
- **Reduced Queuing Risk (Not Guaranteed Radio Priority):** Placing commands on a dedicated **UDP socket** (`Port 9000`) prevents steering/`STOP` packets from queuing behind large video frames in the application buffer. However, both flows still share Wi-Fi airtime, OS network queues, and Pi CPU.
- **Mitigations:**
  - Keep command packets tiny (`4 bytes` payload, `32 bytes` at IPv4/UDP layer).
  - Use **latest-command semantics** (overwrite stale steering commands instead of queuing old ones).
  - Embed the heartbeat inside the command packet (`10–20 Hz`) rather than sending separate heartbeat packets.
  - Isolate/nice the video encoder so it cannot starve the command receiver; **benchmark command latency under maximum video load**.

### 3.2 Realistic Command & Heartbeat Budget Calculation
- `4 bytes` payload + `8 bytes` UDP header + `20 bytes` IPv4 header = **`32 bytes` per packet (IP layer)**.
- At `20 Hz`: `32 × 20 × 8 = 5,120 bps` (**`5.12 kbps`**) — or **`2.56 kbps` at `10 Hz`**, before Wi-Fi MAC/PHY overhead.
- Accordingly, the scheduler reserves **`6–8 kbps`** (not `1 kbps`) for control + heartbeat traffic.

---

## 4. Bandwidth Metering vs. Central Traffic Budget Scheduler

These are treated as **two distinct subsystems**:

### 4.1 Honest Bandwidth Meter (Measurement Boundary)
- **What is measured:** Clearly define the boundary—either read the dedicated Linux network interface counters (`/sys/class/net/<iface>/statistics/tx_bytes` & `rx_bytes` on an isolated hotspot interface) **or** count exact transmitted socket bytes + IP/UDP/TCP headers and **validate accuracy against `tcpdump` / Wireshark**.
- *(Do not claim MAC/PHY-level Wi-Fi airtime precision unless measured at the interface/capture level.)*

### 4.2 Central Traffic Budget Scheduler (Enforcement)
Every 1-second window:
1. **Reserve Control Budget:** Deduct `6–8 kbps` for UDP commands + embedded heartbeat.
2. **Reserve Telemetry Budget:** Deduct fixed telemetry allowance (e.g., `2–4 kbps`, throttled under tight caps).
3. **Allocate Video Budget:** `Video Budget = Organizer Cap - (Control + Telemetry)`.
4. **Enforce Before Send:** Check the **actual encoded JPEG byte size + transport/IP header overhead** against remaining video bytes in the current window. **Drop or defer the frame** if sending it would exceed the budget.

### 4.3 Seamless Live Video Adaptation (No Stream Restart)
- Keep the camera hardware open at a **single fixed capture resolution** (e.g., `640×480`).
- Perform **per-frame in-memory resizing** (`640×480` → `320×240` → `160×120`), **JPEG quality scaling** (`70` → `35` → `15`), and **frame pacing** (`15` → `8` → `3 FPS`) inside the Python loop—so quality changes **on the very next frame** without restarting the camera, freezing the stream, or breaking the client decoder.
- **Hysteresis:** Step **down fast** (`> 85%` budget utilization) and step **up slowly** (`< 55%` sustained for `1.5–2.0 s`) to prevent oscillation.
- **Validation Targets:** Test forced caps at **`250 kbps`**, **`150 kbps`**, and **`80 kbps`**, logging actual measured bitrate, FPS, resolution, dropped frames, and steering latency.

---

## 5. Safe-Stop Watchdog Chain & Physical Stopping Distance

### 5.1 Three-Stage Chain
1. **Laptop → Pi (`10–20 Hz` UDP):** Combined command + heartbeat packet.
2. **Pi Link Monitor (`200–300 ms` timeout):** Forwards commands/`PING` to ESP32-S3 at `20 Hz` while laptop packets arrive; halts UART output immediately if laptop packets time out.
3. **ESP32-S3 Hardware Watchdog (`300–450 ms` timeout):** Tuned above normal UART/Python jitter to avoid false stops; cuts all motor PWMs to `0` on timeout.

### 5.2 Stopping Distance Physics & Required Testing
At speed $v = 1\text{ m/s}$ and total timeout $t = 0.8\text{ s}$, the rover travels $d = v \times t = 0.8\text{ m}$ **before** motor power is even cut (plus mechanical coasting distance).
- **Mitigation:** Cap demo speed to **`~0.35–0.5 m/s`** on the obstacle course and tune timeouts on the live link.
- **Empirical Verification:** Measure and report all **three distinct events** on the actual test surface:
  1. `Command timeout` (ms)
  2. `Motor PWM disabled` (ms)
  3. `Physical vehicle stopping distance` (cm)

---

## 6. Mechanical & Electrical Sizing (Mandatory Pre-Build Checks)

### 6.1 Motor, Driver & Power Audit (Verify Before Final Assembly)
Do **not** assume a module's advertised peak rating equals usable continuous current. Before finalizing wiring, verify and document:
- **Motor specs:** Rated voltage (`12V`), **rated current**, and **stall current per motor** (2 motors in parallel per side = `2×` stall current).
- **Driver specs:** Continuous current rating without active cooling, peak current capability, and **braking truth table** (e.g., `IN1/IN2` vs. `RPWM/LPWM` + enable pins).
- **Battery & Protection:** 3S LiPo discharge rating (`C-rating`), main fuse rating, wire gauge, and connector ratings.
- **Separate Pi Power Rail:** Raspberry Pi 4 requires `5V / 3A`, whereas **Raspberry Pi 5 requires `5V / 5A` (USB-C PD)** under load. Power the Pi from a dedicated, properly rated 5V regulator isolated from motor voltage sag.

### 6.2 Pipe Rover Frame
- **Compact Square PVC Chassis:** Wheelbase ≈ track width for predictable 4-wheel skid-steer turns.
- **Braced Elevated Camera Mast (~30 cm):** Reinforced with a **diagonal pipe brace** so bumps do not shake the camera (stabilizing both driver view and JPEG compression).
- **Curved Front Bumper:** Protects motors and mast on the course.

---

## 7. Phased 24-Hour Build Plan (Risk-Controlled)

Instead of packing all features into Day 1, build in **4 strict phases**:

- **Phase 0 — Minimum Drivable Rover (Hours 0–6):**
  - Assemble PVC frame, wire motors/driver/power safely, flash basic ESP32-S3 motor + watchdog sketch, run basic `W/A/S/D` UDP control + fixed-quality camera stream + **verify link-drop stop**.
- **Phase 1 — Graded HW-1 Core (Hours 6–12):**
  - Implement **Central Traffic Budget Scheduler**, **honest Bandwidth Meter** (validated with packet capture), and **seamless per-frame adaptive resize/FPS/JPEG + hysteresis**.
- **Phase 2 — Benchmarking & Course Tuning (Hours 12–18):**
  - Run `250 / 150 / 80 kbps` cap tests; log actual bitrate, FPS, command latency under video load, and physical stopping distance; tune demo speed.
- **Phase 3 — Polish & Optional Stretch (Hours 18–24):**
  - Rehearse Day 2 demo. Only if Phases 0–2 are 100% stable: add **grayscale fallback** or **ExecuTorch (`MobileNetV3-Small` `.pte`) collision-warning overlay** *(strictly as an optional co-pilot)*.

---

## 8. Day 2 Live Demo Script

1. **Baseline Teleop & Meter:** Set organizer cap (e.g., `250 kbps`); drive via live camera feed and show the meter staying under the cap.
2. **Multi-Stage Cap Enforcement:** Drop cap live (`250 → 150 → 80 kbps`); show seamless frame-by-frame scaling without stream restarts or command lag, backed by logged test metrics.
3. **Obstacle Course Run:** Complete the marked course at controlled speed with minimal collisions.
4. **Link-Drop Safe Stop:** Disconnect Wi-Fi while moving; verify motor cutoff and short physical stopping distance.
