#!/usr/bin/env python3
"""MAVLink v2 서명 활성화 (지상 서명 종단점 ↔ FC, end-to-end).

아키텍처 메모:
  mavlink-router 는 서명을 생성/검증하지 않는 "패스스루" 라우터다.
  따라서 서명은 *종단점* 사이에서만 성립한다:
      [지상 서명 종단점(=VSM 자리)]  <--서명-->  [ArduPilot FC]
  이 스크립트가 지상 서명 종단점 역할을 하며,
    1) 로컬(우리) 송신에 서명을 켜고,
    2) FC 측 서명을 SETUP_SIGNING 메시지로 활성화한다.

사용:
    pip install pymavlink
    python ground/signing/setup_signing.py [conn] [passphrase]
    # 기본 conn = udpout:127.0.0.1:14551
"""
import hashlib
import sys
import time
from pymavlink import mavutil

# Windows 콘솔(cp949) 인코딩 이슈 회피
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONN = sys.argv[1] if len(sys.argv) > 1 else "udpout:127.0.0.1:14551"
PASSPHRASE = (sys.argv[2] if len(sys.argv) > 2
              else "dah-m0-shared-secret-change-me").encode()

# 32바이트 공유 비밀 키 (passphrase → SHA-256)
key = hashlib.sha256(PASSPHRASE).digest()

print(f"[*] connecting {CONN}")
m = mavutil.mavlink_connection(CONN, source_system=255, source_component=195)  # VSM compid

# 라우터(Server)에 학습시키고 FC 식별
m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                     mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
print("[*] waiting heartbeat ...")
if m.wait_heartbeat(timeout=30) is None:
    print("[!] HEARTBEAT 없음 — 링크 확인")
    sys.exit(1)

# 1) 로컬(우리) 서명 활성화
m.setup_signing(key, sign_outgoing=True)
print("[+] local signing enabled")

# 2) FC 측 서명 활성화 — SETUP_SIGNING 전송
#    initial_timestamp 단위: 10us, 기준 2015-01-01 00:00:00 UTC
epoch_2015 = 1420070400
initial_ts = int((time.time() - epoch_2015) * 1e5)
m.mav.setup_signing_send(m.target_system, m.target_component, key, initial_ts)
print(f"[+] SETUP_SIGNING sent → sys={m.target_system} comp={m.target_component}")

# 3) 검증: 서명된 상태로 heartbeat 수신되는지 확인
print("[*] verifying signed link ...")
ok = m.wait_heartbeat(timeout=10)
if ok is None:
    print("[!] 서명 후 HEARTBEAT 미수신 — 키/타임스탬프 확인")
    sys.exit(2)
print("[OK] MAVLink v2 서명 활성화 완료 (지상 종단점 ↔ FC)")
