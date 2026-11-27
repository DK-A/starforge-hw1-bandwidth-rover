"""Generate an IEEE-style publication-grade system architecture block diagram."""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

os.makedirs("assets", exist_ok=True)


def draw_block(ax, x, y, w, h, title, subtitle="", fc="#ffffff", ec="#1f2937", lw=1.6, title_size=9.5):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=3
    )
    ax.add_patch(box)
    if subtitle:
        ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center",
                fontsize=title_size, fontweight="bold", color="#111827", zorder=4)
        ax.text(x + w / 2, y + h * 0.30, subtitle, ha="center", va="center",
                fontsize=7.6, color="#374151", zorder=4)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center",
                fontsize=title_size, fontweight="bold", color="#111827", zorder=4)


def draw_zone(ax, x, y, w, h, label, fc="#f8fafc", ec="#64748b", ls="--"):
    zone = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.12",
        facecolor=fc, edgecolor=ec, linewidth=1.3, linestyle=ls, zorder=1
    )
    ax.add_patch(zone)
    ax.text(x + 0.18, y + h - 0.18, label, ha="left", va="top",
            fontsize=8.5, fontweight="bold", color=ec, zorder=2)


def draw_arrow(ax, x1, y1, x2, y2, label="", color="#1f2937", lw=1.5, ls="-", label_offset=(0, 0.13), ha="center"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="-|>,head_length=0.5,head_width=0.3", color=color, lw=lw, linestyle=ls),
        zorder=5
    )
    if label:
        mx, my = (x1 + x2) / 2 + label_offset[0], (y1 + y2) / 2 + label_offset[1]
        ax.text(mx, my, label, ha=ha, va="center", fontsize=7.5, fontweight="bold",
                color=color, bbox=dict(boxstyle="round,pad=0.15", facecolor="#ffffff", edgecolor="none", alpha=0.88), zorder=6)


