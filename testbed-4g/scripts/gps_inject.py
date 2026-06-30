#!/usr/bin/env python3
# G2(B) — GPS off-셀룰러 주입기 (점대점, dahnet 경유).
#   SITL 의 SIMSTATE(truth lat/lng) + VFR_HUD(alt) 를 읽어 GPS_INPUT(#232) @5Hz 송신.
#   SITL 은 SIM_GPS_DISABLE=1, GPS_TYPE=14 (외부 GPS) 로 떠 있어야 함.
#   ★이 채널은 dahnet(비셀룰러) — C2(tun_srsue, 셀룰러)와 물리적으로 독립.
#   (참조: 기존 testbed rf/gnss_medium.py 의 GPS_INPUT 구성 재사용)
import sys, time
from pymavlink import mavutil

CONN = sys.argv[1] if len(sys.argv) > 1 else 'udpin:0.0.0.0:14560'
m = mavutil.mavlink_connection(CONN)
print("[GPS] %s — SITL telemetry 대기..." % CONN, flush=True)
if m.wait_heartbeat(timeout=60) is None:
    print("[GPS] ✗ SITL telemetry 없음 (dahnet 경유 연결 확인)"); sys.exit(1)
print("[GPS] ✓ SITL 연결(sys=%d) — GPS_INPUT 주입 시작 @5Hz (dahnet, C2와 독립)" % m.target_system, flush=True)
m.mav.request_data_stream_send(m.target_system, m.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)

# ★10Hz 송신(100ms) — ArduPilot GPS 헬스(GPS_MAX_DELTA_MS=245ms) 여유 확보.
#   수신(drain)과 송신 타이밍 분리 → 지터로 인한 245ms 초과("GPS not healthy") 방지.
last_truth = None; last_alt = 30.0; last_send = 0.0; n = 0
while True:
    while True:                                    # 비블로킹 drain
        msg = m.recv_match(blocking=False)
        if not msg: break
        t = msg.get_type()
        if t == "SIMSTATE":  last_truth = (msg.lat, msg.lng)   # degE7 truth
        elif t == "VFR_HUD": last_alt = msg.alt                # MSL m
    now = time.time()
    if last_truth and now - last_send >= 0.1:                  # 10Hz
        last_send = now
        lat, lon = last_truth
        gt = now - 315964800; week = int(gt // 604800); wms = int((gt % 604800) * 1000)
        m.mav.gps_input_send(int(now * 1e6), 0, 0, wms, week, 3,
                             lat, lon, last_alt, 1.0, 1.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 14, 0)
        n += 1
        if n % 50 == 0:
            print("[GPS] injected %d @10Hz (lat=%.5f alt=%.1f)" % (n, lat / 1e7, last_alt), flush=True)
    time.sleep(0.02)
