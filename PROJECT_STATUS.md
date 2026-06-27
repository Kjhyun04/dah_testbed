# DAH 테스트베드 — 프로젝트 현황 (2026-06-27)

> 다음 세션에서 이어서 진행/분석하기 위한 상세 정리. 전체 구성·결정·검증·이슈·남은 작업.

---

## 1. 목표 / 핵심 원칙

- **DAH 공모전**: UAV/UGV · 위성망 네트워크 공방전 테스트베드.
- **목표**: 실제 군용 무인기 통제 구조를 오픈소스로 근사한 가상 환경에서, 지상↔UAV
  사이 무선 채널들을 모델링하고 그 위에서 재밍·스푸핑 등 공격을 실습.
- **역할 경계 (중요)**: *나(AI)는 공격당할 인프라/환경만 구축*, **공격 실행은 사용자가 직접**.
  (Red/Blue 공격·방어 자동화는 만들지 않음 — 검증·관측 도구와 로그뷰어는 인프라라 OK.)
- **v0 방향**: 환경(채널) → 사용자 공격 → 웹 로그뷰어 관측. → **v0 전부 구현·검증 완료.**

---

## 2. 전체 아키텍처 (현재 동작 중)

```
 호스트(Windows+Docker Desktop)
  QGC ─tcp5790→ router    scripts/*.py ─udp14551→ router    브라우저 ─http8080→ logviewer
  KLV ←udp14580─ payload   영상 ←udp5600─ video
 ───────────────────────────── Docker network dahnet 172.28.0.0/16 ─────────────────
  dah-router(.20) ─udp14570→ dah-c2channel(.50) ─tcp5760→ dah-air(.10) ArduPilot SITL
     │  (C2 링크 채널 B: primary/secondary failover + 재밍 + 지연)          ▲ GPS_TYPE=14
     ├─udp14552→ dah-gnss(.30)  GPS 채널 A1(라이브)  ──GPS_INPUT───────────┤ (외부 GPS만)
     │           dah-sdr(.40)   GPS 채널 A2(실제 I/Q, profile iq) ─────────┘
     ├─udp14553→ dah-payload(.60) 카메라/짐벌(comp=100) + KLV(ST0601)
     │           dah-video(.70)   GStreamer RTP H.264 영상
     └─udp14554→ dah-logviewer(.80) 웹 대시보드(:8080)
```

**3개 물리 무선 채널** (각각 독립, 사용자가 직접 공격):
| 채널 | 경로 | 컨테이너 | 공격면 |
|---|---|---|---|
| **A GPS** | 위성→드론 | gnss(A1)/sdr(A2) | 가짜 좌표 I/Q 주입 = 스푸핑 |
| **B C2/텔레** | 지상↔드론 | c2channel | 손실↑ = 재밍 → failover |
| **C 페이로드** | 드론→지상 | payload+video | KLV 센서위치 스푸핑·영상 가로채기·카메라 탈취 |

---

## 3. 구현·검증 현황 (단계별)

| 단계 | 내용 | 검증 결과 |
|---|---|---|
| **M0** | DVD 포크(ArduPilot SITL)+컴패니언 라우터+QGC, MAVLink v2 서명, 비행 | 7/7 (ARM·이륙 16.4m) |
| **#2** | 3-plane(C2/텔레/페이로드) 트래픽 측정·명세 | 28종 텔레, 5Hz≈53kbit/s. `docs/3-plane-spec.md` |
| **A · R0** | GPS 외부화(SIM_GPS_DISABLE=1, GPS_TYPE=14, GPS_INPUT 주입) | 채널 ON→fix3 / OFF→상실 |
| **A · A1** | GPS 채널 컨테이너화(dah-gnss) | stop→상실 / start→fix3 |
| **A · A2** | 실제 I/Q: gps-sdr-sim→GNSS-SDR→GPS_INPUT | 좌표37.60 주입→FC GPS=37.60 |
| **B · B.0** | C2 채널 에뮬 삽입 + 재밍 + GPS 면제 | jam0.9→하트비트 1→0.12Hz, GPS fix3 유지 |
| **B · B.1** | 다중링크(primary/secondary) + 자동 failover/failback | primary재밍0.95→secondary전환→1.0Hz 유지 |
| **B · B.2** | 링크별 지연(위성300ms/RF50ms) | 적용됨 |
| **C · C.0** | 카메라/짐벌 MAVLink 컴포넌트(comp=100) | HEARTBEAT+GIMBAL 방출, 명령 ACK |
| **C · C.1** | KLV 메타데이터(MISB ST0601) | 47B 디코드→센서위치(37.5665) |
| **C · C.2** | 영상(GStreamer RTP H.264) | 624pkt/5s→5600 |
| **#9** | 웹 로그뷰어(3채널 대시보드+이벤트+궤적) | 정적+동적(재밍→failover 이벤트 포착) |