def main():
    fig, ax = plt.subplots(figsize=(13.5, 7.2), dpi=300)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 7.8)
    ax.axis("off")

    # Title
    ax.text(7.0, 7.52, "STARFORGE HW-1: Bandwidth-Capped Teleoperation System Architecture",
            ha="center", va="center", fontsize=13, fontweight="bold", color="#0f172a")
    ax.text(7.0, 7.22, "IEEE-Style Functional Block Diagram — Control, Data, Watchdog Safety & Power Domains",
            ha="center", va="center", fontsize=9, color="#475569")

    # Domain 1: Ground Station Laptop
    draw_zone(ax, 0.3, 1.3, 3.3, 5.5, "1. GROUND STATION (OPERATOR)", fc="#eff6ff", ec="#1d4ed8")
    draw_block(ax, 0.55, 5.1, 2.8, 1.15, "Teleop Web HUD", "W/A/S/D + E-Stop + Cap Selector\nMJPEG / Telemetry Display", fc="#ffffff", ec="#1d4ed8")
    draw_block(ax, 0.55, 3.45, 2.8, 1.15, "FastAPI + UDP Bridge", "4B Binary Cmd + 10 Hz Heartbeat\nLatest-Command Semantics", fc="#ffffff", ec="#1d4ed8")
    draw_block(ax, 0.55, 1.75, 2.8, 1.15, "IP-Layer Usage Meter", "1 s Sliding Window (kbps)\nCmd + Telem + Video vs. Cap", fc="#ffffff", ec="#1d4ed8")

    # Domain 2: Raspberry Pi 4 / Pi 5
    draw_zone(ax, 4.7, 1.3, 4.3, 5.5, "2. ONBOARD SBC (RASPBERRY PI 4 / 5)", fc="#f0fdf4", ec="#15803d")
    draw_block(ax, 5.0, 5.25, 1.75, 1.05, "CSI / USB Camera", "Fixed 640×480\nLocal Capture", fc="#ffffff", ec="#15803d")
    draw_block(ax, 7.0, 5.25, 1.75, 1.05, "Adaptive Encoder", "In-Memory Resize\nJPEG + FPS + Hysteresis", fc="#ffffff", ec="#15803d")
    draw_block(ax, 5.0, 3.45, 3.75, 1.2, "Central Traffic Budget Scheduler", "Reserves 6–8 kbps Control + 2–4 kbps Telem\nDrops/Defers Frames Above Cap", fc="#ffffff", ec="#15803d")
    draw_block(ax, 5.0, 1.75, 3.75, 1.15, "UDP Cmd Rx & Link Monitor", "Port 9000 Receiver | 250 ms Timeout\n20 Hz UART Feed (Halts on Wi-Fi Drop)", fc="#ffffff", ec="#15803d")

    # Domain 3: ESP32-S3 + Drive & Power
    draw_zone(ax, 10.1, 1.3, 3.6, 5.5, "3. REAL-TIME MCU & ACTUATION", fc="#fef2f2", ec="#b91c1c")
    draw_block(ax, 10.4, 4.85, 3.0, 1.35, "ESP32-S3 Safety MCU", "450 ms Hardware Watchdog\n20 kHz Dual H-Bridge PWM\nSafe-Stop (PWM = 0) on Drop", fc="#ffffff", ec="#b91c1c")
    draw_block(ax, 10.4, 3.15, 3.0, 1.15, "Dual H-Bridge Driver", "Stall-Current Rated (BTS7960 / MDD10A)\nLeft Pair + Right Pair Channels", fc="#ffffff", ec="#b91c1c")
    draw_block(ax, 10.4, 1.65, 3.0, 1.0, "4 × 12V DC Geared Motors", "Compact PVC Pipe Skid-Steer\nBraced 30 cm Camera Mast", fc="#ffffff", ec="#b91c1c")

    # Power Bus (Bottom)
    draw_zone(ax, 4.7, 0.2, 9.0, 0.85, "4. ISOLATED POWER SUBSYSTEM", fc="#fffbeb", ec="#b45309", ls="-")
    ax.text(9.3, 0.55, "3S 12V LiPo + Main Fuse  ──►  Direct 12V Rail (Motor Driver)   |   Dedicated 5V/5A (Pi 5) or 5V/3A (Pi 4) Buck (SBC + ESP32-S3)",
            ha="center", va="center", fontsize=8.2, fontweight="bold", color="#78350f", zorder=4)

    # Internal arrows
    draw_arrow(ax, 1.95, 5.1, 1.95, 4.6, "", color="#1d4ed8")
    draw_arrow(ax, 1.95, 2.9, 1.95, 3.45, "", color="#1d4ed8")
    draw_arrow(ax, 6.75, 5.77, 7.0, 5.77, "", color="#15803d")
    draw_arrow(ax, 7.87, 5.25, 7.87, 4.65, "", color="#15803d")
    draw_arrow(ax, 11.9, 4.85, 11.9, 4.3, "", color="#b91c1c")
    draw_arrow(ax, 11.9, 3.15, 11.9, 2.65, "", color="#b91c1c")

    # Wireless & Wired Cross-Domain Links
    draw_arrow(ax, 5.0, 4.05, 3.35, 2.35, "Video + Telem\n(UDP :8001)", color="#0284c7", lw=1.8, label_offset=(-0.05, 0.28))
    draw_arrow(ax, 3.35, 4.05, 5.0, 2.35, "4B Cmd + 10Hz HB\n(UDP :9000)", color="#dc2626", lw=1.8, label_offset=(-0.05, -0.32))
    draw_arrow(ax, 8.75, 2.32, 10.4, 5.45, "USB/UART\n20 Hz", color="#b91c1c", lw=1.8, label_offset=(-0.15, 0.25))

    # Legend / Footer
    ax.text(0.3, 0.55, "Link Isolation:\n• Red: Control & Watchdog\n• Blue: Capped Video/Telem\n• Amber: Isolated Power",
            ha="left", va="center", fontsize=7.6, color="#334155",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#f8fafc", edgecolor="#cbd5e1"))

    plt.tight_layout()
    plt.savefig("assets/ieee_system_architecture.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("Generated assets/ieee_system_architecture.png")


if __name__ == "__main__":
    main()
