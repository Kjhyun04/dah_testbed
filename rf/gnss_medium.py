#!/usr/bin/env python3
"""GNSS 매질 (Track S, R0) — ArduPilot을 외부 GPS_INPUT로 전환하고
SITL 진짜위치를 GPS로 공급하는 '중립 채널' 컴포넌트.

이 매질은 정상 GPS를 *그대로 전달*하는 인프라다. 공격(스푸핑/재밍)은
이후 R1에서 사용자가 I/Q 채널에 신호를 주입해 수행한다.

서브커맨드:
    probe   : 현재 GPS 관련 파라미터 이름/값 확인
    setup   : 외부 GPS 모드로 파라미터 설정 + FC 재부팅
    run     : SIMSTATE(진짜위치) → GPS_INPUT 주입 루프 (매질 가동)
    status  : 현재 GPS fix 상태(GPS_RAW_INT) 출력

사용: python rf/gnss_medium.py <probe|setup|run|status> [conn]
"""
import sys
import time
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CMD = sys.argv[1] if len(sys.argv) > 1 else "probe"
CONN = sys.argv[2] if len(sys.argv) > 2 else "udpout:127.0.0.1:14551"

GPS_PARAM_CANDIDATES = [
    "GPS_TYPE", "GPS1_TYPE", "GPS_TYPE1",
    "SIM_GPS_DISABLE", "SIM_GPS1_ENABLE", "SIM_GPS_ENABLE",
    "SIM_GPS_TYPE", "SIM_GPS1_TYPE", "EK3_SRC1_POSXY", "AHRS_EKF_TYPE",
]


def connect():
    m = mavutil.mavlink_connection(CONN, source_system=255, source_component=200)
    m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                         mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    if m.wait_heartbeat(timeout=20) is None:
        print("[!] HEARTBEAT 없음"); sys.exit(1)
    return m


def get_param(m, name, timeout=3):
    m.mav.param_request_read_send(m.target_system, 1, name.encode(), -1)
    t = time.time() + timeout
    while time.time() < t:
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=timeout)
        if msg and msg.param_id.strip("\x00") == name:
            return msg.param_value
    return None


def set_param(m, name, val, ptype=mavutil.mavlink.MAV_PARAM_TYPE_INT32):
    m.mav.param_set_send(m.target_system, 1, name.encode(), float(val), ptype)
    time.sleep(0.3)


if CMD == "probe":
    m = connect()
    print(f"[probe] 표적 sys={m.target_system}\n현재 GPS 관련 파라미터:")
    for p in GPS_PARAM_CANDIDATES:
        v = get_param(m, p)
        if v is not None:
            print(f"   {p:<18} = {v}")
    print("\n[probe] 위 값으로 setup의 외부 GPS 파라미터를 확정")

elif CMD == "status":
    m = connect()
    m.mav.request_data_stream_send(m.target_system, 1,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    print("[status] 5초간 GPS_RAW_INT 관측 ...")
    end = time.time() + 5
    while time.time() < end:
        msg = m.recv_match(type="GPS_RAW_INT", blocking=True, timeout=2)
        if msg:
            print(f"   fix={msg.fix_type} sats={msg.satellites_visible} "
                  f"lat={msg.lat/1e7:.6f} lon={msg.lon/1e7:.6f} "
                  f"hdop={msg.eph}")

elif CMD == "setup":
    m = connect()
    print("[setup] 외부 GPS(GPS_INPUT) 모드로 전환 시도 ...")
    # 후보 파라미터를 존재하는 것만 설정 (버전 차이 대응)
    plan = {"SIM_GPS_DISABLE": 1, "SIM_GPS1_ENABLE": 0,
            "GPS_TYPE": 14, "GPS1_TYPE": 14}
    for name, val in plan.items():
        if get_param(m, name) is not None:
            set_param(m, name, val)
            print(f"   set {name} = {val}")
    print("[setup] FC 재부팅 ...")
    m.mav.command_long_send(m.target_system, 1,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0,
        1, 0, 0, 0, 0, 0, 0)
    print("[setup] 완료 — 재부팅 후 'run'으로 매질 가동")

elif CMD == "run":
    m = connect()
    m.mav.request_data_stream_send(m.target_system, 1,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
    print("[run] GNSS 매질 가동 — SIMSTATE(진짜위치) → GPS_INPUT 주입 @5Hz")
    print("      (Ctrl+C 로 중지. 중지하면 FC가 GPS를 잃어야 정상)")
    last_truth = None
    last_send = 0.0
    while True:
        msg = m.recv_match(blocking=True, timeout=1)
        if msg is not None and msg.get_type() == "SIMSTATE":
            last_truth = (msg.lat, msg.lng)  # degE7 (truth)
        now = time.time()
        if last_truth and (now - last_send >= 0.2):   # 5Hz
            last_send = now
            lat, lon = last_truth
            # GPS 시각 (GPS epoch 1980-01-06). 유효 week/ms를 주어야 GPS health 정상.
            gt = now - 315964800
            week = int(gt // 604800)
            week_ms = int((gt % 604800) * 1000)
            m.mav.gps_input_send(
                int(now * 1e6), 0,
                0,                       # ignore_flags: 전부 제공
                week_ms, week,           # time_week_ms, time_week
                3,                       # fix_type 3D
                lat, lon, 30.0,          # lat, lon, alt(m) (R0: 고정고도)
                1.0, 1.0,                # hdop, vdop
                0.0, 0.0, 0.0,           # vn, ve, vd
                0.5, 1.0, 1.0,           # speed/horiz/vert accuracy
                14, 0)                   # satellites_visible, yaw

else:
    if CMD not in ("probe", "setup", "status"):
        print(f"[!] 알 수 없는 명령: {CMD}")
