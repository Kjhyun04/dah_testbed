#!/usr/bin/env python3
# 4G-VIZ — 단순 TCP 포워더 (socat 부재 환경용, air 이미지의 python3 만 사용).
#   용도: UAV-UE netns 안에서 도는 noVNC(:6080)를 호스트로 노출.
#         릴레이 컨테이너는 dahnet 에서 -p 6080:6080 로 떠서, UAV-UE 의 dahnet IP:6080
#         (= netns 안 websockify) 로 양방향 포워딩. WebSocket(노VNC) 도 raw TCP 라 그대로 통과.
#   사용:  python3 tcp_relay.py <listen_port> <remote_host> <remote_port>
import sys, socket, threading

LPORT = int(sys.argv[1]); RHOST = sys.argv[2]; RPORT = int(sys.argv[3])


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client):
    try:
        remote = socket.create_connection((RHOST, RPORT), timeout=5)
    except OSError as e:
        print("[relay] upstream %s:%d 연결 실패: %s" % (RHOST, RPORT, e), flush=True)
        client.close(); return
    threading.Thread(target=pipe, args=(client, remote), daemon=True).start()
    threading.Thread(target=pipe, args=(remote, client), daemon=True).start()


srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', LPORT)); srv.listen(64)
print("[relay] 0.0.0.0:%d -> %s:%d (noVNC 릴레이)" % (LPORT, RHOST, RPORT), flush=True)
while True:
    conn, _ = srv.accept()
    handle(conn)
