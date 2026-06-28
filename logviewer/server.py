#!/usr/bin/env python3
"""DAH 웹 로그뷰어 백엔드 — MAVLink·채널 상태를 수집해 /state(JSON)로 제공.

세 채널(GPS·C2·페이로드)의 상태와 이벤트(모드변경·failover·재밍·GPS변화)를
한 화면에서 관측하기 위한 대시보드 서버. 정적 페이지(/)와 상태(/state) 제공.
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pymavlink import mavutil

# 브로드캐스트 전환(P-19): 다운링크 방사를 수동 수신(도청과 동일 경로).
CONN = os.environ.get("CONN", "udpin:0.0.0.0:14550")
CTRL = os.environ.get("CTRL", "/ctrl")
HTML = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "index.html"), encoding="utf-8").read()

state = {
    "drone": {"mode": "-", "armed": False, "lat": 0, "lon": 0, "alt": 0, "hb_hz": 0},
    "gps": {"fix": 0, "sats": 0, "lat": 0, "lon": 0},
    "c2": {"jam_primary": 0.0, "jam_secondary": 0.0, "active": "-"},
    "payload": {"camera": False, "sensor_lat": 0, "sensor_lon": 0},
}
events = []
hb_times = []
prev = {}


def add_event(msg):
    events.append({"t": time.strftime("%H:%M:%S"), "msg": msg})
    del events[:-60]


def changed(key, val, fmt):
    if prev.get(key) != val:
        if key in prev:
            add_event(fmt)
        prev[key] = val


def read_f(p):
    try:
        return float(open(os.path.join(CTRL, p)).read().strip() or 0)
    except Exception:
        return 0.0


def read_s(p):
    try:
        return open(os.path.join(CTRL, p)).read().strip()
    except Exception:
        return "-"


def reader():
    while True:
        try:
            m = mavutil.mavlink_connection(CONN, source_system=255,
                                           source_component=254)
            m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                 mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            m.wait_heartbeat(timeout=20)
            m.mav.request_data_stream_send(
                1, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
            while True:
                msg = m.recv_match(blocking=True, timeout=2)
                if msg is None:
                    continue
                t = msg.get_type()
                if t == "HEARTBEAT" and msg.get_srcSystem() == 1:
                    if msg.get_srcComponent() == 1:
                        hb_times.append(time.time())
                        mode = mavutil.mode_string_v10(msg)
                        armed = bool(msg.base_mode
                                     & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                        changed("mode", mode, f"비행모드 → {mode}")
                        changed("armed", armed, "ARMED" if armed else "DISARMED")
                        state["drone"]["mode"] = mode
                        state["drone"]["armed"] = armed
                    elif msg.get_srcComponent() == 100:
                        if not state["payload"]["camera"]:
                            add_event("페이로드 카메라(comp=100) 감지")
                        state["payload"]["camera"] = True
                elif t == "GLOBAL_POSITION_INT":
                    state["drone"]["lat"] = msg.lat / 1e7
                    state["drone"]["lon"] = msg.lon / 1e7
                    state["drone"]["alt"] = msg.relative_alt / 1000.0
                    state["payload"]["sensor_lat"] = msg.lat / 1e7
                    state["payload"]["sensor_lon"] = msg.lon / 1e7
                elif t == "GPS_RAW_INT":
                    changed("fix", msg.fix_type, f"GPS fix → {msg.fix_type}")
                    state["gps"]["fix"] = msg.fix_type
                    state["gps"]["sats"] = msg.satellites_visible
                    state["gps"]["lat"] = msg.lat / 1e7
                    state["gps"]["lon"] = msg.lon / 1e7
        except Exception as e:
            add_event(f"MAVLink 재연결 ({e})")
            time.sleep(2)


def poller():
    while True:
        now = time.time()
        while hb_times and now - hb_times[0] > 5:
            hb_times.pop(0)
        state["drone"]["hb_hz"] = round(len(hb_times) / 5.0, 2)
        jp, js, active = read_f("jam_primary"), read_f("jam_secondary"), read_s("active")
        changed("jp", jp, f"primary 재밍 = {jp:.2f}")
        changed("js", js, f"secondary 재밍 = {js:.2f}")
        changed("active", active, f"C2 active 링크 → {active}")
        state["c2"]["jam_primary"] = jp
        state["c2"]["jam_secondary"] = js
        state["c2"]["active"] = active
        time.sleep(1)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/state"):
            body = json.dumps({**state, "events": events[-40:]}).encode()
            ctype = "application/json"
        else:
            body = HTML.encode("utf-8")
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


add_event("로그뷰어 시작")
for fn in (reader, poller):
    threading.Thread(target=fn, daemon=True).start()
print("[logviewer] http :8080", flush=True)
ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
