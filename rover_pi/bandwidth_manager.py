"""
Central Traffic Budget Scheduler & IP-Layer Bandwidth Meter for STARFORGE HW-1.

Separates observation (Meter) from enforcement (Scheduler):
  - Reserves 6-8 kbps for 4-byte UDP control + embedded heartbeat (32B @ IPv4/UDP)
  - Reserves 2-4 kbps for telemetry (throttled under tight caps)
  - Allocates remaining byte budget to video
  - Enforces per-frame byte guard before transmission
  - Applies hysteresis (fast step-down >85%, slow step-up <55% for 2.0s)
"""

from collections import deque
from dataclasses import dataclass
import time
from typing import Deque, Tuple


IP_UDP_OVERHEAD_BYTES = 28  # 20B IPv4 + 8B UDP


@dataclass(frozen=True)
class QualityProfile:
    name: str
    width: int
    height: int
    fps: int
    jpeg_quality: int
    grayscale: bool
    telemetry_hz: float


QUALITY_TIERS = [
    QualityProfile("ULTRA_LOW", 160, 120, 3, 18, True, 1.0),
    QualityProfile("LOW",       240, 180, 6, 28, False, 2.0),
    QualityProfile("MEDIUM",    320, 240, 10, 40, False, 4.0),
    QualityProfile("HIGH",      480, 360, 12, 55, False, 6.0),
    QualityProfile("MAX",       640, 480, 15, 70, False, 8.0),
]


class TrafficBudgetScheduler:
    """1-second sliding-window IP-layer meter and central traffic budget scheduler."""

    def __init__(self, cap_kbps: float = 250.0, window_sec: float = 1.0):
        self.cap_kbps = max(40.0, float(cap_kbps))
        self.window_sec = window_sec
        self._samples: Deque[Tuple[float, int, str]] = deque()
        self.tier_index: int = 2  # Start at MEDIUM (320x240 @ 10 FPS)
        self._last_adapt_ts: float = 0.0
        self._low_util_since: float | None = None
        self.total_bytes: int = 0
        self.dropped_frames: int = 0

    def set_cap_kbps(self, cap_kbps: float) -> None:
        self.cap_kbps = max(40.0, float(cap_kbps))

    def record_packet(self, payload_bytes: int, category: str = "video", header_bytes: int = IP_UDP_OVERHEAD_BYTES) -> None:
        """Record transmitted/received packet bytes at the IP layer."""
        now = time.monotonic()
        wire_bytes = payload_bytes + header_bytes
        self._samples.append((now, wire_bytes, category))
        self.total_bytes += wire_bytes
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_sec
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def get_usage(self) -> dict:
        """Return IP-layer bandwidth breakdown in kbps."""
        now = time.monotonic()
        self._prune(now)
        by_cat = {"video": 0, "telemetry": 0, "command": 0}
        for _, nbytes, cat in self._samples:
            by_cat[cat] = by_cat.get(cat, 0) + nbytes

        scale = 8.0 / (self.window_sec * 1000.0)
        video_kbps = by_cat["video"] * scale
        telem_kbps = by_cat["telemetry"] * scale
        cmd_kbps = by_cat["command"] * scale
        total_kbps = video_kbps + telem_kbps + cmd_kbps
        utilization = (total_kbps / self.cap_kbps) * 100.0 if self.cap_kbps > 0 else 0.0

        return {
            "total_kbps": round(total_kbps, 2),
            "video_kbps": round(video_kbps, 2),
            "telemetry_kbps": round(telem_kbps, 2),
            "command_kbps": round(cmd_kbps, 2),
            "cap_kbps": round(self.cap_kbps, 1),
            "utilization_pct": round(utilization, 1),
            "exceeded": total_kbps > self.cap_kbps,
            "dropped_frames": self.dropped_frames,
            "total_kb": round(self.total_bytes / 1024.0, 2),
            "tier": self.current_profile.name,
            "measurement_boundary": "IP-layer (payload + IPv4/UDP headers)",
        }

    @property
    def current_profile(self) -> QualityProfile:
        return QUALITY_TIERS[self.tier_index]

    def can_send_video_frame(self, encoded_payload_bytes: int) -> bool:
        """Hard budget guard: drop frame if sending it (+ IP/UDP headers) would breach cap."""
        usage = self.get_usage()
        est_wire_bytes = encoded_payload_bytes + IP_UDP_OVERHEAD_BYTES
        projected_kbps = usage["total_kbps"] + (est_wire_bytes * 8.0 / (self.window_sec * 1000.0))
        # Reserve 4 kbps safety headroom for control/telemetry jitter
        allowed = projected_kbps <= max(20.0, self.cap_kbps - 4.0)
        if not allowed:
            self.dropped_frames += 1
        return allowed

    def adapt(self) -> QualityProfile:
        """Hysteresis controller: step down fast (>85%), step up slowly (<55% for 2.0s)."""
        now = time.monotonic()
        usage = self.get_usage()
        util = usage["utilization_pct"]

        if util > 85.0:
            self._low_util_since = None
            if self.tier_index > 0 and (now - self._last_adapt_ts >= 0.5):
                self.tier_index -= 1
                self._last_adapt_ts = now
        elif util < 55.0:
            if self._low_util_since is None:
                self._low_util_since = now
            elif (now - self._low_util_since >= 2.0) and self.tier_index < len(QUALITY_TIERS) - 1:
                self.tier_index += 1
                self._last_adapt_ts = now
                self._low_util_since = None
        else:
            self._low_util_since = None

        return self.current_profile
