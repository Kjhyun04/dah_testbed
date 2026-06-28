# DAH 테스트베드 — 프로젝트 현황 (v0 2026-06-27 · 최종 갱신 2026-06-28)

> 다음 세션에서 이어서 진행/분석하기 위한 상세 정리. 전체 구성·결정·검증·이슈·남은 작업.
> **2026-06-28 브로드캐스트 전환·문서 정정·실측 검증 반영 — 아래 「변경 이력」이 최신 상태.**

---

## 변경 이력 — 2026-06-28(b): Gazebo Harmonic 물리엔진 통합 (A 묶음)

§9-A "Gazebo 묶음" 구현. 결정: **Gazebo Harmonic + ardupilot_gazebo**, **air 컨테이너에
SITL+Gazebo+VNC 합침**(localhost FDM으로 P-24 레이턴시 최소화).

**구현 (코드)**
- **P-15 물리엔진**: `air/Dockerfile`에 Gazebo Harmonic(`gz-harmonic`) + `ardupilot_gazebo`
  플러그인 빌드 추가. `air/worlds/dah_world.sdf` 신규(iris_with_gimbal + 인라인 지면,
  physics/sensors/imu/navsat 시스템). `start-sitl.sh`가 SITL을 `--model JSON`(JSON FDM,
  127.0.0.1:9002/9003)로 기동해 Gazebo와 연동. 기존 `--model "+"`(내장 단순물리) 대체.
  파라미터: `copter.parm,gazebo-iris.parm,m0-baseline.parm`(외부 GPS·배터리 FS 설정 유지).
- **P-23 VNC GUI**: 컨테이너 내 `Xvfb :1` + `openbox` + `x11vnc` + `noVNC/websockify`.
  브라우저로 `http://localhost:6080/vnc.html` 접속해 Gazebo GUI 관측. `GZ_HEADLESS=1`이면 생략.
- **P-24 SITL↔Gazebo 레이턴시**: 동일 컨테이너 localhost UDP(9002/9003)로 연결해 최소화.
- **P-25 video→Gazebo 카메라**: iris_with_gimbal 내장 `GstCameraPlugin`이 카메라 센서를
  H.264 RTP로 `CAM_HOST:CAM_PORT`(기본 host.docker.internal:5600) 송출. `start-sitl.sh`가
  모델 SDF의 `<udpHost>/<udpPort>`를 런타임 주입. 기존 `video` 테스트패턴 서비스는
  `profiles:["testvid"]` 폴백으로 전환(기본 up에서 비활성).
- **compose**: `air`에 `6080:6080`(noVNC)·`CAM_*`/`HOME_LOC`/`GZ_HEADLESS` env·
  `host.docker.internal:host-gateway`·`shm_size:1gb` 추가. 소프트웨어 GL(`LIBGL_ALWAYS_SOFTWARE=1`,
  Windows/Docker GPU 미통과 대응).

**상류 대조 검증 (2026-06-28(b), ardupilot_gazebo main 저장소 직접 확인)** — 🟢 구조 확정.
초기 구현의 2개 버그를 발견·수정:
- (수정) 카메라 sed 대상: `iris_with_gimbal/model.sdf`(GstCameraPlugin 없음) →
  **`gimbal_small_3d/model.sdf`**. iris_with_gimbal = iris_with_standoffs(ArduPilotPlugin,
  **fdm_port_in 9002**) + gimbal_small_3d(name=gimbal, 카메라). `--model JSON`(127.0.0.1:9002) 정합.
- (수정) 카메라 태그명: `<udpHost>/<udpPort>`(camelCase 오타) → **`<udp_host>/<udp_port>`**(snake_case).
- (수정) 빌드 의존성 누락: **`libopencv-dev`·`gstreamer1.0-gl`** 추가(README 명시, 카메라 플러그인 필수).

