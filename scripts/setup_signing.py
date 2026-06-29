#!/usr/bin/env python3
"""FC(ArduPilot) MAVLink v2 서명 강제 토글 — 브로드캐스트 적응(업링크 인증).

router/QGC 시절의 점대점 setup_signing(host:14551)을 대체한다. dahnet 브로드캐스트
세그먼트(tools 컨테이너)에서 실행한다. 지상 서명 종단점(=VSM 자리, 255/195)으로서
공유키 SETUP_SIGNING(#256)을 FC에 보내 서명을 켜고/끈다.

서브커맨드:
    on      FC 서명 ON — accept_unsigned off. 무서명 업링크 거부(주입 차단).
            이후 정당 도구(gcs_cli·verify_all·gnss·sdr)는 공유키 서명으로 계속 동작.
    off     FC 서명 OFF(영키 전송) — 무서명도 수용(관용/데모).
            ※ 확실한 리셋은 air 컨테이너 재생성: docker compose up -d --force-recreate air
    status  서명/무서명 명령을 각각 보내 FC 수용 여부를 관측(현재 강제 상태 진단).
    (무인자)  SIGN_ENFORCE env(0/1)로 on/off 자동 선택.

키: SIGNING_PASSPHRASE(모든 컨테이너 공유). 설계 상세는 scripts/mavsign.py.

사용:
    docker compose exec tools python scripts/setup_signing.py on
    docker compose exec tools python scripts/setup_signing.py status
    docker compose exec tools python scripts/setup_signing.py off
"""
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bcastlink  # noqa: E402
import mavsign    # noqa: E402
from pymavlink import mavutil  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EPOCH_2015 = 1420070400   # SETUP_SIGNING.initial_timestamp 기준(UTC), 단위 10us


def _ts():
    return int((time.time() - EPOCH_2015) * 1e5)


def connect():
    """VSM 서명 종단점(255/195)으로 연결. tx 는 (SIGN_OUTGOING=1 이면) 서명 발신."""
    m = bcastlink.connect(255, 195)
    m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                         mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
    print("[sign] 다운링크 하트비트 대기 ...")
    if m.wait_heartbeat(timeout=20) is None:
        print("[!] 하트비트 없음 — air/c2channel 기동 확인")
        sys.exit(1)
    print(f"[sign] 연결 sys={m.target_system} (서명발신={m.signed})")
    return m


def _drain(m, secs=1.0):
    end = time.time() + secs
    while time.time() < end:
        m.recv_match(blocking=False)


def _probe(m, signed):
    """signed=True 면 m(서명) tx, False 면 별도 무서명 tx 로 PARAM_REQUEST_READ 를
    보내고, m.rx 에서 GPS_TYPE PARAM_VALUE 수신 여부를 반환(=FC 수용 여부)."""
    _drain(m)
    if signed:
        m.mav.param_request_read_send(1, 1, b"GPS_TYPE", -1)
    else:
        u = mavutil.mavlink_connection(
            f"udpout:{bcastlink.BCAST}:{bcastlink.UP_PORT}",
            source_system=255, source_component=241, input=False)
        u.port.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        u.mav.param_request_read_send(1, 1, b"GPS_TYPE", -1)
        u.close()
    end = time.time() + 4
    while time.time() < end:
        msg = m.recv_match(type="PARAM_VALUE", blocking=True, timeout=1)
        if msg and msg.param_id.strip("\x00") == "GPS_TYPE":
            return True
    return False


def cmd_on(m):
    key = mavsign.derive_key()
    m.mav.setup_signing_send(m.target_system, m.target_component, key, _ts())
    print("[+] SETUP_SIGNING 전송 (서명 ON) → FC accept_unsigned off (무서명 업링크 거부)")
    time.sleep(1.5)
    ok = _probe(m, signed=True)
    print(f"[sign] 서명 명령 수용: {ok}  (기대 True — 키 일치 시 정상 동작)")
    if not ok:
        print("    [!] 서명 명령이 거부됨 — 컨테이너 간 SIGNING_PASSPHRASE 불일치/시계 확인")


def cmd_off(m):
    m.mav.setup_signing_send(m.target_system, m.target_component, b"\x00" * 32, _ts())
    print("[+] SETUP_SIGNING(영키) 전송 (서명 OFF) — 무서명 수용(관용)")
    print("    확실한 리셋: docker compose up -d --force-recreate air")


def cmd_status(m):
    print("[sign] 강제 상태 진단 — 서명/무서명 명령 응답 비교 ...")
    s = _probe(m, signed=True)
    u = _probe(m, signed=False)
    print(f"    서명 명령 수용   = {s}")
    print(f"    무서명 명령 수용 = {u}")
    if s and not u:
        print("[=] 강제(ENFORCED): 무서명 업링크 거부 중 — 서명만 통과.")
    elif s and u:
        print("[=] 관용(PERMISSIVE): 서명/무서명 모두 수용 — FC 서명 미강제.")
    elif not s and not u:
        print("[!] 둘 다 무응답 — 링크/스트림 문제(c2channel·air 확인).")
    else:
        print("[!] 서명만 거부 — 키 불일치(SIGNING_PASSPHRASE) 의심.")


def main():
    arg = (sys.argv[1].lower() if len(sys.argv) > 1
           else ("on" if mavsign.enforce_default() else "off"))
    if arg not in ("on", "off", "status"):
        print(__doc__)
        return
    m = connect()
    {"on": cmd_on, "off": cmd_off, "status": cmd_status}[arg](m)


if __name__ == "__main__":
    main()
