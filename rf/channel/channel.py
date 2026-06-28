#!/usr/bin/env python3
"""C2 링크 채널 에뮬레이터 (B) — 브로드캐스트 RF 매질 모델.

브로드캐스트 전환(P-17~P-19):
  air(TCP) ↔ dahnet UDP 브로드캐스트 사이를 잇는 '무선 매질' 허브.
  router(fan-out)를 대체한다 — 송출은 브로드캐스트로, 누구나 수동 수신.

  - 다운링크(air→지상): air 텔레메트리를 BCAST:DOWN_PORT 로 방사.
      → 범위 내 누구나(로그뷰어·페이로드·공격자 컨테이너)가 소켓만 열면 도청.
        실제 RF 수동 도청을 재현(유니캐스트 fan-out의 비현실성 해소).
  - 업링크(지상→air): UP_PORT 로 들어온 명령(gcs_cli/도구/GPS_INPUT)을 air(TCP)로 전달.

  다중링크 failover(B.1)·지연(B.2)·메시지 단위 손실(=재밍) 유지:
  - primary(위성/LTE, 고지연) + secondary(직접RF, 저지연) 가상 링크.
  - active 링크로 전달, 무응답(하트비트 미전달 N초) 시 자동 failover, 회복 시 failback.
  - GPS_INPUT(#232)은 손실·지연 면제 — GPS는 UAV 온보드라 C2와 독립.

재밍 제어(사용자):
  echo 0.9 > /ctrl/jam_primary     # primary 90% 손실 → failover 유발
  echo 0   > /ctrl/jam_primary     # 해제 → failback
  echo 0.9 > /ctrl/jam_secondary   # secondary 도 재밍(둘 다 막으면 통신 두절)
"""
import heapq
import os
import random
import socket
import sys
import threading
import time
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AIR = os.environ.get("AIR", "tcp:172.28.0.10:5760")
BCAST = os.environ.get("BCAST", "172.28.255.255")
DOWN_PORT = int(os.environ.get("DOWN_PORT", "14550"))   # air→지상 다운링크 방사
UP_PORT = int(os.environ.get("UP_PORT", "14555"))       # 지상→air 업링크 수신
FAILOVER_T = float(os.environ.get("FAILOVER_T", "3.0"))
GPS_INPUT = "GPS_INPUT"

LINKS = {
    "primary":   {"ctrl": "/ctrl/jam_primary",   "loss": 0.0,
                  "lat": float(os.environ.get("PRIMARY_LAT_MS", "300")) / 1000.0},
    "secondary": {"ctrl": "/ctrl/jam_secondary", "loss": 0.0,
                  "lat": float(os.environ.get("SECONDARY_LAT_MS", "50")) / 1000.0},
}
S = {"active": "primary", "active_since": time.time(), "last_deliv": time.time(),
     "last_air_rx": time.time()}


def air_watchdog():
    # air 연결이 끊기면(10s 무수신) 프로세스 종료 → restart 정책이 재시작·재연결.
    # (브로드캐스트 전환 후에도 air 는 TCP 종단이므로 끊김 감지 방식 유지)
    while True:
        if time.time() - S["last_air_rx"] > 10:
            print("[c2ch] air 무수신 10s → 재시작(reconnect)", flush=True)
            os._exit(1)
        time.sleep(2)


sendq = []
seq = 0
qlock = threading.Lock()


def watch_ctrl():
    while True:
        for name, lk in LINKS.items():
            try:
                if os.path.exists(lk["ctrl"]):
                    v = max(0.0, min(1.0, float(open(lk["ctrl"]).read().strip() or "0")))
                    lk["loss"] = v
            except Exception:
                pass
        time.sleep(1)


def write_active(to):
    try:
        open("/ctrl/active", "w").write(to)
    except Exception:
        pass


def switch(to):
    S["active"] = to
    S["active_since"] = time.time()
    S["last_deliv"] = time.time()
    write_active(to)
    print(f"[c2ch] === LINK 전환 → {to} ===", flush=True)


