# DAH 테스트베드 (v0, as-built)

UAV/UGV · 위성망 **네트워크 공방전** 테스트베드. 실제 군용 무인기 통제 구조를
오픈소스로 근사한 가상 환경에서, 지상↔드론 사이 **무선 채널들**(GPS·C2/텔레메트리·페이로드)을
모델링하고 그 위에서 **재밍·스푸핑 등 공격을 직접 실습**한다.

> **역할 경계:** 이 저장소는 *공격당할 인프라/환경*과 *관측·검증 도구*만 제공한다.
> 공격(재밍/스푸핑/주입) 실행은 사용자가 직접 채널에 가한다.
>
> 전체 현황·설계 이력·이슈는 [`PROJECT_STATUS.md`](PROJECT_STATUS.md) 참조.

---

## 1. 아키텍처

**브로드캐스트 RF 매질 구조** — 실제 RF처럼 다운링크를 공중 방사(브로드캐스트)하여
범위 내 누구나 수동 도청할 수 있다. `router`(fan-out)는 제거되고 `c2channel`이
air(TCP)와 dahnet 브로드캐스트를 잇는 무선 매질 허브 역할을 한다. QGC 대신
`tools` 컨테이너의 `gcs_cli.py`로 기체를 제어한다. 비행역학·카메라는 **air 컨테이너에
통합된 Gazebo Harmonic**(물리엔진)이 담당하고, GUI는 브라우저(noVNC :6080)로 관측한다.

```
 호스트(Windows + Docker Desktop)
  브라우저 ─http8080→ logviewer   브라우저 ─http6080→ air(Gazebo GUI)   영상 ←udp5600─ air(Gazebo cam)
 ───────────────────────── Docker network dahnet 172.28.0.0/16 ─────────────────────
  dah-air(.10) ─tcp5760→ dah-c2channel(.50)   [채널 B 매질: 재밍 + failover + 지연]
   ArduPilot SITL + Gazebo       │  다운링크 방사 → 172.28.255.255:14550 (누구나 수동 도청)
   (JSON FDM localhost 9002/3)   │  업링크 수신   ← 172.28.255.255:14555 → air
   ── dahnet 브로드캐스트 세그먼트 (다운 14550 / 업 14555 / KLV 14580) ──────────────
     ├ dah-gnss(.30)      GPS 채널 A1: SIMSTATE→GPS_INPUT(업링크, 재밍 면제)
     ├ dah-sdr(.40)       GPS 채널 A2(실제 I/Q, profile iq)
     ├ dah-payload(.60)   카메라/짐벌(comp=100) + KLV(ST0601) 브로드캐스트
     ├ dah-logviewer(.80) 다운링크 수동 수신 대시보드(:8080)
     └ dah-tools(.90)     gcs_cli.py(제어) + scripts/(검증)  ← QGC·호스트 스크립트 대체
```

> **브로드캐스트 전환(P-17~P-20, P-26)**: 유니캐스트 fan-out은 공격자가 router에
> 등록돼야 수신 가능해 실제 RF 수동 도청과 달랐다. 이제 공격자 컨테이너가 소켓만
> 열면(`udpin:0.0.0.0:14550`) 즉시 다운링크를 도청한다. dahnet 브리지 브로드캐스트는
> **컨테이너 간 전용**(호스트로는 전달 안 됨, P-21/P-22)이라 진단·제어도 `tools`
> 컨테이너에서 실행한다.

**3개 물리 무선 채널** (각 독립, 사용자가 직접 공격):

| 채널 | 경로 | 컨테이너 | 사용자 공격면 |
|---|---|---|---|
| **A — GPS** | 위성→드론 | `gnss`(A1) / `sdr`(A2) | 가짜 좌표 I/Q 주입 = 스푸핑, 잡음 = 재밍 |
| **B — C2/텔레** | 지상↔드론 | `c2channel` | 손실↑ = 재밍 → 자동 failover |
| **C — 페이로드** | 드론→지상 | `payload` + air(Gazebo 카메라) | KLV 센서위치 스푸핑·영상 가로채기·카메라 탈취 |

---

## 2. 사전 요구사항

- **Docker + Docker Compose** (Windows는 **Docker Desktop + WSL2** 권장)
- 진단·제어는 `tools` 컨테이너 안에서 실행하므로 호스트 Python은 필수 아님
  (호스트에서 영상만 보려면 `check_video.py`용 Python 3 정도).

