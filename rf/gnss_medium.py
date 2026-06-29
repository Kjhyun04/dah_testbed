#!/usr/bin/env python3
"""GNSS 매질 (Track S, R0) — ArduPilot을 외부 GPS_INPUT로 전환하고
SITL 진짜위치를 GPS로 공급하는 '중립 채널' 컴포넌트.

이 매질은 정상 GPS를 *그대로 전달*하는 인프라다. 공격(스푸핑/재밍)은
이후 R1에서 사용자가 I/Q 채널(A2)에 신호를 주입해 수행한다.

브로드캐스트 전환(P-19/P-20):
  - SIMSTATE(진짜위치)는 다운링크 브로드캐스트(DOWN_PORT)에서 수신.
  - GPS_INPUT(#232)은 업링크 브로드캐스트(UP_PORT)로 송출 → c2channel 이
    면제 전달로 air(FC)에 주입.
  - GPS_SOURCE 소프트웨어 스위치: A1(라이브) 컨테이너와 A2(SDR) 컨테이너가
    동시에 송출하면 GPS 소스가 충돌하므로, GPS_SOURCE!=A1 이면 대기(미송출).

서브커맨드:
    probe   : 현재 GPS 관련 파라미터 이름/값 확인
    setup   : 외부 GPS 모드로 파라미터 설정 + FC 재부팅
              (m0-baseline.parm 가 부팅 시 이미 외부 GPS로 설정하므로 보통 불필요)
    run     : SIMSTATE(진짜위치) → GPS_INPUT 주입 루프 (매질 가동)
    status  : 현재 GPS fix 상태(GPS_RAW_INT) 출력

사용: python rf/gnss_medium.py <probe|setup|run|status>
"""
import hashlib
import os
import socket
import sys
import time

os.environ.setdefault("MAVLINK20", "1")   # 서명은 MAVLink2 전용 → v2 발신 강제
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _sign_tx(tx, link_id):
    """업링크 서명(scripts/mavsign.py 와 동일 규약): SIGNING_PASSPHRASE 의 SHA-256
    공유키로 발신 GPS_INPUT 에 서명한다. SIGN_OUTGOING=0 이면 무서명.
    FC 서명 강제(accept_unsigned off) 시 GPS_INPUT 도 서명돼야 GPS 가 유지된다
    (ArduPilot unsigned 화이트리스트엔 GPS_INPUT 이 없음)."""
    if str(os.environ.get("SIGN_OUTGOING", "1")).strip().lower() in (
            "0", "", "false", "no", "off"):
        return False
    pp = os.environ.get("SIGNING_PASSPHRASE", "dah-m0-shared-secret-change-me")
    key = hashlib.sha256(pp.encode()).digest()
    tx.setup_signing(key, sign_outgoing=True, link_id=int(link_id) & 0xFF)
    return True

CMD = sys.argv[1] if len(sys.argv) > 1 else "probe"

GPS_SOURCE = os.environ.get("GPS_SOURCE", "A1")
BCAST = os.environ.get("BCAST", "172.28.255.255")
DOWN_PORT = int(os.environ.get("DOWN_PORT", "14550"))   # air→지상 다운링크 수신
UP_PORT = int(os.environ.get("UP_PORT", "14555"))       # 지상→air 업링크 송출

GPS_PARAM_CANDIDATES = [
    "GPS_TYPE", "GPS1_TYPE", "GPS_TYPE1",
    "SIM_GPS_DISABLE", "SIM_GPS1_ENABLE", "SIM_GPS_ENABLE",
    "SIM_GPS_TYPE", "SIM_GPS1_TYPE", "EK3_SRC1_POSXY", "AHRS_EKF_TYPE",
]


def connect(src_comp=200):
    """브로드캐스트 양방향 링크: rx(다운링크 수신) + tx(업링크 브로드캐스트 송출)."""
    rx = mavutil.mavlink_connection(f"udpin:0.0.0.0:{DOWN_PORT}",
                                    source_system=255, source_component=src_comp)
    tx = mavutil.mavlink_connection(f"udpout:{BCAST}:{UP_PORT}",
                                    source_system=255, source_component=src_comp,
                                    input=False)
    tx.port.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    tx.target_system = 1
    tx.target_component = 1
    if _sign_tx(tx, src_comp):
        print(f"[gnss] 업링크 서명 ON (comp={src_comp})", flush=True)
    if rx.wait_heartbeat(timeout=20) is None:
        print("[!] HEARTBEAT 없음 (다운링크 브로드캐스트 미수신)"); sys.exit(1)
    return rx, tx