def monitor():
    while True:
        now = time.time()
        if S["active"] == "primary" and now - S["last_deliv"] > FAILOVER_T:
            print("[c2ch] primary 무응답 → FAILOVER", flush=True)
            switch("secondary")
        elif (S["active"] == "secondary" and LINKS["primary"]["loss"] < 0.3
              and now - S["active_since"] > 3.0):
            print("[c2ch] primary 회복 → FAILBACK", flush=True)
            switch("primary")
        time.sleep(0.5)


def schedule(send_time, fn):
    """지연 적용: send_time 에 fn() 을 실행(스케줄러 스레드)."""
    global seq
    with qlock:
        heapq.heappush(sendq, (send_time, seq, fn))
        seq += 1


def sender():
    while True:
        item = None
        with qlock:
            if sendq and sendq[0][0] <= time.time():
                item = heapq.heappop(sendq)
        if item:
            try:
                item[2]()
            except Exception:
                pass
        else:
            time.sleep(0.002)


# ── 다운링크 송출 소켓(브로드캐스트) ─────────────────────────────
down_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
down_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)


def emit_down(buf):
    try:
        down_sock.sendto(buf, (BCAST, DOWN_PORT))
    except Exception:
        pass


def relay_down(air):
    """air(TCP) → 지상 브로드캐스트(DOWN_PORT). 손실·지연·failover 적용."""
    while True:
        msg = air.recv_match(blocking=True)
        if msg is None or msg.get_type() == "BAD_DATA":
            continue
        S["last_air_rx"] = time.time()
        t = msg.get_type()
        buf = msg.get_msgbuf()
        # SIMSTATE 면제: GPS 매질(gnss)이 진짜위치를 받는 truth 피드.
        # GPS는 UAV 온보드라 C2와 독립 → C2 재밍·지연에서 면제(즉시 방사).
        if t == "SIMSTATE":
            emit_down(buf)
            continue
        lk = LINKS[S["active"]]
        # 재밍(손실)
        if lk["loss"] > 0 and random.random() < lk["loss"]:
            continue
        # 전달된 하트비트 추적 → failover 판정
        if t == "HEARTBEAT":
            S["last_deliv"] = time.time()
        # 링크 지연 후 방사
        schedule(time.time() + lk["lat"], lambda b=buf: emit_down(b))


def relay_up(up, air):
    """지상 업링크(UP_PORT) → air(TCP). GPS_INPUT 면제, 그 외 손실·지연 적용."""
    while True:
        msg = up.recv_match(blocking=True)
        if msg is None or msg.get_type() == "BAD_DATA":
            continue
        t = msg.get_type()
        buf = msg.get_msgbuf()
        # GPS_INPUT 면제: 손실·지연 없이 즉시 전달
        if t == GPS_INPUT:
            try:
                air.write(buf)
            except Exception:
                pass
            continue
        lk = LINKS[S["active"]]
        if lk["loss"] > 0 and random.random() < lk["loss"]:
            continue
        schedule(time.time() + lk["lat"], lambda b=buf: air.write(b))


print(f"[c2ch] connecting air={AIR} ; down=bcast {BCAST}:{DOWN_PORT} / "
      f"up=udpin:{UP_PORT} ...", flush=True)
air = mavutil.mavlink_connection(AIR)
up = mavutil.mavlink_connection(f"udpin:0.0.0.0:{UP_PORT}")
print(f"[c2ch] 브로드캐스트 매질 가동 — primary(lat {LINKS['primary']['lat']*1000:.0f}ms) / "
      f"secondary(lat {LINKS['secondary']['lat']*1000:.0f}ms), GPS_INPUT 면제", flush=True)

write_active(S["active"])
for fn in (watch_ctrl, monitor, sender, air_watchdog):
    threading.Thread(target=fn, daemon=True).start()
threading.Thread(target=relay_down, args=(air,), daemon=True).start()
relay_up(up, air)