> 최초 빌드는 ArduPilot SITL·**Gazebo Harmonic + ardupilot_gazebo**·GNSS-SDR·GStreamer를
> 소스/패키지로 받아 빌드하므로 시간이 걸린다(수십 분·수 GB 가능). air 컨테이너가 가장 무겁다.
> GPU 미통과 환경(Windows/Docker Desktop)에선 Gazebo가 **소프트웨어 렌더링**(LIBGL_ALWAYS_SOFTWARE)
> 으로 동작 — 카메라 센서 부하가 클 수 있다. GUI 없이 돌리려면 `GZ_HEADLESS=1`.
>
> QGroundControl은 더 이상 기본 제어 경로가 아니다(브로드캐스트 전환으로 router/QGC
> 제거). 기체 제어는 `gcs_cli.py`(아래 §3·§5)로 한다.

---

## 3. 실행 (전체 흐름)

```bash
cd dah/testbed

# 0) 환경 변수 준비 (선택) — 서명 비밀·빌드 태그 등
cp .env.example .env        # 필요 시 SIGNING_PASSPHRASE 등 수정

# 1) 빌드 (최초 1회)
docker compose build

# 2) 기동 — 6개 서비스(air·c2channel·gnss·payload·logviewer·tools)
#    (영상원은 air의 Gazebo 카메라. test패턴 폴백이 필요하면 --profile testvid)
docker compose up -d

# 3) 검증 (tools 컨테이너 안에서, 아래 §4)
docker compose exec tools python scripts/verify_all.py   # 7 PASS / 1 WARN 기대

# 4) 기체 제어 (QGC 대체 — gcs_cli)
docker compose exec tools python gcs_cli.py status
docker compose exec tools python gcs_cli.py mode GUIDED
docker compose exec tools python gcs_cli.py arm
docker compose exec tools python gcs_cli.py takeoff 10

# 5) 관측
#    브라우저: http://localhost:8080         (로그뷰어 대시보드)
#    브라우저: http://localhost:6080/vnc.html (Gazebo GUI — 3D 물리 비행 관측, P-23)
#    호스트 UDP 5600                          (Gazebo 카메라 H.264 RTP 영상, P-25)

# 6) 공격 (사용자 직접, 아래 §5)

# 종료
docker compose down
```

`.env`를 만들지 않아도 `.env.example`의 기본값으로 동작한다.
`ARDUPILOT_TAG=Rover-4.5`(+ `air/Dockerfile`의 `./waf rover`)로 바꾸면 UGV 변형.

### MAVLink v2 업링크 서명 (선택 — 토글식 강제)

지상→air **업링크 명령 인증**. 모든 지상 도구(`gcs_cli`·`verify_all`·`gnss`·`sdr`)는
공유키(`SIGNING_PASSPHRASE`)로 발신을 **항상 서명**한다. FC 강제는 런타임에 토글한다.
`c2channel`은 원본 바이트를 그대로 중계하므로 서명이 손상 없이 FC까지 전달된다.

```bash
# 강제 ON — FC 가 무서명 업링크를 거부(주입 차단). 정당 도구는 서명으로 계속 동작.
docker compose exec tools python scripts/setup_signing.py on

# 현재 강제 상태 진단 — 서명/무서명 명령 응답 비교(ENFORCED/PERMISSIVE 판정)
docker compose exec tools python scripts/setup_signing.py status

# 무서명 주입이 거부되는지 직접 관측 — 서명 끄고 명령 시도(강제 ON 상태에서)
docker compose exec tools -e SIGN_OUTGOING=0 python gcs_cli.py arm   # ACK 미수신 = 거부

# 강제 OFF(관용) — 무서명도 수용. 확실한 리셋은 air 재생성:
docker compose exec tools python scripts/setup_signing.py off
#   docker compose up -d --force-recreate air
```

> 키를 탈취(VSM 장악)하면 유효 서명 명령을 발행할 수 있다 — 군용 심화(LOI 단계 탈취)의
> 출발점. GPS 스푸핑(A2)은 RF 계층에서 일어나 C2 서명을 **우회**한다(설계 의도).
> 점대점 시절의 `ground/signing/setup_signing.py`는 이전됨(이력 보존).

---

## 4. 검증 스크립트 (`scripts/`)

MAVLink 기반 스크립트는 **`tools` 컨테이너 안에서** 실행한다(브로드캐스트 세그먼트는
컨테이너 전용). 다운링크(14550) 수신 + 업링크(14555) 송신을 `scripts/bcastlink.py`
헬퍼가 묶어 처리한다. `check_video.py`만 호스트에서 실행한다(영상은 호스트:5600로 전달).