**라이브 검증 (2026-06-29, 실제 빌드·기동)** — 🟢 핵심 동작 확인. `docker compose build air` 성공
(ardupilot_gazebo 플러그인 ArduPilot/GstCamera/CameraZoom/Parachute 전부 컴파일). 기동 후:
- ✅ **noVNC `http://localhost:6080/vnc.html` HTTP 200** — Gazebo GUI 관측 가능.
- ✅ **SITL↔Gazebo FDM 연결**(SERIAL0 connection, sim_time 진행, ArduPilotPlugin 프레임 교환).
- ✅ **verify_all 8 PASS / 0 WARN / 0 FAIL** — fix=3 sats=14, **GPS health 정상**(이전 WARN 해소 →
  §9-B arm 게이트도 해소 가능성, 비행 실습 시 재확인 권장).

**라이브 중 발견·수정한 버그 3건**:
1. (Dockerfile) **x264enc 누락** → 카메라 파이프라인 "failed to create GStreamer elements".
   `gstreamer1.0-plugins-ugly`(+`-tools`) 추가. (README 미기재 의존성.)
2. (start-sitl.sh) **docker restart 시 X 락 잔존**(`/tmp/.X1-lock`) → Xvfb `:1` 점유 실패 →
   gz GUI abort → FDM 중단. Xvfb 기동 전 잔존 락 정리 추가.
3. (start-sitl.sh) **server+GUI 결합 모드(`gz sim -r`)가 소프트웨어 렌더링에서 물리 스텝 정지**
   (SITL "No JSON sensor"). **헤드리스 서버(`-s -r`) + 별도 GUI 클라이언트(`-g`)로 분리** → 물리/FDM
   안정. GUI가 느려도 비행 시뮬은 영향 없음.
4. (m0-baseline.parm) **arm "Main loop slow"** — GPU 미통과 소프트웨어 렌더로 SITL 루프율이
   ~166Hz로 하락, 기본 400Hz arm 검사 거부. **`SCHED_LOOP_RATE=100`** 으로 낮춰 안정 무장(HW
   렌더/`GZ_HEADLESS=1`면 200~400 상향 가능). 재시작 직후 10~15초 settle 후 무장됨.
5. (gnss_medium.py) **이륙 직후 LAND 페일세이프** — GPS_INPUT 고도가 고정 30m였음(SIMSTATE엔
   고도 없음). 다운링크 **VFR_HUD.alt(실제 고도) 추종**으로 변경. gnss 중지 시에도 baro로 고도
   정확(순환참조 아님) 확인.

**카메라(P-25) 잔여 한계** — 🟡 GPU 미통과 환경. 인코더·라우팅·센서 렌더는 개별 검증 통과
(수동 gst 파이프라인은 621 RTP/5s 수신)하나, GstCameraPlugin이 enable 게이트(기본 off, enable 토픽
구독 미형성) + 소프트웨어 렌더 저속으로 실 스트림 미생성. **영상 채널은 `--profile testvid`(테스트패턴)
폴백으로 운용 중**. Gazebo 카메라 실스트림은 GPU 통과(HW 렌더) 환경에서 재시도 권장.

**영구화 완료 (2026-06-29)** — air·gnss 이미지 **재빌드 후 `up -d --force-recreate`로 배포**.
위 5개 수정 전부 이미지에 반영됨(더 이상 live-patch 아님).

**최종 통합 검증 (baked 이미지, 실행 기반)** — 🟢 전 항목 통과. 검증 방향은 *현실적 GCS-UAV
구조 유사성 + 동작 정합성*(공격 가능성 평가 제외 — 사용자가 직접 실습 예정).
- 기능: verify_all **8 PASS/0/0**, FDM No-JSON 0(스톨 없음), 비행 mode→arm→takeoff→land 전 주기,
  **고도 추종 정확**(GPI.relalt 10m = Gazebo Z 9.9m), LAND 페일세이프 미발생, gnss 중지 시 GPS
  상실 페일세이프(항법 부하성 정상), **링크 failover**(primary→secondary→failback), 페이로드
  (comp100+KLV), 영상 RTP, 로그뷰어/noVNC 200, 텔레 스트림 ~137msg/s(실 ArduPilot 구성).
