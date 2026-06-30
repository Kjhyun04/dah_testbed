#!/usr/bin/env python3
# G2(A) — 폐루프 비행: GCS가 셀룰러 C2(MAVLink)로 arm→takeoff→land 제어, 고도 추종 관측.
#   실행: pymavlink 이미지에서 GCS-UE(srsue_zmq2) netns 공유로.
import sys, time
from pymavlink import mavutil

CONN = sys.argv[1] if len(sys.argv) > 1 else 'udpin:0.0.0.0:14550'
ALT = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
m = mavutil.mavlink_connection(CONN)

def hb(): m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
def relalt(t=2):
    g = m.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=t)
    return (g.relative_alt / 1000.0) if g else None
def armed():
    h = m.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
    return bool(h and (h.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED))

print("[G2] %s — waiting heartbeat..." % CONN, flush=True)
if m.wait_heartbeat(timeout=40) is None: print("[G2] ✗ no heartbeat"); sys.exit(1)
TS, TC = m.target_system, m.target_component
print("[G2] vehicle sys=%d (셀룰러 C2 연결)" % TS, flush=True)
m.mav.request_data_stream_send(TS, TC, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)

# 1) GPS/EKF armable 대기 (GLOBAL_POSITION_INT 유효좌표 = GPS/EKF OK 프록시)
print("[G2] GPS/EKF 준비 대기(최대 120s)...", flush=True)
ok = False; t = time.time()
while time.time() - t < 120:
    hb()
    g = m.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=2)
    if g and g.lat != 0: ok = True; break
if not ok: print("[G2] ✗ GPS/EKF 미준비"); sys.exit(2)
print("[G2] ✓ GPS/EKF 준비 (lat=%.5f)" % (g.lat / 1e7), flush=True)

# 2) GUIDED
print("[G2] set mode GUIDED", flush=True)
m.set_mode_apm('GUIDED'); time.sleep(1.5)

# 3) ARM — 외부GPS health(10Hz 지속)가 채워질 때까지 넉넉히 재시도(최대 ~48s)
print("[G2] ARM (GPS health 안정화까지 재시도)...", flush=True)
a = False
for _ in range(8):
    m.mav.command_long_send(TS, TC, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1,0,0,0,0,0,0)
    t = time.time()
    while time.time() - t < 6:
        hb()
        if armed(): a = True; break
    if a: break
if not a: print("[G2] ✗ ARM 실패 (GPS health 미충족 가능)"); sys.exit(3)
print("[G2] ✓ ARMED", flush=True)

# 4) TAKEOFF
print("[G2] TAKEOFF %.0fm..." % ALT, flush=True)
m.mav.command_long_send(TS, TC, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0,0,0,0,0,0, ALT)
t = time.time(); peak = 0.0
while time.time() - t < 45:
    hb()
    al = relalt()
    if al is not None:
        peak = max(peak, al)
        if al >= ALT * 0.9: break
print("[G2] climb peak=%.1fm (target %.0f)" % (peak, ALT), flush=True)
took_off = peak >= ALT * 0.6

# 5) LAND
print("[G2] LAND...", flush=True)
m.mav.command_long_send(TS, TC, mavutil.mavlink.MAV_CMD_NAV_LAND, 0, 0,0,0,0,0,0,0)
t = time.time(); landed = False
while time.time() - t < 90:
    hb()
    if not armed(): landed = True; break
print("[G2] landed/disarmed=%s" % landed, flush=True)

if took_off and landed:
    print("[G2] ✅ 폐루프 완주(arm→takeoff %.1fm→land→disarm) — 셀룰러 C2로 비행 (G2-A 통과)" % peak); sys.exit(0)
elif took_off:
    print("[G2] △ 이륙은 됨(%.1fm), 착륙 확인 타임아웃" % peak); sys.exit(4)
else:
    print("[G2] ✗ 이륙 실패(peak %.1fm)" % peak); sys.exit(5)
