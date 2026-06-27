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

```
 호스트(Windows + Docker Desktop)
  QGC ─tcp5790→ router    scripts/*.py ─udp14551→ router    브라우저 ─http8080→ logviewer
  KLV ←udp14580─ payload   영상 ←udp5600─ video
 ───────────────────────── Docker network dahnet 172.28.0.0/16 ─────────────────────
  dah-router(.20) ─udp14570→ dah-c2channel(.50) ─tcp5760→ dah-air(.10)  ArduPilot SITL
     │  (채널 B: primary/secondary failover + 재밍 + 지연)                ▲ 외부 GPS(GPS_TYPE=14)
     ├─udp14552→ dah-gnss(.30)  GPS 채널 A1(라이브)  ──GPS_INPUT──────────┤
     │           dah-sdr(.40)   GPS 채널 A2(실제 I/Q, profile iq) ────────┘
     ├─udp14553→ dah-payload(.60) 카메라/짐벌(comp=100) + KLV(ST0601)
     │           dah-video(.70)   GStreamer RTP H.264 영상
     └─udp14554→ dah-logviewer(.80) 웹 대시보드(:8080)
```

**3개 물리 무선 채널** (각 독립, 사용자가 직접 공격):

| 채널 | 경로 | 컨테이너 | 사용자 공격면 |
|---|---|---|---|
| **A — GPS** | 위성→드론 | `gnss`(A1) / `sdr`(A2) | 가짜 좌표 I/Q 주입 = 스푸핑, 잡음 = 재밍 |
| **B — C2/텔레** | 지상↔드론 | `c2channel` | 손실↑ = 재밍 → 자동 failover |
| **C — 페이로드** | 드론→지상 | `payload` + `video` | KLV 센서위치 스푸핑·영상 가로채기·카메라 탈취 |

---

## 2. 사전 요구사항

- **Docker + Docker Compose** (Windows는 **Docker Desktop + WSL2** 권장)
- 호스트에 **Python 3** + `pymavlink` (점검 스크립트용): `pip install pymavlink`
- **QGroundControl** (선택, GUI 확인용)

> 최초 빌드는 ArduPilot SITL·GNSS-SDR·GStreamer를 소스/패키지로 받아 빌드하므로
> 시간이 걸린다(수십 분 가능).

---

## 3. 실행 (전체 흐름)

```bash
cd dah/testbed

# 0) 환경 변수 준비 (선택) — 서명 비밀·빌드 태그 등
cp .env.example .env        # 필요 시 SIGNING_PASSPHRASE 등 수정

# 1) 빌드 (최초 1회)
docker compose build

# 2) 기동 — 7개 서비스(air·router·gnss·c2channel·payload·video·logviewer)
docker compose up -d

# 3) 검증 (호스트에서, 아래 §4)
python scripts/verify_all.py        # 7 PASS / 1 WARN 기대

# 4) 관측
#    브라우저: http://localhost:8080  (로그뷰어 대시보드)
#    QGC:      TCP 127.0.0.1:5790

# 5) 공격 (사용자 직접, 아래 §5)

# 종료
docker compose down
```

`.env`를 만들지 않아도 `.env.example`의 기본값으로 동작한다.
`ARDUPILOT_TAG=Rover-4.5`(+ `air/Dockerfile`의 `./waf rover`)로 바꾸면 UGV 변형.

### MAVLink v2 서명 (선택)

지상 종단점 ↔ FC end-to-end 서명을 켜려면:

```bash
python ground/signing/setup_signing.py
```

---

## 4. 검증 스크립트 (`scripts/`)

모두 호스트에서 실행하며, 기본 접속은 라우터 점검 엔드포인트 `udpout:127.0.0.1:14551`.
대부분 `[conn]` 인자로 접속 대상을 바꿀 수 있다.

| 스크립트 | 용도 | 사용 |
|---|---|---|
| `verify_all.py` | 연결·텔레·GPS·위치·EKF·C2 양방향 종합 점검 (PASS/WARN/FAIL) | `python scripts/verify_all.py [conn]` |
| `check_telemetry.py` | HEARTBEAT/위치/자세 텔레메트리 수신 확인 | `python scripts/check_telemetry.py [conn]` |
| `measure_streams.py` | 메시지 종류별 빈도·대역폭 측정(3-plane 분류) | `python scripts/measure_streams.py [conn] [sec] [--request]` |
| `monitor_flight.py` | ARM/이륙 시 armed·고도·상승률 라이브 모니터 | `python scripts/monitor_flight.py [conn] [sec]` |
| `jam_check.py` | C2 재밍 시 하트비트 수신율 ↓ / GPS 유지 확인 | `python scripts/jam_check.py [sec]` |
| `check_payload.py` | 카메라(comp=100) MAVLink + KLV(ST0601) 디코드 | `python scripts/check_payload.py` |
| `check_video.py` | UDP 5600에서 RTP 영상 패킷 수신 확인 | `python scripts/check_video.py` |

