"""
STARFORGE HW-1 | Raspberry Pi Edge Rover Node
--------------------------------------------
- Dedicated UDP socket (port 9000) for 4-byte binary commands + embedded heartbeat
- 250 ms Wi-Fi link monitor -> stops ESP32-S3 UART pings on link drop
- Fixed-resolution camera capture with seamless per-frame resize & JPEG encoding
- Central Traffic Budget Scheduler enforcing organizer bandwidth cap
"""

import argparse
import json
import socket
import struct
import threading
import time

import cv2
import numpy as np

from bandwidth_manager import TrafficBudgetScheduler

CMD_STRUCT = struct.Struct("<bbBB")  # left_pct (-100..100), right_pct (-100..100), flags, seq


class SerialBridge:
    def __init__(self, port: str, baud: int = 115200, mock: bool = False):
        self.mock = mock
        self.ser = None
        if not mock:
            import serial
            self.ser = serial.Serial(port, baud, timeout=0.05)

    def send_drive(self, left_pwm: int, right_pwm: int) -> None:
        msg = f"M,{left_pwm},{right_pwm}\n"
        if self.mock:
            return
        if self.ser and self.ser.is_open:
            self.ser.write(msg.encode("ascii"))

    def send_ping(self) -> None:
        if self.mock:
            return
        if self.ser and self.ser.is_open:
            self.ser.write(b"PING\n")


def main():
    parser = argparse.ArgumentParser(description="STARFORGE HW-1 Rover Pi Node")
    parser.add_argument("--ground-ip", default="127.0.0.1", help="Ground station laptop IP")
    parser.add_argument("--video-port", type=int, default=8001, help="UDP video/telemetry target port")
    parser.add_argument("--cmd-port", type=int, default=9000, help="UDP command/heartbeat listen port")
    parser.add_argument("--serial-port", default="/dev/ttyACM0", help="ESP32-S3 serial port")
    parser.add_argument("--cap-kbps", type=float, default=250.0, help="Initial bandwidth cap (kbps)")
    parser.add_argument("--mock", action="store_true", help="Run without physical ESP32-S3/camera")
    args = parser.parse_args()

    scheduler = TrafficBudgetScheduler(cap_kbps=args.cap_kbps)
    bridge = SerialBridge(args.serial_port, mock=args.mock)

    state = {
        "left_pwm": 0,
        "right_pwm": 0,
        "last_hb_ts": time.monotonic(),
        "link_alive": False,
    }
    state_lock = threading.Lock()

    # 1. Dedicated UDP Command & Heartbeat Listener (latest-command semantics)
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cmd_sock.bind(("0.0.0.0", args.cmd_port))
    cmd_sock.settimeout(0.05)

    def command_loop():
        while True:
            try:
                data, _ = cmd_sock.recvfrom(64)
                scheduler.record_packet(len(data), category="command")
                if len(data) == CMD_STRUCT.size:
                    left_pct, right_pct, flags, _ = CMD_STRUCT.unpack(data)
                    # Optional cap update flag or E-stop (flags & 1)
                    if flags & 1:
                        left_pct, right_pct = 0, 0
                    with state_lock:
                        state["left_pwm"] = int(max(-100, min(100, left_pct)) * 2.55)
                        state["right_pwm"] = int(max(-100, min(100, right_pct)) * 2.55)
                        state["last_hb_ts"] = time.monotonic()
                        state["link_alive"] = True
                elif data.startswith(b"CAP:"):
                    new_cap = float(data.decode("ascii").split(":", 1)[1])
                    scheduler.set_cap_kbps(new_cap)
            except socket.timeout:
                pass
            except Exception:
                pass

            # 250 ms Wi-Fi link monitor -> stop feeding ESP32-S3 if link drops
            with state_lock:
                alive = (time.monotonic() - state["last_hb_ts"]) <= 0.25
                state["link_alive"] = alive
                lp, rp = state["left_pwm"], state["right_pwm"]
            if alive:
                bridge.send_drive(lp, rp)
            time.sleep(0.05)  # 20 Hz ESP32-S3 feed rate

    threading.Thread(target=command_loop, daemon=True).start()

    # 2. Fixed-Resolution Camera Capture + In-Memory Adaptive Stream
    cap = None if args.mock else cv2.VideoCapture(0)
    if cap is not None:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    video_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    last_telem_ts = 0.0

    print(f"[ROVER] Listening UDP cmds on :{args.cmd_port}, streaming to {args.ground_ip}:{args.video_port} (cap={args.cap_kbps} kbps)")
    while True:
        profile = scheduler.adapt()
        frame_interval = 1.0 / max(1, profile.fps)
        t_start = time.monotonic()

        if cap is not None and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                continue
        else:
            # Synthetic test frame in --mock mode
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, f"MOCK ROVER | {profile.name}", (30, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 120), 2)

        resized = cv2.resize(frame, (profile.width, profile.height))
        if profile.grayscale:
            resized = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        ok, enc = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), profile.jpeg_quality])
        if ok:
            payload = enc.tobytes()
            # Keep single-datagram UDP frames under MTU (< 60 KB)
            if len(payload) < 60000 and scheduler.can_send_video_frame(len(payload)):
                video_sock.sendto(b"VID:" + payload, (args.ground_ip, args.video_port))
                scheduler.record_packet(len(payload) + 4, category="video")

        now = time.monotonic()
        if now - last_telem_ts >= (1.0 / profile.telemetry_hz):
            with state_lock:
                link_ok = state["link_alive"]
            telem = json.dumps({"link": link_ok, "usage": scheduler.get_usage()}).encode("utf-8")
            video_sock.sendto(b"TLM:" + telem, (args.ground_ip, args.video_port))
            scheduler.record_packet(len(telem) + 4, category="telemetry")
            last_telem_ts = now

        elapsed = time.monotonic() - t_start
        if elapsed < frame_interval:
            time.sleep(frame_interval - elapsed)


if __name__ == "__main__":
    main()