**최종 통합 검증**: 7 컨테이너 Up, verify_all 7 PASS / 1 WARN / 0 FAIL.

---

## 4. 디렉터리 / 파일 맵

```
dah/
  CLAUDE.md
  docs/testbed-overview.html          # 개념·설계 배경·STANAG 이론·로드맵 (왜/무엇)
  testbed/
    PROJECT_STATUS.md                 # ← 이 문서
    README.md                         # M0 가이드
    docker-compose.yml                # 7서비스(+sdr profile iq)
    .env.example
    air/      Dockerfile, start-sitl.sh, params/m0-baseline.parm   # ArduPilot SITL
    ground/
      mavlink-router/ Dockerfile, main.conf                        # 라우터
      signing/ setup_signing.py                                    # MAVLink v2 서명(VSM 자리)
    rf/
      gnss_medium.py                  # GPS 채널 A1 (라이브)
      README.md                       # 무선 채널(GPS A / C2 B) 문서
      sdr/  Dockerfile, gnss-sdr.conf, run_decode.sh, run_channel.sh, sdr_to_gps.py  # A2 실제 I/Q
      channel/ Dockerfile, channel.py, ctrl/{jam_primary,jam_secondary,active}        # C2 B
    payload/  Dockerfile, payload.py, README.md                    # C 카메라/짐벌+KLV
    video/    Dockerfile, run_video.sh                             # C 영상
    logviewer/ Dockerfile, server.py, index.html, README.md        # #9 웹 대시보드
    scripts/  check_telemetry.py measure_streams.py monitor_flight.py
              verify_all.py jam_check.py check_payload.py check_video.py
    docs/  testbed-guide.html(as-built) address-scheme.md m0-validation.md 3-plane-spec.md
```
※ `testbed/DAH2026_테스트베드_구성설계.html` 는 기존 파일(내가 만들지 않음, 미사용).

---

## 5. 네트워크 / 포트 / 주소체계

**컨테이너 IP**: air .10 / router .20 / gnss .30 / sdr .40 / c2channel .50 / payload .60 / video .70 / logviewer .80

**라우터 엔드포인트**: c2channel(UDP14570 Normal→.50) · QGC(TCP5790 server) · UDP14550/14551 · gnss(14552) · payload(14553) · logviewer(14554)

**호스트 포트**: 5790/tcp(QGC) · 14550/14551 udp · 5600/udp(영상 수신) · 14580/udp(KLV 수신) · 8080/tcp(로그뷰어)

**air 포트**: 5760(serial0=C2). serial1(5762) 노출 시도했으나 SITL 바인딩 문제로 포기 → GPS는 라우터14552 경유 + C2채널에서 GPS_INPUT 면제로 분리.

**MAVLink 주소**: AV(sys1/comp1) · VSM서명(255/195) · GPS채널(255/200·201) · 카메라(1/100) · QGC(255/190) · 로그뷰어(255/254) · 도구(255/240~253)

---

## 6. 실행 / 검증 / 공격

```bash
cd dah/testbed
docker compose build                 # 최초(ArduPilot·GNSS-SDR·GStreamer 빌드, 시간 소요)
docker compose up -d                 # air+router+gnss+c2channel+payload+video+logviewer

# 검증
python scripts/verify_all.py         # 채널·텔레·GPS·EKF (7 PASS 기대)
python scripts/check_payload.py      # 카메라+KLV
python scripts/check_video.py        # 영상 RTP
# 브라우저: http://localhost:8080     # 로그뷰어
# QGC: TCP 127.0.0.1:5790

# 공격 (사용자 직접)
echo 0.9 > rf/channel/ctrl/jam_primary          # C2 재밍 → 자동 failover (로그뷰어 포착)
echo 0   > rf/channel/ctrl/jam_primary          # 해제
docker compose stop gnss                          # GPS를 A2(실제 I/Q)로:
IQ_LAT=37.70 IQ_LON=127.10 docker compose --profile iq up -d sdr   # 가짜 좌표 스푸핑
```

---

## 7. 핵심 설계 결정 (이력)

