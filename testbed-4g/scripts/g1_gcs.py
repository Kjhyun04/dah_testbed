#!/usr/bin/env python3
# G1 — GCS over LTE: UAV-UE의 SITL MAVLink을 udpin:14550으로 수신(다운링크) 후
#   명령을 송신해 응답 확인(업링크). 셀룰러 UE-to-UE 경로 위 양방향 C2 증명.
#   실행: pymavlink 있는 이미지에서, GCS-UE(srsue_zmq2) netns 공유로.
import sys, time
from pymavlink import mavutil

conn = sys.argv[1] if len(sys.argv) > 1 else 'udpin:0.0.0.0:14550'
m = mavutil.mavlink_connection(conn)
print("[GCS] listening %s — waiting HEARTBEAT (다운링크)..." % conn, flush=True)

hb = m.wait_heartbeat(timeout=40)
if hb is None:
    print("[GCS] ✗ FAIL: HEARTBEAT 미수신 — 다운링크 불통"); sys.exit(1)
print("[GCS] ✓ DOWNLINK: HEARTBEAT sysid=%d comp=%d type=%d autopilot=%d (셀룰러 경유)" % (
    m.target_system, m.target_component, hb.type, hb.autopilot), flush=True)

# GCS heartbeat 송신(차량이 GCS 주소 인지) + 업링크 명령
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
print("[GCS] sending UPLINK cmd: REQUEST_AUTOPILOT_CAPABILITIES(520)...", flush=True)
m.mav.command_long_send(m.target_system, m.target_component,
    mavutil.mavlink.MAV_CMD_REQUEST_AUTOPILOT_CAPABILITIES, 0, 1, 0,0,0,0,0,0)

t = time.time(); got = None
while time.time() - t < 15:
    msg = m.recv_match(type=['COMMAND_ACK', 'AUTOPILOT_VERSION'], blocking=True, timeout=5)
    if msg:
        got = msg.get_type(); break
if got:
    print("[GCS] ✓ UPLINK: 응답 수신(%s) — 양방향 MAVLink C2-over-LTE 성립 ✅ (G1 통과)" % got, flush=True)
    sys.exit(0)
else:
    print("[GCS] △ 업링크 응답 없음(명령 송신됨). 다운링크는 OK — 부분 통과.", flush=True)
    sys.exit(2)
