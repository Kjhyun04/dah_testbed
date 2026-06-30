#!/usr/bin/env python3
# UE-to-UE UDP 전송 검증 (MAVLink 전송 경로). ICMP 가 아닌 실제 UDP 14550 도달 확인.
#   수신:  python3 udp_test.py rx <timeout_s>
#   송신:  python3 udp_test.py tx <src_ip> <dst_ip>
import socket, sys, time

role = sys.argv[1]
if role == "rx":
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 14550))
    s.settimeout(float(sys.argv[2]))
    try:
        d, a = s.recvfrom(2048)
        print("RECEIVED %d bytes from %s  payload=%r" % (len(d), a[0], d[:40]))
    except Exception as e:
        print("NO-UDP:", e)
else:  # tx
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((sys.argv[2], 0))                       # tun_srsue 소스로 송출(셀룰러 경유)
    msg = bytes([0xFD, 0x09, 0, 0, 0, 1, 1, 0, 0, 0]) + b"MAVLINK-C2-TEST"  # MAVLink v2 magic 0xFD
    for _ in range(6):
        s.sendto(msg, (sys.argv[3], 14550)); time.sleep(0.4)
    print("SENT 6 datagrams to %s:14550" % sys.argv[3])
