#!/usr/bin/env python3
"""SITL이 실제로 내보내는 MAVLink 메시지·레이트·대역폭 측정.

다운링크 브로드캐스트(14550)로 흘러오는 텔레메트리를 일정 시간 수집해 메시지
종류별 빈도(Hz)·바이트·플레인 분류를 산출한다. 3-plane 정상 트래픽 명세(#2)의
*측정 기반* 근거로 사용한다.

사용 (tools 컨테이너 내부):
    docker compose exec tools python scripts/measure_streams.py [seconds] [--request]
    # seconds = 15(기본)
    # --request : 측정 클라이언트가 직접 ALL 스트림을 요청(레이트 상한 관찰용)
"""
import sys
import time
from collections import defaultdict
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcastlink  # noqa: E402

args = [a for a in sys.argv[1:] if a != "--request"]
REQUEST = "--request" in sys.argv
DUR = float(args[0]) if len(args) > 0 else 15.0

# 플레인 분류 (C2 / 텔레메트리 / 페이로드)
C2 = {"COMMAND_LONG", "COMMAND_INT", "COMMAND_ACK", "SET_MODE",
      "MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_COUNT", "MISSION_ITEM",
      "MISSION_ITEM_INT", "MISSION_ACK", "MISSION_CURRENT",
      "PARAM_REQUEST_LIST", "PARAM_REQUEST_READ", "PARAM_VALUE", "PARAM_SET",
      "REQUEST_DATA_STREAM", "MANUAL_CONTROL", "RC_CHANNELS_OVERRIDE"}
PAYLOAD = {"CAMERA_IMAGE_CAPTURED", "CAMERA_INFORMATION", "CAMERA_SETTINGS",
           "GIMBAL_MANAGER_STATUS", "GIMBAL_DEVICE_ATTITUDE_STATUS",
           "VIDEO_STREAM_INFORMATION"}


def plane(t):
    if t in C2:
        return "C2"
    if t in PAYLOAD:
        return "PAYLOAD"
    return "TELEMETRY"


m = bcastlink.connect(255, 242)
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
print("[*] 브로드캐스트 연결, heartbeat 대기 ...")
if m.wait_heartbeat(timeout=20) is None:
    print("[!] HEARTBEAT 없음"); sys.exit(1)

if REQUEST:
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
    print("[*] --request: ALL @ 10Hz 요청")

print(f"[*] {DUR:.0f}초 측정 시작 ...\n")
count = defaultdict(int)
nbytes = defaultdict(int)
start = time.time()
end = start + DUR
while time.time() < end:
    msg = m.recv_match(blocking=True, timeout=1)
    if msg is None:
        continue
    t = msg.get_type()
    if t == "BAD_DATA":
        continue
    count[t] += 1
    try:
        nbytes[t] += len(msg.get_msgbuf())
    except Exception:
        pass
elapsed = time.time() - start

if not count:
    print("[!] 수신 메시지 없음 — QGC 연결/스트림 요청 상태 확인 (--request 로 재시도)")
    sys.exit(2)

# 출력
rows = sorted(count.items(), key=lambda kv: -kv[1])
total_msgs = sum(count.values())
total_bytes = sum(nbytes.values())
print(f"측정시간 {elapsed:.1f}s | 총 {total_msgs} msgs | "
      f"{total_bytes} bytes | 평균 {total_bytes/elapsed:.0f} B/s "
      f"({total_bytes*8/elapsed/1000:.1f} kbit/s)\n")
print(f"{'MESSAGE':<26} {'PLANE':<10} {'count':>6} {'Hz':>7} {'B/s':>7}")
print("-" * 62)
for t, c in rows:
    print(f"{t:<26} {plane(t):<10} {c:>6} {c/elapsed:>7.2f} {nbytes[t]/elapsed:>7.0f}")

# 플레인별 합계
print("-" * 62)
pl = defaultdict(lambda: [0, 0])
for t, c in count.items():
    pl[plane(t)][0] += c
    pl[plane(t)][1] += nbytes[t]
for p in ("C2", "TELEMETRY", "PAYLOAD"):
    c, b = pl[p]
    print(f"{p:<26} {'':<10} {c:>6} {c/elapsed:>7.2f} {b/elapsed:>7.0f}")
print("\n[완료] 이 측정값을 3-plane 명세의 기준선으로 사용")
