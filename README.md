# DAH 테스트베드 — M0 (baseline)

군용 근사 테스트베드의 **기반 환경**입니다. M0의 목표는 *공격 이전*의 **정상 비행 + 정상 C2/텔레메트리 흐름**을 세우는 것입니다.

> 전체 설계 배경은 `../docs/testbed-overview.html` 참조.

---

## M0 범위

```
[지상]  pymavlink 점검/서명 종단점(=VSM 자리)   QGroundControl
              │  UDP 14551                         │ UDP 14550
              └──────────────┬─────────────────────┘
                       mavlink-router (ground)
                             │  TCP 5760  (← 무선 MAVLink 구간을 M0에선 TCP로 대역)
                       ArduPilot SITL (air, ArduCopter)
```

M0에서 확인하는 것:
1. ArduPilot SITL 기동 + 정상 비행(ARM/이륙 가능 상태)
2. mavlink-router가 SITL ↔ 지상 클라이언트로 MAVLink fan-out
3. QGC / pymavlink가 **HEARTBEAT·위치·자세 텔레메트리** 수신
4. **MAVLink v2 서명 ON** (지상 종단점 ↔ FC end-to-end)
5. **주소체계(sysid/compid)** 확정 — `docs/address-scheme.md`

M0에서 **아직 안 하는 것** (후속 마일스톤):
- STANAG 4586 DLI / CUCS↔VSM 실구현 (#3)
- 위성 다중링크 + failover, 실제 RF 매질(Track S) (#4)
- LOI 에스컬레이션 공격 (#5)
- Gazebo 물리(현재는 SITL 내장 모델)

---

## 사전 요구사항

- **Docker + Docker Compose** (Windows는 **Docker Desktop + WSL2** 권장)
- 호스트에 Python 3 + `pymavlink` (점검 스크립트용): `pip install pymavlink`
- QGroundControl (선택, GUI 확인용)

---

## 실행

```bash
# 1) 빌드 (최초 1회, ArduPilot/mavlink-router 소스 빌드라 시간 소요)
docker compose build

# 2) 기동
docker compose up -d

# 3) 텔레메트리 점검 (호스트에서)
python scripts/check_telemetry.py            # 기본 udpout:127.0.0.1:14551

# 4) MAVLink v2 서명 활성화 (지상 종단점 ↔ FC)
python ground/signing/setup_signing.py

# 5) QGroundControl: UDP 링크로 127.0.0.1:14550 연결

# 종료
docker compose down
```

수용 기준 체크리스트: `docs/m0-validation.md`

---

## ✅ 검증 상태 (2026-06-26 기동 검증 완료)

Docker 빌드·기동·헤드리스 검증을 **실제로 통과**했습니다:

- `docker compose build` — air(ArduCopter SITL)·router 빌드 성공
- `docker compose up -d` — air/router 둘 다 Up, router가 air(172.28.0.10:5760) TCP 접속
- `python scripts/check_telemetry.py` — **HEARTBEAT + ATTITUDE/GLOBAL_POSITION_INT/SYS_STATUS/VFR_HUD/GPS_RAW_INT 수신 → [OK]**
- `python ground/signing/setup_signing.py` — MAVLink v2 서명 활성화 + 검증 [OK]

남은 항목(사용자 GUI 필요): **QGC 연결(UDP 127.0.0.1:14550)**, **ARM/이륙 비행 확인**.

기동 중 해결한 이슈는 `docs/m0-validation.md`의 "해결된 빌드 이슈" 참조.
참고: `air/params/m0-baseline.parm`의 `SR0_*` 스트림 레이트는 다음 air 재빌드 시 반영됨
(현재는 점검 스크립트가 스트림을 직접 요청해 검증; QGC도 자체 요청하므로 무방).

---

## 디렉터리

```
testbed/
├── docker-compose.yml
├── .env.example
├── air/                  # 공중: ArduPilot SITL
│   ├── Dockerfile
│   ├── start-sitl.sh
│   └── params/m0-baseline.parm
├── ground/               # 지상: 라우터 + (VSM 자리)서명
│   ├── mavlink-router/{Dockerfile,main.conf}
│   └── signing/setup_signing.py
├── scripts/check_telemetry.py
└── docs/{address-scheme.md, m0-validation.md}
```