| 스크립트 | 용도 | 사용 |
|---|---|---|
| `verify_all.py` | 연결·텔레·GPS·위치·EKF·C2 양방향 종합 점검 (PASS/WARN/FAIL) | `docker compose exec tools python scripts/verify_all.py` |
| `check_telemetry.py` | HEARTBEAT/위치/자세 텔레메트리 수신 확인 | `docker compose exec tools python scripts/check_telemetry.py` |
| `measure_streams.py` | 메시지 종류별 빈도·대역폭 측정(3-plane 분류) | `docker compose exec tools python scripts/measure_streams.py [sec] [--request]` |
| `monitor_flight.py` | ARM/이륙 시 armed·고도·상승률 라이브 모니터 | `docker compose exec tools python scripts/monitor_flight.py [sec]` |
| `jam_check.py` | C2 재밍 시 하트비트 수신율 ↓ / GPS 유지 확인 | `docker compose exec tools python scripts/jam_check.py [sec]` |
| `check_payload.py` | 카메라(comp=100) MAVLink + KLV(ST0601) 디코드 | `docker compose exec tools python scripts/check_payload.py` |
| `check_video.py` | UDP 5600에서 RTP 영상 패킷 수신 확인 | `python scripts/check_video.py` (호스트) |
| `gcs_cli.py` | QGC 대체 제어(status/arm/disarm/takeoff/mode/rtl/land) | `docker compose exec tools python gcs_cli.py <cmd>` |
| `setup_signing.py` | MAVLink v2 업링크 서명 강제 토글(on/off/status) | `docker compose exec tools python scripts/setup_signing.py on` |

---

## 5. 공격 실습 (사용자가 직접)

채널은 정상 신호를 전달하는 중립 인프라다. 공격은 사용자가 채널에 신호를 주입하거나
재밍 노브를 올려서 가한다. 효과는 로그뷰어(`:8080`)와 검증 스크립트로 관측한다.

### 다운링크 수동 도청 (수신기만 있으면 됨)

브로드캐스트 전환의 핵심: 공격자 컨테이너가 소켓만 열면 다운링크 텔레메트리를
수동 도청한다(router 등록 불필요). dahnet 상의 임의 컨테이너에서:

```bash
docker compose exec tools python -c "from pymavlink import mavutil; \
m=mavutil.mavlink_connection('udpin:0.0.0.0:14550'); \
[print(m.recv_match(blocking=True).get_type()) for _ in range(20)]"
```

### B — C2 링크 재밍 → 자동 failover

```bash
echo 0.95 > rf/channel/ctrl/jam_primary     # primary 강재밍 → secondary로 failover
echo 0    > rf/channel/ctrl/jam_primary     # 해제 → primary로 failback
echo 0.95 > rf/channel/ctrl/jam_secondary   # 둘 다 막으면 통신 두절
docker compose exec tools python scripts/jam_check.py    # 효과 측정(GPS는 면제 유지)
```

### A — GPS 스푸핑 (실제 I/Q, A2 모드)

A1(라이브)과 A2(I/Q)는 같은 GPS 소스라 **동시 가동 금지**.

```bash
docker compose stop gnss                                      # A1 중지 (또는 GPS_SOURCE=A2 로 idle)
IQ_LAT=37.70 IQ_LON=127.10 docker compose --profile iq up -d sdr   # 가짜 좌표 I/Q 주입
# FC GPS가 IQ_LAT/IQ_LON으로 끌려가는지 verify_all / 로그뷰어로 확인
```

상세는 [`rf/README.md`](rf/README.md) (채널 A/B), [`payload/README.md`](payload/README.md) (채널 C) 참조.

---

## 6. 네트워크 / 포트 / 주소체계

**컨테이너 IP** (`dahnet` 172.28.0.0/16): air `.10` · gnss `.30` · sdr `.40` ·
c2channel `.50` · payload `.60` · video `.70`(폴백 profile testvid) · logviewer `.80` · tools `.90`
(router `.20`는 제거됨)

**dahnet 브로드캐스트 포트** (컨테이너 전용, `172.28.255.255`):

| 포트 | 방향 | 용도 |
|---|---|---|
| `14550/udp` | 다운링크(air→지상) | 텔레메트리 방사 — 누구나 수동 수신/도청 |
| `14555/udp` | 업링크(지상→air) | 제어 명령 + GPS_INPUT → c2channel → air |
| `14580/udp` | 다운링크 | KLV(ST0601) 브로드캐스트 |

**호스트 노출 포트**: `8080/tcp` (웹 로그뷰어) · `6080/tcp` (noVNC — Gazebo GUI) ·
`5600/udp` (페이로드 영상 RTP, air의 Gazebo 카메라→호스트)

