#!/usr/bin/env python3
"""브로드캐스트 양방향 링크 헬퍼 — dahnet RF 매질용.

router(fan-out) 제거 후, 지상 도구는 점대점 request/response 대신
  - 다운링크(DOWN_PORT) 브로드캐스트 수신
  - 업링크(UP_PORT) 브로드캐스트 송신 (c2channel 이 air 로 전달)
을 묶어서 사용한다. 기존 mavutil 단일연결 코드(.mav.*_send / recv_match /
wait_heartbeat / target_system)와 거의 동일한 인터페이스를 제공한다.

주의: dahnet 브로드캐스트는 컨테이너 간 전용(P-21/P-22)이므로 이 헬퍼를
쓰는 스크립트는 dahnet 상의 컨테이너(예: tools 서비스)에서 실행해야 한다.
"""
import os
import socket
import sys
from pymavlink import mavutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import mavsign  # 업링크 서명 공유 헬퍼(같은 scripts/ 디렉터리)
except Exception:    # pragma: no cover - 서명 모듈 부재 시 무서명 진행
    mavsign = None

BCAST = os.environ.get("BCAST", "172.28.255.255")
DOWN_PORT = int(os.environ.get("DOWN_PORT", "14550"))
UP_PORT = int(os.environ.get("UP_PORT", "14555"))


class BcastLink:
    def __init__(self, src_sys=255, src_comp=250):
        self.rx = mavutil.mavlink_connection(
            f"udpin:0.0.0.0:{DOWN_PORT}",
            source_system=src_sys, source_component=src_comp)
        self.tx = mavutil.mavlink_connection(
            f"udpout:{BCAST}:{UP_PORT}",
            source_system=src_sys, source_component=src_comp, input=False)
        self.tx.port.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # 업링크 서명: 발신(지상→air) 메시지에 공유키 서명을 붙인다(기본 on).
        # link_id 를 src_comp 로 구분 → 도구별 독립 서명 스트림.
        self.signed = False
        if mavsign is not None:
            try:
                self.signed = mavsign.apply(self.tx, link_id=src_comp)
            except Exception as e:   # 서명 실패해도 링크는 동작(무서명)
                print(f"[bcastlink] 서명 적용 실패(무서명 진행): {e}")
        self.mav = self.tx.mav        # .mav.*_send → 업링크 브로드캐스트로 송신
        self.target_system = 1
        self.target_component = 1

    def recv_match(self, **kw):
        return self.rx.recv_match(**kw)

    def wait_heartbeat(self, timeout=30):
        """비행제어기(sysid 1 / comp 1) 하트비트를 다운링크에서 기다린다.
        (페이로드 comp 100 하트비트와 혼동하지 않도록 comp 1 만 채택.)"""
        import time
        end = time.time() + timeout
        while time.time() < end:
            msg = self.rx.recv_match(type="HEARTBEAT", blocking=True, timeout=2)
            if msg and msg.get_srcSystem() == 1 and msg.get_srcComponent() == 1:
                self.target_system = 1
                self.target_component = 1
                return msg
        return None


def connect(src_sys=255, src_comp=250):
    return BcastLink(src_sys, src_comp)
