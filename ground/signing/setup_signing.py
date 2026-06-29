#!/usr/bin/env python3
"""[DEPRECATED] 점대점 MAVLink v2 서명 설정 — 브로드캐스트 전환으로 이전됨.

router/QGC(점대점 host:14551) 구조에서 쓰던 서명 종단점 스크립트였다.
브로드캐스트 RF 매질 전환(P-17~P-20) 이후, 서명은 dahnet 브로드캐스트 세그먼트
안에서 동작해야 하므로 아래로 이전되었다(VSM 서명 종단점 = 지상측, 255/195):

    scripts/setup_signing.py   # FC 서명 강제 토글(on/off/status) — tools 컨테이너에서 실행
    scripts/mavsign.py         # 공유키 파생 + 업링크 서명 적용(모든 지상 도구 공용)

사용:
    docker compose exec tools python scripts/setup_signing.py on      # 무서명 거부(강제)
    docker compose exec tools python scripts/setup_signing.py status  # 강제 상태 진단
    docker compose exec tools python scripts/setup_signing.py off      # 관용(무서명 수용)

설계 배경은 scripts/mavsign.py 의 docstring 및 PROJECT_STATUS.md §9-B 참조.
이 파일은 이력 보존용으로만 남겨둔다(ground/mavlink-router 와 동일).
"""
import sys

print(__doc__)
sys.exit(0)
