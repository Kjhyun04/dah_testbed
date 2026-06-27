#!/usr/bin/env python3
"""M0 텔레메트리 점검.

라우터의 UDP 14551 엔드포인트를 통해 HEARTBEAT / 위치 / 자세 텔레메트리가
정상 수신되는지 확인한다. (라우터 UdpEndpoint=Server 이므로 우리가 먼저
패킷을 보내 학습시킨다 → udpout 사용.)

사용:
    pip install pymavlink
    python scripts/check_telemetry.py [conn]
    # 기본 conn = udpout:127.0.0.1:14551
"""
import sys
import time
from pymavlink import mavutil

# Windows 콘솔(cp949) 인코딩 이슈 회피
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONN = sys.argv[1] if len(sys.argv) > 1 else "udpout:127.0.0.1:14551"

print(f"[*] connecting {CONN}")
m = mavutil.mavlink_connection(CONN, source_system=255, source_component=240)

# 라우터(Server 모드)에 우리 존재를 학습시키기 위해 heartbeat 송신
m.mav.heartbeat_send(
    mavutil.mavlink.MAV_TYPE_GCS,
    mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)

print("[*] waiting heartbeat (timeout 30s) ...")
hb = m.wait_heartbeat(timeout=30)
if hb is None:
    print("[!] HEARTBEAT 없음 — air/router 기동 및 포트 매핑 확인")
    sys.exit(1)
print(f"[+] HEARTBEAT  sys={m.target_system} comp={m.target_component} "
      f"type={hb.type} autopilot={hb.autopilot}")

# 실제 GCS처럼 데이터 스트림 요청 (ArduPilot은 요청해야 스트리밍)
m.mav.request_data_stream_send(
    m.target_system, m.target_component,
    mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)  # 5 Hz, start
print("[*] requested data streams (ALL @ 5Hz)")

# 정상 baseline 메시지 몇 종 수신 확인
want = {"GLOBAL_POSITION_INT", "ATTITUDE", "SYS_STATUS", "GPS_RAW_INT", "VFR_HUD"}
seen = {}
deadline = time.time() + 15
while want - set(seen) and time.time() < deadline:
    msg = m.recv_match(blocking=True, timeout=2)
    if msg is None:
        continue
    t = msg.get_type()
    if t in want and t not in seen:
        seen[t] = msg
        print(f"[+] {t}")

missing = want - set(seen)
if missing:
    print(f"[!] 미수신: {sorted(missing)} (스트림 레이트 SR1_* 확인)")
    sys.exit(2)

print("\n[OK] M0 텔레메트리 흐름 정상 — C2/텔레메트리 baseline 확인 완료")
