#!/usr/bin/env python3
"""페이로드 컴포넌트 (C) — UAV 온보드 카메라/짐벌 + KLV 메타데이터.

MAVLink 카메라 컴포넌트(sysid 1 / compid 100=CAMERA)로 등록되어:
  - HEARTBEAT(MAV_TYPE_CAMERA), GIMBAL_DEVICE_ATTITUDE_STATUS, VIDEO_STREAM_INFORMATION 방출
  - 카메라/짐벌 명령(COMMAND_LONG → compid 100)에 ACK
  - FC 위치(GLOBAL_POSITION_INT)를 읽어 **MISB ST0601 KLV** 메타데이터 생성·송신(UDP)

KLV는 페이로드 다운링크의 메타데이터 채널(영상에 동기). 사용자가 KLV의 센서 위치를
스푸핑하면 GPS 스푸핑과 교차연계되어 상관탐지를 회피하는 공격면이 된다.
"""
import os
import socket
import sys
import threading
import time
from pymavlink import mavutil

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONN = os.environ.get("CONN", "udpout:172.28.0.20:14553")
KLV_DEST = os.environ.get("KLV_DEST", "host.docker.internal:14580")
khost, kport = KLV_DEST.split(":")
kport = int(kport)
ksock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

pos = {"lat": 37.5665, "lon": 126.978, "hdg": 0.0}

ST0601_UL = bytes.fromhex("060e2b34020b01010e01030101000000")  # 16-byte UL key


def encode_st0601(ts_us, hdg_deg, lat, lon):
    """최소 ST0601 KLV: 타임스탬프(2)·플랫폼방위(5)·센서위경도(13,14)·체크섬(1)."""
    items = b""
    items += bytes([2, 8]) + (ts_us & ((1 << 64) - 1)).to_bytes(8, "big")
    items += bytes([5, 2]) + (int(hdg_deg / 360 * 65535) & 0xFFFF).to_bytes(2, "big")
    items += bytes([13, 4]) + (int(lat / 90 * (2**31 - 1)) & 0xFFFFFFFF).to_bytes(4, "big")
    items += bytes([14, 4]) + (int(lon / 180 * (2**31 - 1)) & 0xFFFFFFFF).to_bytes(4, "big")
    body = items + bytes([1, 2])          # 체크섬 tag(1) + len(2)
    length = len(body) + 2                 # + 체크섬 값 2바이트
    packet = ST0601_UL + bytes([length]) + body
    bcc = 0
    for i, b in enumerate(packet):         # MISB 16-bit 체크섬
        bcc = (bcc + (b << (8 * ((i + 1) % 2)))) & 0xFFFF
    return packet + bcc.to_bytes(2, "big")


m = mavutil.mavlink_connection(CONN, source_system=1, source_component=100)
print(f"[payload] 카메라 컴포넌트(comp=100) 연결 {CONN}, KLV→{KLV_DEST}", flush=True)


def reader():
    while True:
        msg = m.recv_match(blocking=True)
        if msg is None:
            continue
        t = msg.get_type()
        if t == "GLOBAL_POSITION_INT":
            pos["lat"] = msg.lat / 1e7
            pos["lon"] = msg.lon / 1e7
            pos["hdg"] = msg.hdg / 100.0
        elif t == "COMMAND_LONG" and getattr(msg, "target_component", 0) == 100:
            m.mav.command_ack_send(msg.command,
                                   mavutil.mavlink.MAV_RESULT_ACCEPTED)
            print(f"[payload] 카메라/짐벌 명령 {msg.command} ACK", flush=True)


threading.Thread(target=reader, daemon=True).start()

n = 0
while True:
    now = time.time()
    # 카메라 컴포넌트 생존
    m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_CAMERA,
                         mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    # 짐벌 자세(아래로 조준 예시 q)
    try:
        m.mav.gimbal_device_attitude_status_send(
            0, 0, int(now * 1000) % 4294967296, 0,
            [0.707, 0.0, 0.707, 0.0], 0.0, 0.0, 0.0, 0)
    except Exception:
        pass
    # KLV (ST0601) 송신 — 센서 위치 = FC 위치
    klv = encode_st0601(int(now * 1e6), pos["hdg"], pos["lat"], pos["lon"])
    try:
        ksock.sendto(klv, (khost, kport))
    except Exception:
        pass
    if n % 5 == 0:
        print(f"[payload] KLV 송신 sensor=({pos['lat']:.5f},{pos['lon']:.5f}) "
              f"{len(klv)}B", flush=True)
    n += 1
    time.sleep(1)
