#!/usr/bin/env python3
"""전체 검증 스윕 — 현재 testbed의 누락·미동작 부분을 점검.

연결/텔레메트리/GPS 채널/위치/EKF/C2 양방향/센서health 를 확인하고
PASS/WARN/FAIL 로 요약한다.

사용: python scripts/verify_all.py [conn]
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

results = []


def rec(name, status, detail=""):
    results.append((name, status))
    print(f"[{status:^4}] {name}{(' — ' + detail) if detail else ''}")


m = bcastlink.connect(255, 250)
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
if m.wait_heartbeat(timeout=20) is None:
    rec("연결/HEARTBEAT", "FAIL", "no heartbeat")
    sys.exit(1)
rec("연결/HEARTBEAT", "PASS", f"sys={m.target_system}")

# A) 요청 없이 자동 스트리밍 되는가 (SR0 baked 확인)
t = time.time() + 4
passive = set()
while time.time() < t:
    msg = m.recv_match(blocking=True, timeout=1)
    if msg and msg.get_type() != "BAD_DATA":
        passive.add(msg.get_type())
core = {"ATTITUDE", "GLOBAL_POSITION_INT", "VFR_HUD", "SYS_STATUS"}
if core & passive and len(passive) > 5:
    rec("기본 스트리밍(SR0)", "PASS", f"요청전 {len(passive)}종 자동 수신")
else:
    rec("기본 스트리밍(SR0)", "WARN", f"요청전 {len(passive)}종 — 스트림 요청 필요")

# 스트림 요청 후 수집
m.mav.request_data_stream_send(m.target_system, 1,
                               mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
data = {}
t = time.time() + 6
while time.time() < t:
    msg = m.recv_match(blocking=True, timeout=1)
    if msg:
        data[msg.get_type()] = msg

# B) 핵심 텔레메트리
need = {"ATTITUDE", "GLOBAL_POSITION_INT", "GPS_RAW_INT", "SYS_STATUS",
        "VFR_HUD", "EKF_STATUS_REPORT"}
miss = need - set(data)
rec("핵심 텔레메트리", "PASS" if not miss else "WARN",
    "전부 수신" if not miss else f"누락 {sorted(miss)}")

# C) GPS 채널 fix
g = data.get("GPS_RAW_INT")
if g and g.fix_type >= 3 and g.satellites_visible > 0:
    rec("GPS 채널(fix)", "PASS", f"fix={g.fix_type} sats={g.satellites_visible}")
else:
    rec("GPS 채널(fix)", "FAIL",
        f"fix={getattr(g, 'fix_type', '?')} — gnss 컨테이너 확인")

# D) 위치 추정
p = data.get("GLOBAL_POSITION_INT")
if p and (p.lat != 0 or p.lon != 0):
    rec("위치 추정", "PASS",
        f"{p.lat/1e7:.5f},{p.lon/1e7:.5f} relalt={p.relative_alt/1000:.1f}m")
else:
    rec("위치 추정", "FAIL", "위치 0")

# E) EKF 상태
e = data.get("EKF_STATUS_REPORT")
if e:
    rec("EKF 상태", "PASS",
        f"flags=0x{e.flags:04x} posvar={e.pos_horiz_variance:.2f}")
else:
    rec("EKF 상태", "WARN", "EKF_STATUS_REPORT 없음")

# F) C2 양방향 (param read → value)
m.mav.param_request_read_send(m.target_system, 1, b"GPS_TYPE", -1)
t = time.time() + 4
pv = None
while time.time() < t:
    msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=2)
    if msg and msg.param_id.strip("\x00") == "GPS_TYPE":
        pv = msg.param_value
        break
if pv is not None:
    rec("C2 양방향(param)", "PASS", f"GPS_TYPE={pv:.0f} (14=외부)")
else:
    rec("C2 양방향(param)", "WARN", "PARAM_VALUE 응답 없음")

# G) GPS 센서 health
s = data.get("SYS_STATUS")
if s is not None:
    ok = bool(s.onboard_control_sensors_health & 32)  # MAV_SYS_STATUS_SENSOR_GPS
    rec("GPS 센서 health", "PASS" if ok else "WARN",
        "정상" if ok else "비정상 비트")

# 요약
f = sum(1 for _, st in results if st == "FAIL")
w = sum(1 for _, st in results if st == "WARN")
pcount = len(results) - f - w
print(f"\n=== 요약: {pcount} PASS / {w} WARN / {f} FAIL ===")
sys.exit(1 if f else 0)