| 결정 | 내용 / 사유 |
|---|---|
| 충실도 | **Tier 3 (실제 SDR/PHY)** 지향, 무HW Track S부터. 사용자 직접 공격 |
| 비행 스택 | PX4 → **ArduPilot** 선회 (UGV 지원·GPS 시뮬·DVD·보안연구 생태계) |
| 베이스 | **DVD(Damn Vulnerable Drone) 포크/참조** |
| 토폴로지 | 컴패니언 BVLOS · 다중링크 failover · **MAVLink v2 서명 ON** |
| STANAG 4586 | 논문 확인: **VSM 지상측**(CUCS와 co-locate), 실보안=링크 COMSEC(7085), 우리 MAVLink 서명은 그 근사. → **보류(#3)** |
| 최종목표(보류) | UCS LOI 권한계층 + 단계적 LOI 탈취 (STANAG과 함께 보류) |
| 역할 | **인프라만 구축, 공격은 사용자** (한때 Red/Blue 자동화 만들었다 제지받고 철회) |
| 채널 분리 | GPS는 온보드라 C2와 독립 → C2채널이 GPS_INPUT 손실·지연 면제 |

---

## 8. 알려진 이슈 / 디버깅 학습 (재현·확장 시 참고)

- **GPS health 비트 off** (verify_all WARN): `GPS_TYPE=14`(외부 MAV GPS)의 보고 특성. fix3·EKF정상·ARM성공이라 **비행 무관**. GPS 시각 넣어도 안 바뀜.
- **GNSS-SDR(A2)**: ① `Channels.in_acquisition=8`(병렬 포착) 필수, `=1`이면 PVT 간헐 실패 ② `DUR=180`(신호 길이) 마진 ③ gnss-sdr를 **shell 리다이렉트**로 호출(python 파일객체 stdout이면 PVT 미산출) ④ 샘플 궤도력 `brdc0010.22n`(자동탐지).
- **air serial1(5762) 바인딩 실패**: `--serial1 tcp:0.0.0.0:5762`가 5760에 바인딩 시도→충돌. 포기하고 GPS_INPUT 면제 방식으로 분리.
- **C2 채널 복원력**: air 재시작 시 채널이 죽은 TCP 붙들고 재연결 안 함 → `air_watchdog`(10s 무수신→프로세스 종료→restart 정책 재연결) 추가.
- **빌드 gotcha**: gps-sdr-sim엔 `build-essential`(libc 헤더), mavlink-router엔 `systemd` 패키지(`systemd.pc`), ArduPilot은 **비root**로 빌드(+`USER=ardu` for usermod).
- **mavlink-router**: TcpEndpoint Address는 **IP만**(DNS 미해석) · 설정값 뒤 **인라인 주석 금지** · `TcpServerPort` 켜야 QGC TCP(5790).
- **QGC**: UDP Server 모드 까다로움 → **TCP 5790** 권장.
- **컨테이너 restart 정책**: air/router에 없으면 Docker 재시작 시 다운 → 전부 `unless-stopped`.

---

## 9. 남은 작업 / 다음 단계 (분석·확장 방향)

### 보류된 군용 근사 심화 (#3)
- **STANAG 4586 DLI 레이어**: `python-stanag-4586-EDA-v1`+`-vsm` (CUCS↔VSM). Neptus는 IMC기반이라 연구급 한계 → python 스택을 코어로, Neptus는 선택 콘솔.
- **VSM = STANAG↔MAVLink 변환 + 서명 종단점**(지상측). VSM 장악=유효 서명 MAVLink 발행.
- **LOI 권한계층(LOI 1~5) + 단계적 탈취**: LOI3 페이로드→LOI4 기체→LOI5 이착륙. 공격경로: 키탈취·핸드오버 스푸핑·failover 악용·GPS 스푸핑 우회.
- 상세 설계는 `../docs/testbed-overview.html` §3·§5·§6 참조.

### 선택적 하드닝 (D)
- **UGV(Rover) 변형**: ArduPilot Rover로 air 교체(DAH는 UGV 포함). `air/Dockerfile`의 `./waf rover`.
- **Track H (실제 SDR HW)**: HackRF/USRP로 진짜 RF. 케이블 결선·감쇠기 필수(공중 방사 불법).
- **완전 STANAG 4609**: KLV-in-MPEG-TS 멀티플렉싱(현재 KLV는 별도 UDP).
- **Essential BVLOS 텔레레이트**: 위성 저대역 링크용 다운레이트(#2 발견).

### 가능한 분석
- 공격 시나리오별 효과 측정(재밍 J/S vs 통신율, 스푸핑 walk-off vs EKF innovation).
- 탐지 지표(EKF innovation·C/N0·하트비트율) 기반 이상탐지 분석.
- 채널 독립성·failover 동역학 정량화.

---

## 10. 문서 인덱스
- `docs/testbed-overview.html` — 개념·설계·STANAG 이론·로드맵 (rev.2)
- `docs/testbed-guide.html` — as-built 구성·통신과정·사용법 (현행)
- `docs/3-plane-spec.md` · `docs/address-scheme.md` · `docs/m0-validation.md`
- `rf/README.md` · `payload/README.md` · `logviewer/README.md` · `README.md`(M0)
- 메모리: 설계 결정·역할 원칙은 Claude 메모리에도 기록됨.
