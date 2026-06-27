#!/usr/bin/env python3
"""C2 링크 채널 에뮬레이터 (B) — 지상↔UAV 무선 링크 모델.

다중링크 + failover (B.1) + 지연 (B.2):
  - primary  (위성/LTE, 고지연) + secondary (직접RF, 저지연) 두 링크.
  - active 링크로 전달. active 링크가 무응답(하트비트 미전달 N초)이면
    자동 failover → 다른 링크. primary 회복 시 자동 failback.
  - 메시지 단위 손실(=재밍)·지연 적용.
  - GPS_INPUT(#232)은 손실·지연 면제 — GPS는 UAV 온보드라 C2와 독립.

재밍 제어(사용자):
  echo 0.9 > /ctrl/jam_primary     # primary 90% 손실 → failover 유발
  echo 0   > /ctrl/jam_primary     # 해제 → failback
  echo 0.9 > /ctrl/jam_secondary   # secondary 도 재밍(둘 다 막으면 통신 두절)
"""
import heapq
import os
import random
import sys
import threading
import time
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

AIR = os.environ.get("AIR", "tcp:172.28.0.10:5760")
GND_PORT = int(os.environ.get("GND_PORT", "14570"))
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
    # air 연결이 끊기면(10s 무수신) 프로세스 종료 → restart 정책이 재시작·재연결
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


def schedule(send_time, dst, buf):
    global seq
    with qlock:
        heapq.heappush(sendq, (send_time, seq, dst, buf))
        seq += 1


def sender():
    while True:
        item = None
        with qlock:
            if sendq and sendq[0][0] <= time.time():
                item = heapq.heappop(sendq)
        if item:
            try:
                item[2].write(item[3])
            except Exception:
                pass
        else:
            time.sleep(0.002)


def relay(src, dst, exempt_gps, down):
    while True:
        msg = src.recv_match(blocking=True)
        if msg is None or msg.get_type() == "BAD_DATA":
            continue
        if down:
            S["last_air_rx"] = time.time()
        t = msg.get_type()
        buf = msg.get_msgbuf()
        # GPS_INPUT 면제: 손실·지연 없이 즉시 전달
        if exempt_gps and t == GPS_INPUT:
            try:
                dst.write(buf)
            except Exception:
                pass
            continue
        lk = LINKS[S["active"]]
        # 재밍(손실)
        if lk["loss"] > 0 and random.random() < lk["loss"]:
            continue
        # 전달된 하트비트 추적(텔레메트리 방향) → failover 판정
        if down and t == "HEARTBEAT":
            S["last_deliv"] = time.time()
        # 링크 지연 후 전송
        schedule(time.time() + lk["lat"], dst, buf)


print(f"[c2ch] connecting air={AIR}, gnd=udp:{GND_PORT} ...", flush=True)
air = mavutil.mavlink_connection(AIR)
gnd = mavutil.mavlink_connection(f"udpin:0.0.0.0:{GND_PORT}")
print(f"[c2ch] 채널 가동 — primary(lat {LINKS['primary']['lat']*1000:.0f}ms) / "
      f"secondary(lat {LINKS['secondary']['lat']*1000:.0f}ms), GPS_INPUT 면제", flush=True)

write_active(S["active"])
for fn in (watch_ctrl, monitor, sender, air_watchdog):
    threading.Thread(target=fn, daemon=True).start()
threading.Thread(target=relay, args=(air, gnd, False, True), daemon=True).start()
relay(gnd, air, True, False)