**air 내부 포트(컨테이너 로컬)**: `5760/tcp`(serial0=C2) · `9002·9003/udp`(SITL↔Gazebo JSON FDM) ·
`5900/tcp`(x11vnc, noVNC가 6080으로 프록시)

**MAVLink 주소(sysid/compid)**: AV `1/1` · GCS(gcs_cli) `255/190` · VSM 서명 `255/195` ·
GPS 채널 `255/200·201` · 카메라/짐벌 `1/100` · 로그뷰어 `255/254` · 점검 도구 `255/240~253`

---

## 7. 디렉터리

```
testbed/
├── docker-compose.yml          # 6서비스 (+ sdr: profile "iq", video: profile "testvid")
├── .env.example                # 환경 변수 템플릿
├── PROJECT_STATUS.md           # 전체 현황·설계 이력·이슈
├── gcs_cli.py                  # QGC 대체 제어 CLI (pymavlink)
├── air/                        # 공중: ArduPilot SITL + Gazebo Harmonic
│   ├── Dockerfile, start-sitl.sh  # SITL+Gazebo+ardupilot_gazebo+VNC 통합 기동
│   ├── worlds/dah_world.sdf    # Gazebo 월드(iris_with_gimbal, P-15/P-25)
│   └── params/m0-baseline.parm # (배터리 Failsafe 비활성 포함)
├── ground/
│   ├── mavlink-router/{...}     # (브로드캐스트 전환으로 미사용 — 참조용 보존)
│   └── signing/setup_signing.py # [이전됨] → scripts/setup_signing.py + mavsign.py
├── rf/                         # 무선 채널 (README.md)
│   ├── gnss_medium.py          # GPS 채널 A1 (라이브, GPS_SOURCE 스위치)
│   ├── channel/                # C2 매질 B (channel.py 브로드캐스트 허브 + ctrl/ 재밍)
│   └── sdr/                    # GPS 채널 A2 (실제 I/Q: gps-sdr-sim→GNSS-SDR)
├── payload/                    # 페이로드 채널 C: 카메라/짐벌 + KLV (브로드캐스트)
├── video/                      # 페이로드 영상 C.2 폴백: 테스트패턴 RTP (profile testvid)
│                               #   기본 영상원은 air의 Gazebo 카메라(P-25)
├── logviewer/                  # 웹 대시보드 :8080 (다운링크 수동 수신)
├── tools/                      # 지상 도구 컨테이너(Dockerfile) — 진단·제어 실행
└── scripts/                    # 검증·측정 도구 + bcastlink.py + 서명(mavsign·setup_signing) (§4)
```

> 빌드 로그·GNSS 생성 데이터(RINEX·I/Q bin 등)·설계 HTML 문서는 저장소에서 제외되어
> `dah/_excluded/` 로 분리 보관된다(`.gitignore`로 재유입 방지).

---

## 8. 알려진 이슈 (요약)

- **GPS health 비트 off** (`verify_all` WARN): `GPS_TYPE=14`(외부 MAV GPS)의 보고 특성.
  fix=3·EKF 정상이라 텔레메트리·항법엔 지장 없음. **단 이 health off가 prearm "GPS 1: not
  healthy"로 작동해 `gcs_cli arm`을 차단**한다(외부 GPS 구성 고유). Gazebo 물리엔진은
  통합됨(2026-06-28(b)) — 실제 비행 실습 전 `ARMING_CHECK` 조정 또는 GPS_INPUT health 보강으로
  arm 게이트 해제 예정(PROJECT_STATUS §9-B).
- **A1/A2 동시 금지**: 같은 GPS 소스 — A2 사용 시 `docker compose stop gnss`(또는 `GPS_SOURCE=A2`).
- **GNSS-SDR(A2)**: `gnss-sdr.conf`의 `Channels.in_acquisition=8` 필수, `DUR=180` 마진 권장.
- **브로드캐스트는 컨테이너 전용**(P-21/P-22): Docker 브리지 브로드캐스트는 호스트로
  전달되지 않는다. 그래서 진단·제어를 `tools` 컨테이너에서 실행한다(QGC/호스트 스크립트 제거).
- **C2 재밍 중 GPS 유지**: SIMSTATE(GPS truth 피드)와 GPS_INPUT은 재밍 면제라,
  primary를 강재밍해도 FC는 GPS fix를 유지한다(채널 독립 원칙).

상세 디버깅 학습은 [`PROJECT_STATUS.md`](PROJECT_STATUS.md) §8, [`rf/README.md`](rf/README.md) 참조.