def get_param(rx, tx, name, timeout=3):
    tx.mav.param_request_read_send(1, 1, name.encode(), -1)
    t = time.time() + timeout
    while time.time() < t:
        msg = rx.recv_match(type="PARAM_VALUE", blocking=True, timeout=timeout)
        if msg and msg.param_id.strip("\x00") == name:
            return msg.param_value
    return None


def set_param(tx, name, val, ptype=mavutil.mavlink.MAV_PARAM_TYPE_INT32):
    tx.mav.param_set_send(1, 1, name.encode(), float(val), ptype)
    time.sleep(0.3)


if CMD == "probe":
    rx, tx = connect()
    print("[probe] 현재 GPS 관련 파라미터:")
    for p in GPS_PARAM_CANDIDATES:
        v = get_param(rx, tx, p)
        if v is not None:
            print(f"   {p:<18} = {v}")
    print("\n[probe] 위 값으로 setup의 외부 GPS 파라미터를 확정")

elif CMD == "status":
    rx, tx = connect()
    tx.mav.request_data_stream_send(1, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
    print("[status] 5초간 GPS_RAW_INT 관측 ...")
    end = time.time() + 5
    while time.time() < end:
        msg = rx.recv_match(type="GPS_RAW_INT", blocking=True, timeout=2)
        if msg:
            print(f"   fix={msg.fix_type} sats={msg.satellites_visible} "
                  f"lat={msg.lat/1e7:.6f} lon={msg.lon/1e7:.6f} "
                  f"hdop={msg.eph}")

elif CMD == "setup":
    rx, tx = connect()
    print("[setup] 외부 GPS(GPS_INPUT) 모드로 전환 시도 ...")
    plan = {"SIM_GPS_DISABLE": 1, "SIM_GPS1_ENABLE": 0,
            "GPS_TYPE": 14, "GPS1_TYPE": 14}
    for name, val in plan.items():
        if get_param(rx, tx, name) is not None:
            set_param(tx, name, val)
            print(f"   set {name} = {val}")
    print("[setup] FC 재부팅 ...")
    tx.mav.command_long_send(1, 1,
        mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0,
        1, 0, 0, 0, 0, 0, 0)
    print("[setup] 완료 — 재부팅 후 'run'으로 매질 가동")

elif CMD == "run":
    # GPS 소스 스위치 (P-20): A1(이 컨테이너)이 아니면 송출하지 않고 대기.
    if GPS_SOURCE != "A1":
        print(f"[gnss] 대기 모드 — GPS_SOURCE={GPS_SOURCE} (A1 아님, 패킷 미송출)",
              flush=True)
        while True:
            time.sleep(60)
    rx, tx = connect()
    tx.mav.request_data_stream_send(1, 1, mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
    print("[run] GNSS 매질 가동 — SIMSTATE(진짜위치) → GPS_INPUT 주입 @5Hz "
          f"(업링크 bcast {BCAST}:{UP_PORT})", flush=True)
    print("      (중지하면 FC가 GPS를 잃어야 정상)")
    last_truth = None
    last_alt = 30.0          # GPS_INPUT 고도(MSL,m). 첫 VFR_HUD 전까진 홈 고도로 시작.
    last_send = 0.0
    while True:
        msg = rx.recv_match(blocking=True, timeout=1)
        if msg is not None:
            mt = msg.get_type()
            if mt == "SIMSTATE":
                last_truth = (msg.lat, msg.lng)  # degE7 (truth lat/lng)
            elif mt == "VFR_HUD":
                # 진짜 고도 추종: SIMSTATE엔 고도가 없으므로 EKF/baro 기반 VFR_HUD.alt(MSL,m)을
                # GPS_INPUT 고도로 사용한다. 고정 30m면 상승 시 GPS≠실제로 EKF 불일치 →
                # 고도 페일세이프(LAND) 유발. (baro가 수직 truth라 순환참조 아님.)
                last_alt = msg.alt
        now = time.time()
        if last_truth and (now - last_send >= 0.2):   # 5Hz
            last_send = now
            lat, lon = last_truth
            # GPS 시각 (GPS epoch 1980-01-06). 유효 week/ms를 주어야 GPS health 정상.
            gt = now - 315964800
            week = int(gt // 604800)
            week_ms = int((gt % 604800) * 1000)
            tx.mav.gps_input_send(
                int(now * 1e6), 0,
                0,                       # ignore_flags: 전부 제공
                week_ms, week,           # time_week_ms, time_week
                3,                       # fix_type 3D
                lat, lon, last_alt,      # lat, lon, alt(m) — 실제 고도 추종(VFR_HUD)
                1.0, 1.0,                # hdop, vdop
                0.0, 0.0, 0.0,           # vn, ve, vd
                0.5, 1.0, 1.0,           # speed/horiz/vert accuracy
                14, 0)                   # satellites_visible, yaw

else:
    print(f"[!] 알 수 없는 명령: {CMD}")