- 현실성: MAVLink v2·GCS↔FC·GPS 독립·다중링크 BVLOS·ISR(KLV ST0601)·ArduPilot 비행 = 🟢 충실.
  단순화: 물리계층 부재(패킷 손실/지연만), GPU 미통과(루프 100Hz), STANAG DLI 미구현.
- 공격 선설정: jam=0(중립)·attacker 도구 없음 — **중립 인프라 baseline 확보**.

> 형상: 위 변경 전부 working tree(미커밋). `air/worlds/` 신규.

---

## 변경 이력 — 2026-06-28: 브로드캐스트 전환 + 문서 정정 (Gazebo 제외)

`DAH2026_전체_문제점_해결방안.md`의 문제점 해결을 반영(Gazebo 관련 P-15/P-23~P-26 제외).

**네트워크 재구성 (코드)**
- **router 제거(P-19)**: `c2channel`이 air(TCP)↔dahnet UDP 브로드캐스트를 잇는 무선
  매질 허브로 재작성. 다운링크 `172.28.255.255:14550` 방사(수동 도청), 업링크 `14555` 수신.
- **C2 채널(P-17/P-18)**: `rf/channel/channel.py` 브로드캐스트 프록시. 재밍·failover·지연
  유지, GPS_INPUT(업링크)·SIMSTATE(다운링크) 재밍 면제로 GPS 독립성 보존.
- **GPS A1/A2(P-20)**: `gnss_medium.py`에 `GPS_SOURCE` 소프트웨어 스위치(A1 외 idle).
  SIMSTATE는 다운링크 수신, GPS_INPUT은 업링크 브로드캐스트 송출. `sdr_to_gps.py`도 업링크화.
- **페이로드**: `payload.py` 다운링크 방사 + 업링크 명령 수신, KLV도 dahnet 브로드캐스트.
- **QGC 대체(P-26)**: `gcs_cli.py`(pymavlink) + `tools` 컨테이너. 진단 스크립트는
  `scripts/bcastlink.py`(다운 14550 수신 / 업 14555 송신) 헬퍼로 전환, `tools`에서 실행.
- **배터리 Failsafe(P-16)**: `m0-baseline.parm`에 `FS_BATT_ENABLE=0` 등 추가.
- 서비스 구성: air·c2channel·gnss·payload·video·logviewer·**tools** (router 삭제, +sdr profile iq).
- `ground/mavlink-router/`는 미사용(참조용 보존). 호스트 노출은 `8080`(로그뷰어)·`5600`(영상)만.

**문서 정정** — HTML: `docs/testbed-overview.html`(P-01·02·07·08·09·11·12·14),
`reports/DAH2026_AS3_*`(P-03·04·10), `reports/DAH2026_S4S5_*`(P-05·06). 증거 등급
(실증🟢/원리🟡/가정🔴/조건부🟣) 일관 적용, CWE 재매핑(345→306+362, 840→924+345 등).
DOCX 생성기 동기화: `reports/build_as3.py`(P-03 AV:L·P-04 가정 등급), `build_s4s5.py`
(P-05 first-come 락·P-06 CoT≠OTH-GOLD, CWE 재매핑) 수정 후 DOCX 재생성 → HTML·DOCX 정합.

**정리(cleanup)** — `ground/mavlink-router/` 제거(미사용). `rf/`·`payload/`·`logviewer/`
README 및 `scripts/*` docstring의 옛 router/QGC/14551 참조를 브로드캐스트·tools 실행으로 갱신.

**실측 검증 (2026-06-28, `docker compose build/up` 후 라이브)** — ✅ 통과
- `verify_all`: **7 PASS / 1 WARN / 0 FAIL** (v0 동일). 다운링크 SR0 29~31종 자동 수신,
  GPS fix=3 sats=14 5Hz, 양방향 param read(업14555→air→다운14550) 정상.
