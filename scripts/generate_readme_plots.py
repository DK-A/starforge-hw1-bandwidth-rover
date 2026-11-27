"""Generate analytical engineering plots for the STARFORGE HW-1 README."""

import os
import matplotlib
matplotlib.use("Agg")
import numpy as np
import matplotlib.pyplot as plt

os.makedirs("assets", exist_ok=True)

# Global dark aerospace styling
plt.rcParams.update({
    "figure.facecolor": "#0d1117",
    "axes.facecolor": "#161b22",
    "axes.edgecolor": "#30363d",
    "axes.labelcolor": "#c9d1d9",
    "text.color": "#e6edf3",
    "xtick.color": "#8b949e",
    "ytick.color": "#8b949e",
    "grid.color": "#21262d",
    "font.size": 10,
})


def plot_budget_allocation():
    caps = ["250 kbps Cap", "150 kbps Cap", "80 kbps Cap"]
    ctrl = np.array([6.0, 6.0, 6.0])       # 32B IP/UDP @ 20Hz = 5.12 kbps + margin
    telem = np.array([4.0, 3.0, 2.0])      # Throttled telemetry budget
    video = np.array([235.0, 136.0, 67.0]) # Remaining budget (with 5 kbps safety margin)
    margin = np.array([5.0, 5.0, 5.0])

    x = np.arange(len(caps))
    fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=180)

    ax.bar(x, ctrl, width=0.52, label="UDP Control + Embedded HB (6 kbps)", color="#f85149")
    ax.bar(x, telem, width=0.52, bottom=ctrl, label="Telemetry Budget (2–4 kbps)", color="#f0883e")
    ax.bar(x, video, width=0.52, bottom=ctrl + telem, label="Allocated Video Budget", color="#58a6ff")
    ax.bar(x, margin, width=0.52, bottom=ctrl + telem + video, label="Safety Headroom (5 kbps)", color="#30363d", hatch="//")

    for i, total in enumerate(ctrl + telem + video):
        ax.text(i, total + 10, f"Video: {video[i]:.0f} kbps\n(Active: {total:.0f}/{[250,150,80][i]} kbps)",
                ha="center", va="bottom", fontsize=9, fontweight="bold", color="#e6edf3")

    ax.set_xticks(x)
    ax.set_xticklabels(caps, fontweight="bold")
    ax.set_ylabel("IP-Layer Bandwidth (kbps)")
    ax.set_ylim(0, 300)
    ax.set_title("Central Traffic Budget Scheduler — Priority Slicing Model\n(vs. Unthrottled 640×480 @ 20 FPS Webcam ≈ 2,000–5,000 kbps)",
                 fontsize=11.5, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    ax.legend(loc="upper right", frameon=True, facecolor="#0d1117", edgecolor="#30363d")

    plt.tight_layout()
    plt.savefig("assets/budget_allocation_chart.png", dpi=180)
    plt.close()


def plot_adaptive_hysteresis():
    t = np.linspace(0, 60, 121)  # 0.5s steps
    cap = np.piecewise(t, [t < 20, (t >= 20) & (t < 40), t >= 40], [250.0, 150.0, 80.0])

    # Simulated IP-layer throughput with hysteresis & frame-drop guard
    rng = np.random.default_rng(42)
    used = np.zeros_like(t)
    tier = np.zeros_like(t)
    # Tiers: 4=640x480@15, 3=480x360@12, 2=320x240@10, 1=240x180@6, 0=160x120@3
    tier_kbps = {4: 215, 3: 165, 2: 120, 1: 85, 0: 55}
    cur_tier = 4
    low_streak = 0

    for i in range(len(t)):
        base = tier_kbps[cur_tier] + rng.normal(0, 6)
        # Hard frame-drop guard keeps throughput <= cap
        used[i] = min(base, cap[i] - 4.0)
        util = (used[i] / cap[i]) * 100.0
        if util > 85.0 and cur_tier > 0:
            cur_tier -= 1
            low_streak = 0
        elif util < 55.0 and cur_tier < 4:
            low_streak += 1
            if low_streak >= 4:  # 2.0s sustained headroom
                cur_tier += 1
                low_streak = 0
        else:
            low_streak = 0
        tier[i] = cur_tier

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.4), dpi=180, sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})

    ax1.step(t, cap, where="post", color="#f85149", linestyle="--", linewidth=2, label="Organizer Bandwidth Cap (kbps)")
    ax1.plot(t, used, color="#3fb950", linewidth=2, label="Scheduler Enforced IP-Layer Rate (kbps)")
    ax1.fill_between(t, used, 0, color="#3fb950", alpha=0.12)
    ax1.set_ylabel("Throughput (kbps)")
    ax1.set_ylim(0, 290)
    ax1.set_title("Analytical Adaptive Video & Hysteresis Profile (Design Simulation)",
                  fontsize=11.5, fontweight="bold", pad=10)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper right", frameon=True, facecolor="#0d1117", edgecolor="#30363d")

    ax2.step(t, tier, where="post", color="#58a6ff", linewidth=2)
    ax2.set_yticks([0, 1, 2, 3, 4])
    ax2.set_yticklabels(["160×120\n3 FPS", "240×180\n6 FPS", "320×240\n10 FPS", "480×360\n12 FPS", "640×480\n15 FPS"], fontsize=8)
    ax2.set_xlabel("Time (seconds)")
    ax2.set_ylabel("Quality Tier")
    ax2.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig("assets/adaptive_hysteresis_profile.png", dpi=180)
    plt.close()


def plot_stopping_distance():
    speeds = np.array([0.35, 0.50, 0.75, 1.00])
    t_pi = 0.25       # Pi link-monitor timeout (s)
    t_esp = 0.45      # ESP32-S3 watchdog timeout (s)
    t_total = t_pi + t_esp  # 0.70 s before PWM=0

    d_timeout = speeds * t_total
    # Analytical coasting distance estimate after PWM=0: v^2 / (2*a), a ≈ 2.2 m/s^2
    d_coast = (speeds ** 2) / (2 * 2.2)

    x = np.arange(len(speeds))
    fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=180)

    ax.bar(x, d_timeout * 100, width=0.48, label="Travel During Watchdog Delay (0.70 s: Pi 250ms + ESP32 450ms)", color="#f0883e")
    ax.bar(x, d_coast * 100, width=0.48, bottom=d_timeout * 100, label="Estimated Mechanical Coasting After PWM=0", color="#f85149")

    for i in range(len(speeds)):
        tot_cm = (d_timeout[i] + d_coast[i]) * 100
        ax.text(i, tot_cm + 2.5, f"{tot_cm:.1f} cm", ha="center", va="bottom", fontweight="bold", color="#e6edf3")

    ax.axvspan(-0.4, 1.4, color="#3fb950", alpha=0.10, label="Recommended Demo Speed Zone (0.35–0.50 m/s)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s:.2f} m/s" for s in speeds], fontweight="bold")
    ax.set_ylabel("Stopping Distance (cm)")
    ax.set_ylim(0, 110)
    ax.set_title("Safe-Stop Physics Model (d = v·t + Coasting) — Why Demo Speed Is Capped\n(Analytical Projection; To Be Verified Empirically on Course Surface)",
                 fontsize=11, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    ax.legend(loc="upper left", frameon=True, facecolor="#0d1117", edgecolor="#30363d", fontsize=8.5)

    plt.tight_layout()
    plt.savefig("assets/stopping_distance_analysis.png", dpi=180)
    plt.close()


if __name__ == "__main__":
    plot_budget_allocation()
    plot_adaptive_hysteresis()
    plot_stopping_distance()
    print("Generated 3 engineering plots in assets/")
