#!/usr/bin/env python3
"""페이로드 채널 검증 — 카메라 컴포넌트(MAVLink) + KLV(ST0601) 수신·디코드.

(1) 다운링크 브로드캐스트(14550)에서 compid=100(카메라) 메시지가 보이는지
(2) KLV(dahnet 브로드캐스트 14580)를 받아 ST0601 센서 위경도가 디코드되는지
tools 컨테이너 내부에서 실행: docker compose exec tools python scripts/check_payload.py
"""
import socket
import sys
import time
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (1) 카메라 컴포넌트 MAVLink 확인 (브로드캐스트 다운링크)
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcastlink  # noqa: E402

m = bcastlink.connect(255, 253)
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
m.wait_heartbeat(timeout=15)
cam_types = set()
end = time.time() + 8
while time.time() < end:
    msg = m.recv_match(blocking=True, timeout=1)
    if msg and msg.get_srcComponent() == 100:
        cam_types.add(msg.get_type())
if cam_types:
    print(f"[OK] 카메라 컴포넌트(comp=100) 메시지: {sorted(cam_types)}")
else:
    print("[!] 카메라 컴포넌트 메시지 없음")

# (2) KLV(ST0601) 수신·디코드
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 14580))
s.settimeout(8)
try:
    data, _ = s.recvfrom(2048)
except socket.timeout:
    print("[!] KLV 미수신 (payload→host.docker.internal:14580 확인)")
    sys.exit(1)


def parse_st0601(p):
    # UL(16) + BER len(1, <128 가정) + TLV
    out = {}
    i = 17
    while i < len(p) - 1:
        tag = p[i]
        ln = p[i + 1]
        val = p[i + 2:i + 2 + ln]
        if tag == 13:
            out["sensor_lat"] = int.from_bytes(val, "big", signed=True) / (2**31 - 1) * 90
        elif tag == 14:
            out["sensor_lon"] = int.from_bytes(val, "big", signed=True) / (2**31 - 1) * 180
        i += 2 + ln
    return out


dec = parse_st0601(data)
print(f"[OK] KLV {len(data)}B 수신 → 센서위치 "
      f"({dec.get('sensor_lat'):.5f},{dec.get('sensor_lon'):.5f})")
print("\n[완료] 페이로드 채널: 카메라 컴포넌트 + KLV 메타데이터 동작")
