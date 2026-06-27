# 무선 채널 계층 (RF channel, Track S)

드론을 둘러싼 무선 신호 경로(채널)들을 소프트웨어로 모델링하는 **중립 인프라**.
채널은 정상 신호를 그대로 전달하고, **공격(스푸핑/재밍)은 사용자가 채널에 신호를 주입해 직접 수행**한다.

> 용어: 이전 문서의 "매질" = 여기의 "채널/통로". 드론 주변엔 여러 채널이 있다:
> - **GPS 채널** (GPS 위성 → 드론 수신기, 단방향) ← R0/R1 대상
> - **C2 링크 채널** (지상 GCS ↔ 드론, 양방향 MAVLink) ← R2 대상 (지금은 TCP)

> Tier-3(실제 I/Q) 방향. 무HW(Track S)로 시작 → 추후 Track H(실제 SDR).

## 단계

| 단계 | 내용 | 상태 |
|---|---|---|
| **R0** GPS 외부화 | ArduPilot을 외부 `GPS_INPUT` 모드로 전환, `gnss_medium.py`가 SITL 진짜위치를 GPS로 공급 | ✅ 검증 완료 |
| **R1** 실제 I/Q 채널 | gps-sdr-sim → GNSS-SDR 소프트수신기 → 매질 → FC. 사용자가 스푸퍼 I/Q·재밍 잡음 주입 | 예정 |
| **R2** C2 링크 RF | MAVLink 무선구간 채널 에뮬(SNR→BER), 사용자가 링크 재밍 | 예정 |

## R0 — GNSS 매질 (gnss_medium.py)