---

## 5. 공격 실습 (사용자가 직접)

채널은 정상 신호를 전달하는 중립 인프라다. 공격은 사용자가 채널에 신호를 주입하거나
재밍 노브를 올려서 가한다. 효과는 로그뷰어(`:8080`)와 검증 스크립트로 관측한다.

### B — C2 링크 재밍 → 자동 failover

```bash
echo 0.95 > rf/channel/ctrl/jam_primary     # primary 강재밍 → secondary로 failover
echo 0    > rf/channel/ctrl/jam_primary     # 해제 → primary로 failback
echo 0.95 > rf/channel/ctrl/jam_secondary   # 둘 다 막으면 통신 두절
python scripts/jam_check.py                  # 효과 측정
```

### A — GPS 스푸핑 (실제 I/Q, A2 모드)

A1(라이브)과 A2(I/Q)는 같은 GPS 소스라 **동시 가동 금지**.

```bash
docker compose stop gnss                                      # A1 중지
IQ_LAT=37.70 IQ_LON=127.10 docker compose --profile iq up -d sdr   # 가짜 좌표 I/Q 주입
# FC GPS가 IQ_LAT/IQ_LON으로 끌려가는지 verify_all / 로그뷰어로 확인
```

상세는 [`rf/README.md`](rf/README.md) (채널 A/B), [`payload/README.md`](payload/README.md) (채널 C) 참조.

---

## 6. 네트워크 / 포트 / 주소체계

**컨테이너 IP** (`dahnet` 172.28.0.0/16): air `.10` · router `.20` · gnss `.30` · sdr `.40` ·
c2channel `.50` · payload `.60` · video `.70` · logviewer `.80`

**호스트 노출 포트**:

| 포트 | 용도 |
|---|---|
| `5790/tcp` | QGroundControl (권장) |
| `14550/udp` | QGroundControl (대체) |
| `14551/udp` | 텔레메트리 점검 / VSM(서명) 종단점 |
| `5600/udp` | 페이로드 영상(RTP) 수신 |
| `14580/udp` | KLV(ST0601) 수신 |
| `8080/tcp` | 웹 로그뷰어 |

**MAVLink 주소(sysid/compid)**: AV `1/1` · QGC `255/190` · VSM 서명 `255/195` ·
GPS 채널 `255/200·201` · 카메라/짐벌 `1/100` · 로그뷰어 `255/254` · 점검 도구 `255/240~253`

---

## 7. 디렉터리

```
testbed/
├── docker-compose.yml          # 7서비스 (+ sdr: profile "iq")
├── .env.example                # 환경 변수 템플릿
├── PROJECT_STATUS.md           # 전체 현황·설계 이력·이슈
├── air/                        # 공중: ArduPilot SITL
│   ├── Dockerfile, start-sitl.sh
│   └── params/m0-baseline.parm
├── ground/
│   ├── mavlink-router/{Dockerfile, main.conf}   # 라우터 fan-out
│   └── signing/setup_signing.py                 # MAVLink v2 서명(VSM 자리)
├── rf/                         # 무선 채널 (README.md)
│   ├── gnss_medium.py          # GPS 채널 A1 (라이브)
│   ├── channel/                # C2 채널 B (channel.py + ctrl/ 재밍 노브)
│   └── sdr/                    # GPS 채널 A2 (실제 I/Q: gps-sdr-sim→GNSS-SDR)
├── payload/                    # 페이로드 채널 C: 카메라/짐벌 + KLV (README.md)
├── video/                      # 페이로드 영상 C.2: GStreamer RTP H.264
├── logviewer/                  # 웹 대시보드 :8080 (server.py + index.html, README.md)
└── scripts/                    # 검증·측정 도구 (§4)
```

> 빌드 로그·GNSS 생성 데이터(RINEX·I/Q bin 등)·설계 HTML 문서는 저장소에서 제외되어
> `dah/_excluded/` 로 분리 보관된다(`.gitignore`로 재유입 방지).

---

## 8. 알려진 이슈 (요약)

- **GPS health 비트 off** (`verify_all` WARN): `GPS_TYPE=14`(외부 MAV GPS)의 보고 특성.
  fix=3·EKF 정상·ARM 성공이라 비행엔 지장 없음.
- **A1/A2 동시 금지**: 같은 GPS 소스 — A2 사용 시 `docker compose stop gnss` 먼저.
- **GNSS-SDR(A2)**: `gnss-sdr.conf`의 `Channels.in_acquisition=8` 필수, `DUR=180` 마진 권장.
- **QGC**: UDP Server 모드가 까다로움 → **TCP 5790** 권장.

상세 디버깅 학습은 [`PROJECT_STATUS.md`](PROJECT_STATUS.md) §8, [`rf/README.md`](rf/README.md) 참조.