- 수동 도청: 컨테이너가 `udpin:14550` 열어 다운링크 689건/5s 수신(P-17 핵심 목표 달성).
- 제어: `gcs_cli mode GUIDED` **ACK OK**, 모드 실제 전환. 페이로드 comp100+KLV 브로드캐스트 수신.
- C2 재밍: primary 0.9→secondary failover(하트비트 유지) / 양링크 0.95→C2 저하, 해제 후
  fix=3 즉시 복귀(GPS_INPUT·SIMSTATE 면제로 FC가 재밍 내내 GPS lock 유지).

**발견사항 — arm/GPS-health 게이트 (사전 이슈, 브로드캐스트와 무관)**
- `gcs_cli arm` → `result=4` "PreArm: GPS 1: not healthy". `GPS_TYPE=14`(외부 GPS)에서
  GPS health 비트가 항상 off(0/60)인데 arming 검사가 이를 게이트. GPS_INPUT은 5Hz·fix=3로
  정상 전달되므로 **순전히 GPS_TYPE=14 보고 특성**. v0 "ARM 16.4m"는 M0(내부 SIM GPS) 기록이고
  외부화 이후 ARM은 재시험된 바 없음. → 비행 실습 시 해결 필요(아래 남은작업 B).

**이번 변경에서 제외/보류**
- Gazebo 그룹(P-15·P-23·P-24·P-25) + `air/start-sitl.sh` gazebo-iris 전환 → 본선 준비 묶음.
- attacker/ 도구(sniffer·injector·analyzer) → 역할 경계상 미구축(환경만 제공).
- `ground/signing/setup_signing.py` → 점대점 서명이라 브로드캐스트 미적응(host:14551 잔존).

> 형상: 위 변경은 전부 working tree 상태(미커밋). `ground/mavlink-router` 삭제는 인덱스 스테이징.

---

## 1. 목표 / 핵심 원칙

- **DAH 공모전**: UAV/UGV · 위성망 네트워크 공방전 테스트베드.
- **목표**: 실제 군용 무인기 통제 구조를 오픈소스로 근사한 가상 환경에서, 지상↔UAV
  사이 무선 채널들을 모델링하고 그 위에서 재밍·스푸핑 등 공격을 실습.
- **역할 경계 (중요)**: *나(AI)는 공격당할 인프라/환경만 구축*, **공격 실행은 사용자가 직접**.
  (Red/Blue 공격·방어 자동화는 만들지 않음 — 검증·관측 도구와 로그뷰어는 인프라라 OK.)
- **v0 방향**: 환경(채널) → 사용자 공격 → 웹 로그뷰어 관측. → **v0 전부 구현·검증 완료.**

---

## 2. 전체 아키텍처

