#!/usr/bin/env python3
"""C2 재밍 효과 측정 — HEARTBEAT 수신율 + GPS fix 유지 여부.

C2 채널의 재밍(손실)을 높였을 때 C2 텔레메트리(하트비트)가 줄고,
GPS(면제)는 유지되는지 확인한다.

사용: python scripts/jam_check.py [seconds]
"""
import sys
import time
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
m = mavutil.mavlink_connection("udpout:127.0.0.1:14551",
                               source_system=255, source_component=252)
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
m.wait_heartbeat(timeout=15)
m.mav.request_data_stream_send(1, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)

hb = 0
gps_fix = None
pos = 0
end = time.time() + DUR
while time.time() < end:
    msg = m.recv_match(blocking=True, timeout=1)
    if msg is None:
        continue
    ty = msg.get_type()
    if ty == "HEARTBEAT" and msg.get_srcSystem() == 1:
        hb += 1
    elif ty == "GPS_RAW_INT":
        gps_fix = msg.fix_type
    elif ty == "GLOBAL_POSITION_INT":
        pos += 1

print(f"{DUR:.0f}s | HEARTBEAT {hb}개 ({hb/DUR:.2f} Hz) | "
      f"위치메시지 {pos}개 | GPS fix={gps_fix}")