ArduPilot의 내부 시뮬 GPS를 끄고(`SIM_GPS_DISABLE=1`), 외부 GPS(`GPS_TYPE=14`)로 전환.
매질이 SITL의 `SIMSTATE`(진짜위치)를 읽어 `GPS_INPUT`(#232)으로 5Hz 주입한다.
→ FC의 GPS가 **전적으로 이 매질을 경유**하므로, 이후 이 경로에 가짜 신호를 주입하면 항법이 오염된다.

### 사용

```bash
python rf/gnss_medium.py probe     # GPS 관련 파라미터 확인
python rf/gnss_medium.py setup     # 외부 GPS 모드 전환 + FC 재부팅 (1회)
python rf/gnss_medium.py run       # 매질 가동 (GPS_INPUT 주입 루프, 상시 실행)
python rf/gnss_medium.py status    # 현재 GPS fix 상태
```

> **중요:** GPS 채널이 떠 있어야 FC가 GPS를 가진다. 중지하면 fix를 잃는다(설계대로).

### A1: 컨테이너화 (완료, 2026-06-26)

GPS 채널을 **Docker 서비스 `dah-gnss`** (172.28.0.30)로 compose에 통합.
- 외부 GPS 설정(`GPS_TYPE=14`, `SIM_GPS_DISABLE=1`)을 air baseline params에 **baked** → 별도 setup 불필요.
- 라우터에 **GPS 전용 엔드포인트 UDP 14552** 추가, gnss 컨테이너가 거기로 GPS_INPUT 주입.
- `docker compose up -d` 로 자동 기동(`restart:unless-stopped`).
- 검증: `docker compose stop gnss`→fix 상실 / `start gnss`→fix=3 복구.

호스트 수동 실행(probe/status/run)은 디버그용으로 그대로 가능
(`python rf/gnss_medium.py status tcp:127.0.0.1:5790`).

### R0 검증 결과 (2026-06-26)

| 조건 | GPS_RAW_INT |
|---|---|
| 매질 `run` 가동 | fix=3 (3D), sats=14, 정상 좌표 |
| 매질 중지 | fix=1, sats=0, 좌표 0 → **GPS 상실** |

→ GPS가 매질에 종속됨을 확인. 외부 주입점 확보 완료.

## A2 — 실제 I/Q 채널 (gps-sdr-sim → GNSS-SDR)

GPS 위치를 메시지로 주는 대신, **진짜 GPS L1 신호(I/Q)를 만들어 소프트 수신기가 해독**한다.
구성: `rf/sdr/` (이미지 `dah-sdr`) = gps-sdr-sim(신호 생성) + GNSS-SDR(apt, 소프트 수신기).

### A2.0 검증 완료 (2026-06-26)

`docker run --rm -e DUR=120 dah-sdr` (= `rf/sdr/run_decode.sh`):
- gps-sdr-sim이 좌표 37.5665,126.978,30 의 L1 I/Q 생성(8-bit, 2.6 MHz, 샘플 궤도력 `brdc0010.22n`)
- GNSS-SDR가 위성 8개 포착·추적·항법해독·PVT →
  `Lat=37.566504, Long=126.977995, Height≈34m` (입력과 일치, 수 m 오차)
- 120s 신호를 13s에 처리(실시간보다 빠름)
- 주의: NMEA 파일 미생성 → 위치는 stdout `Position at ... Lat=.. Long=..` 로 파싱(A2.2).

### A2.2 검증 완료 (2026-06-27)

`sdr_to_gps.py`가 GNSS-SDR 디코드 위치를 `GPS_INPUT`으로 FC에 공급:
- 좌표 37.60,127.00 의 I/Q → 디코드 77개 → 중앙값 37.600005,126.999996 → FC GPS `fix=3 lat=37.600007 lon=126.999997`
- A1 home(37.5665)과 달라 **I/Q 디코드 경로임을 명확히 입증**.

**구성:** `run_channel.sh` = gps-sdr-sim 생성 → `sdr_to_gps.py`(gnss-sdr 디코드 → GPS_INPUT 5Hz).

**중요 설정/주의:**
- `gnss-sdr.conf`: `Channels.in_acquisition=8`(병렬 포착) 필수 — `=1`이면 포착이 느려 PVT가 신호 안에 못 풀려 *간헐 실패*.
- `DUR=180`(신호 길이) 마진 확보. 첫 PVT가 늦게 나오므로 짧으면 실패.
- `sdr_to_gps`는 gnss-sdr를 **shell 리다이렉트**로 호출(파이썬 파일객체 stdout이면 PVT 미산출 현상 있었음).

### 운영 모델: A1(라이브) vs A2(I/Q) — GPS 소스 택일

| 모드 | GPS 소스 | 가동 |
|---|---|---|
| **A1 라이브** (기본) | SITL 진짜위치 추종 (`dah-gnss`) | `docker compose up -d` |
| **A2 I/Q** | 디코드된 정적 좌표 (`dah-sdr`) | `docker compose stop gnss` 후 `docker compose --profile iq up -d sdr` (좌표=`IQ_LAT/IQ_LON`) |

둘은 같은 GPS 소스라 **동시 가동 금지**.

### 사용자 공격면 (A2 완료 후)

**사용자가** 별도 `gps-sdr-sim`(가짜 좌표) I/Q를 채널에 주입 → GNSS-SDR가 가짜를 디코드 → FC가 속음(스푸핑).
잡음 주입 → GNSS-SDR 락 상실 → FC GPS 상실(재밍). (수신기는 받은 I/Q를 충실히 디코드만 함)

## C2 링크 채널 (B) — `rf/channel/`

지상↔UAV **C2/텔레메트리 무선 링크**를 모델링하는 채널 에뮬레이터(`dah-c2channel`, 172.28.0.50).
router↔air:5760 사이에 삽입되어 MAVLink 메시지 단위 **손실(=재밍)**을 적용한다.
**GPS_INPUT(#232)은 면제** — GPS는 UAV 온보드라 C2 링크와 독립.

### 다중링크 + failover (B.1) + 지연 (B.2)

- **primary**(위성/LTE, 지연 300ms) + **secondary**(직접RF, 지연 50ms) 두 링크.
- active 링크 무응답(하트비트 미전달 3s) → **자동 failover**, primary 회복 → **자동 failback**.
- 메시지 단위 손실(=재밍) + 링크별 지연. GPS_INPUT은 손실·지연 면제.

### 재밍 (사용자가 직접)

```bash
echo 0.95 > rf/channel/ctrl/jam_primary     # primary 강재밍 → secondary로 failover
echo 0    > rf/channel/ctrl/jam_primary     # 해제 → primary로 failback
echo 0.95 > rf/channel/ctrl/jam_secondary   # 둘 다 막으면 통신 두절
```

### 검증 완료 (2026-06-27)

| 단계 | HEARTBEAT | 채널 로그 |
|---|---|---|
| 정상 | 1.0 Hz (primary) | — |
| **primary 재밍 0.95** | **1.0 Hz 유지** | `FAILOVER → secondary` |
| primary 해제 | 1.0 Hz | `FAILBACK → primary` |

→ **재밍→자동 failover→통신 유지** + GPS 면제(두 채널 독립) 입증. B.0/B.1/B.2 완료.

## 알려진 이슈 (검증 2026-06-26)

- **GPS 센서 health 비트 off** (`scripts/verify_all.py` WARN): `GPS_TYPE=14`(외부 MAV GPS)에선
  SYS_STATUS의 GPS health 비트가 켜지지 않는다. **fix=3·EKF 정상·ARM 성공**이라 *기능엔 지장 없음*.
  GPS_INPUT에 GPS 시각을 넣어도 해소 안 됨 → ArduPilot MAV GPS health 보고 특성으로 판단.

## 참고

- `_medium.log` 는 채널 실행 로그(임시, 호스트 수동 실행 시).
- 파라미터 변경(`GPS_TYPE`,`SIM_GPS_DISABLE`)은 FC에 적용된 상태이며 재부팅 시 유지.
  정상 SITL로 되돌리려면 `GPS_TYPE=1`, `SIM_GPS_DISABLE=0` 으로 복구 후 재부팅.
