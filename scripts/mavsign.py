#!/usr/bin/env python3
"""MAVLink v2 서명 공유 헬퍼 — 브로드캐스트 RF 매질용 (업링크 인증).

설계(2026-06-29, 서명 브로드캐스트 적응 / PROJECT_STATUS §9-B 후속):
  router/QGC 시절의 점대점 setup_signing(host:14551)을 대체한다. 모든 지상
  업링크 송신자(gcs_cli·verify_all·gnss·sdr 등)가 *동일한 공유키*로 발신 메시지에
  서명한다. c2channel 은 원본 바이트(get_msgbuf)를 그대로 중계하므로 서명 트레일러가
  손상 없이 air(FC)까지 전달된다.

토글식 강제(SIGN_ENFORCE):
  - FC(ArduPilot)에 서명이 *켜지면*(scripts/setup_signing.py on) accept_unsigned 가
    off 가 되어 무서명 업링크를 거부한다(주입 차단). ArduPilot 펌웨어의 unsigned
    화이트리스트는 RADIO_STATUS·GPS_RTCM_DATA 뿐이라, GPS_INPUT 포함 모든 업링크가
    서명되어야 한다 → 그래서 gnss/sdr 도 서명한다.
  - FC 서명이 *꺼져 있으면* 서명은 통과만 하고(무시) 무서명도 수용한다. (수신 측에
    signing 미설정이면 mavlink_signature_check 가 통과시키므로 무해.)

방향: 업링크만(지상→air). 다운링크 텔레메트리는 평문(수동 도청 유지) — scope 결정.

키:
  SIGNING_PASSPHRASE (env, 기본 'dah-m0-shared-secret-change-me') → SHA-256 = 32B 키.
  모든 컨테이너가 같은 passphrase 를 공유해야 서명이 일관된다(키 일관 적용).
  → 군용 심화 시나리오: 이 키를 탈취(VSM 장악)하면 유효 서명 명령을 발행할 수 있다.
"""
import hashlib
import os

DEFAULT_PASSPHRASE = "dah-m0-shared-secret-change-me"


def _truthy(v):
    return str(v).strip().lower() not in ("0", "", "false", "no", "off")


def derive_key(passphrase=None):
    """passphrase(또는 SIGNING_PASSPHRASE env) → 32바이트 공유키."""
    p = passphrase if passphrase is not None else os.environ.get(
        "SIGNING_PASSPHRASE", DEFAULT_PASSPHRASE)
    return hashlib.sha256(p.encode()).digest()


def sign_outgoing_enabled():
    """지상 도구가 발신 서명을 붙일지. 기본 True('정당 도구는 항상 서명').
    SIGN_OUTGOING=0 으로 끄면 무서명 발신 → 강제(on) 상태에서 거부되는지 관측 가능."""
    return _truthy(os.environ.get("SIGN_OUTGOING", "1"))


def enforce_default():
    """setup_signing 무인자 실행 시 FC 강제(on/off) 기본값 (SIGN_ENFORCE env)."""
    return _truthy(os.environ.get("SIGN_ENFORCE", "0"))


def ensure_v2(conn):
    """서명은 MAVLink2 전용이므로 연결의 발신 다이얼렉트를 v2 로 보장.
    pymavlink 기본이 v1(MAVLINK20 env 미설정)이면 발신 메시지에 서명이 붙지 않아
    무서명으로 새 나간다 → 강제 모드에서 정당 도구가 거부되는 보안 footgun.
    conn.mav 를 v20 MAVLink 로 교체(srcSystem/comp 보존). v1 파서도 v2 프레임을
    파싱하므로 수신 측 호환성에는 영향 없음."""
    if ".v20." in type(conn.mav).__module__:
        return conn.mav
    from pymavlink.dialects.v20 import ardupilotmega as mav2
    new = mav2.MAVLink(conn, srcSystem=conn.mav.srcSystem,
                       srcComponent=conn.mav.srcComponent)
    new.robust_parsing = getattr(conn.mav, "robust_parsing", True)
    conn.mav = new
    return new


def apply(conn, link_id=0, passphrase=None, sign_outgoing=None):
    """mavutil 연결의 발신에 서명을 적용.

    sign_outgoing=None 이면 env(SIGN_OUTGOING)를 따른다.
    link_id 는 송신자별로 구분(같은 키·다른 스트림 → FC 가 타임스탬프를
    (link_id, sysid, compid) 단위로 추적하므로 송신자 간 재생방지 충돌 방지).
    반환: 실제 서명 발신 여부(bool).
    """
    if sign_outgoing is None:
        sign_outgoing = sign_outgoing_enabled()
    if sign_outgoing:
        ensure_v2(conn)   # 서명이 실제로 붙도록 v2 보장
    key = derive_key(passphrase)
    conn.setup_signing(key, sign_outgoing=sign_outgoing, link_id=int(link_id) & 0xFF)
    return sign_outgoing
