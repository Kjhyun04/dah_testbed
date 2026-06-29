#!/usr/bin/env python3
"""A2.2 브리지 — GNSS-SDR 디코드 위치를 GPS_INPUT으로 FC에 공급.

GNSS-SDR를 I/Q 파일에 대해 실행하고, stdout의
  "Position at ... Lat = X [deg], Long = Y [deg], Height = Z [m]"
를 파싱해 안정 위치(중앙값)를 구한 뒤, 그 위치를 GPS_INPUT(#232)으로
업링크 브로드캐스트(UP_PORT) → c2channel(면제 전달) 경유 FC에 5Hz 공급한다.
(파일 디코드라 정적 위치)

사용: python3 sdr_to_gps.py [conn]
      (기본 udpout:$BCAST:$UP_PORT — 업링크 브로드캐스트)
"""
import os
import re
import socket
import statistics
import subprocess
import sys
import time

os.environ.setdefault("MAVLINK20", "1")   # 서명은 MAVLink2 전용 → v2 발신 강제
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BCAST = os.environ.get("BCAST", "172.28.255.255")
UP_PORT = int(os.environ.get("UP_PORT", "14555"))
CONN = sys.argv[1] if len(sys.argv) > 1 else f"udpout:{BCAST}:{UP_PORT}"
CONFIG = "/opt/gnss-sdr.conf"
RX = re.compile(r"Lat = ([\-\d.]+) \[deg\], Long = ([\-\d.]+) \[deg\], "
                r"Height = ([\-\d.]+)")

LOG = "/data/gnss_decode.log"
print("[sdr2gps] GNSS-SDR 디코드 ...", flush=True)
# run_decode 와 완전히 동일한 shell 호출 (cd /data + > 리다이렉트)
subprocess.run(f"cd /data && gnss-sdr --config_file={CONFIG} > {LOG} 2>&1",
               shell=True)

positions = []
with open(LOG, errors="ignore") as f:
    for line in f:
        mt = RX.search(line)
        if mt:
            positions.append((float(mt.group(1)), float(mt.group(2)),
                              float(mt.group(3))))

if not positions:
    print("[sdr2gps] 위치 디코드 실패 — I/Q/설정 확인")
    sys.exit(1)
print(f"[sdr2gps] 디코드 위치 {len(positions)}개 수집", flush=True)

lat = statistics.median(p[0] for p in positions)
lon = statistics.median(p[1] for p in positions)
alt = statistics.median(p[2] for p in positions)
print(f"[sdr2gps] 디코드 완료: {len(positions)}개 → 중앙값 "
      f"{lat:.6f},{lon:.6f},{alt:.1f}m", flush=True)
print(f"[sdr2gps] GPS_INPUT 공급 시작 (5Hz, {CONN})", flush=True)

m = mavutil.mavlink_connection(CONN, source_system=255, source_component=201,
                               input=False)
# 업링크 브로드캐스트 송출 허용
try:
    m.port.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
except Exception:
    pass

# 업링크 서명(scripts/mavsign.py 규약): FC 서명 강제 시 A2 의 GPS_INPUT 도 서명돼야
# GPS 가 유지된다. SIGN_OUTGOING=0 이면 무서명.
if str(os.environ.get("SIGN_OUTGOING", "1")).strip().lower() not in (
        "0", "", "false", "no", "off"):
    import hashlib
    _pp = os.environ.get("SIGNING_PASSPHRASE", "dah-m0-shared-secret-change-me")
    m.setup_signing(hashlib.sha256(_pp.encode()).digest(),
                    sign_outgoing=True, link_id=201)
    print("[sdr2gps] 업링크 서명 ON (comp=201)", flush=True)

lat_e7, lon_e7 = int(lat * 1e7), int(lon * 1e7)
while True:
    now = time.time()
    gt = now - 315964800
    m.mav.gps_input_send(
        int(now * 1e6), 0, 0,
        int((gt % 604800) * 1000), int(gt // 604800),  # week_ms, week
        3, lat_e7, lon_e7, alt,
        1.0, 1.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 14, 0)
    time.sleep(0.2)