> ⚠ 아래 §2·§5 다이어그램/포트는 **router 기반 v0 (2026-06-27)** 기록이다. 2026-06-28
> 브로드캐스트 전환으로 router 제거·c2channel 허브·tools/gcs_cli 추가됨 — **최신 구조는
> 상단 「변경 이력」과 `README.md` 참조**. 아래는 설계 이력 보존용.

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
    README.md                         # as-built 실행·사용 가이드 (현행)
    docker-compose.yml                # 6서비스(+sdr profile iq, +video profile testvid)
    .env.example
    gcs_cli.py                        # QGC 대체 제어 CLI (pymavlink, tools에서 실행)
    air/      Dockerfile, start-sitl.sh           # ArduPilot SITL + Gazebo Harmonic 통합 기동
              worlds/dah_world.sdf                # Gazebo 월드(iris_with_gimbal, P-15/P-25)
              params/m0-baseline.parm             # 배터리 FS 비활성·외부 GPS
    ground/
      mavlink-router/ Dockerfile, main.conf                        # 라우터(미사용, 참조용 보존)
      signing/ setup_signing.py                                    # MAVLink v2 서명(VSM 자리)
    rf/
      gnss_medium.py                  # GPS 채널 A1 (라이브, GPS_SOURCE 스위치)
      README.md                       # 무선 채널(GPS A / C2 B) 문서
      sdr/  Dockerfile, gnss-sdr.conf, run_decode.sh, run_channel.sh, sdr_to_gps.py  # A2 실제 I/Q
      channel/ Dockerfile, channel.py, ctrl/{jam_primary,jam_secondary,active}        # C2 B(브로드캐스트 허브)
    payload/  Dockerfile, payload.py, README.md                    # C 카메라/짐벌+KLV
    video/    Dockerfile, run_video.sh                             # C 영상 폴백(테스트패턴, profile testvid)
    logviewer/ Dockerfile, server.py, index.html, README.md        # #9 웹 대시보드
    tools/    Dockerfile                                           # 지상 도구 컨테이너(진단·제어 실행)
    scripts/  check_telemetry.py measure_streams.py monitor_flight.py bcastlink.py
              verify_all.py jam_check.py check_payload.py check_video.py
    docs/  (설계 HTML/md 은 _excluded/ 로 분리 — README §7 참조)
```
※ `testbed/DAH2026_테스트베드_구성설계.html` 는 기존 파일(내가 만들지 않음, 미사용).

---

## 5. 네트워크 / 포트 / 주소체계 (현행: 브로드캐스트 + Gazebo)

> 옛 router/QGC 기반 엔드포인트는 §2·§7(이력)에 보존. 아래는 현재 구성.

**컨테이너 IP** (dahnet 172.28.0.0/16): air .10 / gnss .30 / sdr .40(profile iq) / c2channel .50 / payload .60 / video .70(profile testvid) / logviewer .80 / tools .90  (router .20 제거)

**dahnet 브로드캐스트 포트**(컨테이너 전용, 172.28.255.255): 14550/udp(다운링크 텔레) · 14555/udp(업링크 제어+GPS_INPUT) · 14580/udp(KLV)

**호스트 노출 포트**: 8080/tcp(로그뷰어) · 6080/tcp(noVNC Gazebo GUI) · 5600/udp(영상 RTP, air Gazebo 카메라)

**air 내부 포트**: 5760/tcp(serial0=C2, c2channel 접속) · 9002·9003/udp(SITL↔Gazebo JSON FDM) · 5900/tcp(x11vnc→noVNC 6080 프록시). serial1(5762)은 SITL 바인딩 충돌로 포기 → GPS는 외부 채널 + C2 GPS_INPUT 면제로 분리.

**MAVLink 주소**: AV(sys1/comp1) · VSM서명(255/195) · GPS채널(255/200·201) · 카메라(1/100) · GCS(gcs_cli 255/190) · 로그뷰어(255/254) · 도구(255/240~253)

---

## 6. 실행 / 검증 / 공격

```bash
cd dah/testbed
docker compose build                 # 최초(ArduPilot·Gazebo Harmonic·GNSS-SDR·GStreamer, 시간·용량 큼)
docker compose up -d                 # air(+Gazebo)·c2channel·gnss·payload·logviewer·tools

# 검증 (브로드캐스트 세그먼트 = 컨테이너 전용 → tools 안에서 실행)
docker compose exec tools python scripts/verify_all.py     # 채널·텔레·GPS·EKF (7 PASS 기대)
docker compose exec tools python scripts/check_payload.py  # 카메라+KLV
python scripts/check_video.py                              # 영상 RTP(호스트 5600, Gazebo 카메라)

# 제어 (QGC 대체)
docker compose exec tools python gcs_cli.py status

# 관측
# 브라우저: http://localhost:8080          # 로그뷰어 대시보드
# 브라우저: http://localhost:6080/vnc.html  # Gazebo GUI(3D 물리 비행)

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

