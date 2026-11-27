"""
STARFORGE HW-1 | Ground Station Server (FastAPI + UDP Bridge)
-------------------------------------------------------------
- Receives UDP video frames & telemetry from Raspberry Pi (port 8001)
- Streams MJPEG video & JSON telemetry to the browser HUD
- Sends 4-byte binary UDP commands + 10 Hz heartbeat to Pi (port 9000)
"""

import argparse
import asyncio
import json
import socket
import struct
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

CMD_STRUCT = struct.Struct("<bbBB")  # left_pct, right_pct, flags, seq

app = FastAPI(title="STARFORGE HW-1 Ground Station")

STATE = {
    "rover_ip": "127.0.0.1",
    "cmd_port": 9000,
    "latest_frame": None,
    "latest_telem": {"link": False, "usage": {}},
    "left_pct": 0,
    "right_pct": 0,
    "estop": False,
    "seq": 0,
}

cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def udp_video_listener(listen_port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", listen_port))
    while True:
        data, _ = sock.recvfrom(65535)
        if data.startswith(b"VID:"):
            STATE["latest_frame"] = data[4:]
        elif data.startswith(b"TLM:"):
            try:
                STATE["latest_telem"] = json.loads(data[4:].decode("utf-8"))
            except Exception:
                pass


def udp_command_heartbeat_loop():
    while True:
        STATE["seq"] = (STATE["seq"] + 1) % 256
        flags = 1 if STATE["estop"] else 0
        pkt = CMD_STRUCT.pack(STATE["left_pct"], STATE["right_pct"], flags, STATE["seq"])
        cmd_sock.sendto(pkt, (STATE["rover_ip"], STATE["cmd_port"]))
        time.sleep(0.1)  # 10 Hz combined command + heartbeat


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/video_feed")
async def video_feed():
    async def frame_gen():
        while True:
            frame = STATE["latest_frame"]
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            await asyncio.sleep(0.05)

    return StreamingResponse(frame_gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(ws.receive_json(), timeout=0.1)
                if "left" in msg and "right" in msg:
                    STATE["left_pct"] = int(max(-100, min(100, msg["left"])))
                    STATE["right_pct"] = int(max(-100, min(100, msg["right"])))
                    STATE["estop"] = bool(msg.get("estop", False))
                if "cap_kbps" in msg:
                    cmd_sock.sendto(f"CAP:{float(msg['cap_kbps'])}".encode("ascii"),
                                    (STATE["rover_ip"], STATE["cmd_port"]))
            except asyncio.TimeoutError:
                pass
            await ws.send_json(STATE["latest_telem"])
    except WebSocketDisconnect:
        STATE["left_pct"] = 0
        STATE["right_pct"] = 0


def main():
    parser = argparse.ArgumentParser(description="STARFORGE HW-1 Ground Station")
    parser.add_argument("--rover-ip", default="127.0.0.1", help="Raspberry Pi IP address")
    parser.add_argument("--cmd-port", type=int, default=9000, help="Rover UDP command port")
    parser.add_argument("--video-port", type=int, default=8001, help="Local UDP port for incoming video/telemetry")
    parser.add_argument("--web-port", type=int, default=8000, help="Web HUD HTTP port")
    args = parser.parse_args()

    STATE["rover_ip"] = args.rover_ip
    STATE["cmd_port"] = args.cmd_port

    threading.Thread(target=udp_video_listener, args=(args.video_port,), daemon=True).start()
    threading.Thread(target=udp_command_heartbeat_loop, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=args.web_port, log_level="warning")


if __name__ == "__main__":
    main()
