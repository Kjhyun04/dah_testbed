#!/usr/bin/env python3
"""페이로드 영상 스트림 검증 — UDP 5600에서 RTP 패킷 수신 확인."""
import socket
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 5600))
s.settimeout(5)
n = b = 0
end = time.time() + 5
while time.time() < end:
    try:
        d, _ = s.recvfrom(8192)
        n += 1
        b += len(d)
    except socket.timeout:
        break
if n > 0:
    print(f"[OK] RTP 영상 패킷 {n}개 / {b} bytes (5s) → 영상 스트림 동작")
else:
    print("[!] RTP 패킷 없음 — video 컨테이너/포트(5600) 확인")
    sys.exit(1)