- **GPS health 비트 off** (verify_all WARN): `GPS_TYPE=14`(외부 MAV GPS)의 보고 특성. fix3·EKF정상이라 텔레메트리/항법엔 무관. GPS 시각 넣어도 안 바뀜. **단, 2026-06-28 확인: 이 health off가 ArduCopter prearm "GPS 1: not healthy"로 작동해 `arm`을 차단**한다(health 0/60). v0 "ARM 16.4m"는 외부화 이전 M0(내부 SIM GPS) 기록. → 비행 실습 시 §9-B 해결 필요.
- **GNSS-SDR(A2)**: ① `Channels.in_acquisition=8`(병렬 포착) 필수, `=1`이면 PVT 간헐 실패 ② `DUR=180`(신호 길이) 마진 ③ gnss-sdr를 **shell 리다이렉트**로 호출(python 파일객체 stdout이면 PVT 미산출) ④ 샘플 궤도력 `brdc0010.22n`(자동탐지).
- **air serial1(5762) 바인딩 실패**: `--serial1 tcp:0.0.0.0:5762`가 5760에 바인딩 시도→충돌. 포기하고 GPS_INPUT 면제 방식으로 분리.
- **C2 채널 복원력**: air 재시작 시 채널이 죽은 TCP 붙들고 재연결 안 함 → `air_watchdog`(10s 무수신→프로세스 종료→restart 정책 재연결) 추가.
- **빌드 gotcha**: gps-sdr-sim엔 `build-essential`(libc 헤더), mavlink-router엔 `systemd` 패키지(`systemd.pc`), ArduPilot은 **비root**로 빌드(+`USER=ardu` for usermod).
- **mavlink-router**: TcpEndpoint Address는 **IP만**(DNS 미해석) · 설정값 뒤 **인라인 주석 금지** · `TcpServerPort` 켜야 QGC TCP(5790).
- **QGC**: UDP Server 모드 까다로움 → **TCP 5790** 권장.
- **컨테이너 restart 정책**: air/router에 없으면 Docker 재시작 시 다운 → 전부 `unless-stopped`.

---

## 9. 남은 작업 / 다음 단계 (분석·확장 방향)

### 문제점 해결 후속 (2026-06-28 기준, Gazebo 제외 적용 후)

**A. Gazebo 묶음** — ✅ **구현 완료(2026-06-28(b), 라이브 검증 대기)**. P-15(물리)·P-23(VNC)·
P-24(localhost FDM)·P-25(Gazebo 카메라). 상단 「변경 이력 — Gazebo Harmonic 물리엔진 통합」 참조.
→ 다음 세션 잔여: `docker compose build air` 후 라이브 검증(§위 검증 상태 5항목)·B(arm 게이트) 동반 비행 실습.

**B. arm/GPS-health 게이트 (A와 함께)** — `gcs_cli arm`이 "GPS 1: not healthy"로 차단(§8).
실제 비행 실습에 필요. 해결 옵션: ① GPS_INPUT을 healthy로 보고(원인 규명 필요) ②
`ARMING_CHECK`에서 GPS 비트 제외(즉효, sim 양보 명시) ③ force-arm(편법). Gazebo 비행 관측과 묶음.

**C. 선택 / 역할경계 (사용자 결정)**
- **attacker/ 도구**(sniffer·injector·analyzer): 문서 §8엔 "추가"이나 역할 경계상 미구축.
  브로드캐스트로 도청(`udpin:14550`)·주입(`udpout:…:14555`) *가능한 환경*은 이미 제공. sniffer만
  관측 도구로 제공하는 절충도 가능 — 지시 필요.
- **`ground/signing` 적응**(P-02 방어 시연): `setup_signing.py`를 `bcastlink`로 적응 필요(현재
  host:14551 참조). 단 `accept_unsigned` off 시 무서명 정당 도구(verify_all·gcs_cli)도 차단되므로
  키 일관 적용 또는 데모 시나리오 한정 운용 필요.

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
