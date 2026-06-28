#!/usr/bin/env python3
"""SITL 비행 상태 라이브 모니터.

gcs_cli.py 로 ARM / Takeoff 하는 동안 이 스크립트를 띄워두면, 그 명령이 SITL
물리에 반영되는지(armed 비트, 고도, 상승률, throttle)를 다운링크 텔레메트리로
직접 확인할 수 있다.

사용 (tools 컨테이너 내부):
    docker compose exec tools python scripts/monitor_flight.py [seconds]
    # seconds = 20(기본)
"""
import sys
import time
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcastlink  # noqa: E402

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0

m = bcastlink.connect(255, 241)
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
print("[*] 브로드캐스트 연결, heartbeat 대기 ...")
if m.wait_heartbeat(timeout=20) is None:
    print("[!] HEARTBEAT 없음"); sys.exit(1)
m.mav.request_data_stream_send(m.target_system, m.target_component,
                               mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)

armed = mode = alt = climb = thr = None
last = 0.0
end = time.time() + DUR
print(f"[*] {DUR:.0f}초간 모니터링 — 지금 QGC에서 ARM / Takeoff 해보세요\n")
print(f"{'시각':>6} | {'ARMED':^6} | {'MODE':^8} | {'상대고도':>8} | {'상승률':>7} | {'throttle':>8}")
print("-" * 60)
while time.time() < end:
    msg = m.recv_match(blocking=True, timeout=1)
    if msg is None:
        continue
    t = msg.get_type()
    if t == "HEARTBEAT":
        armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        mode = mavutil.mode_string_v10(msg)
    elif t == "GLOBAL_POSITION_INT":
        alt = msg.relative_alt / 1000.0
    elif t == "VFR_HUD":
        climb = msg.climb
        thr = msg.throttle
    now = time.time()
    if now - last >= 1.0:
        last = now
        a = "ARMED" if armed else "disarm"
        print(f"{now % 1000:6.1f} | {a:^6} | {str(mode):^8} | "
              f"{(alt if alt is not None else 0):7.2f}m | "
              f"{(climb if climb is not None else 0):6.2f} | "
              f"{(thr if thr is not None else 0):7}%")
print("\n[완료] 위 표에서 ARMED 전환·고도 상승·throttle 증가가 보이면 SITL 연동 확인")
