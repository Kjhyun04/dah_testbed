# testbed-4g — Open5GS EPC + srsRAN(ZMQ) 위 MAVLink C2 (검증됨)

셀룰러(4G/LTE) UAV 명령·제어 보안 테스트베드. **Operation Spiderweb**(실 4G 작전) + **Sonaglio et al.**
(ITA, arXiv:2603.04662, TM1/2/3) 기반. 2026-07-01 **전 게이트 로컬 실측 통과**.

> 역할경계: 이 디렉토리는 **인프라/환경/배선만**. 공격(TM1/2/3)·방어(MAVLink 서명)·GPS 스푸핑 실행은 사용자.

---

## 0. 전제 (로컬 — 채택)
**WSL2 Ubuntu + Docker Desktop.** 선행 1회: Docker Desktop ▸ Settings ▸ Resources ▸ WSL integration ▸ `Ubuntu` ON.
> 검증: WSL2 공유커널에 `sctp.ko` 존재 → `modprobe sctp` 시 컨테이너가 SCTP 인식(MME S1AP). **단 WSL2 VM 재시작 시 sctp 휘발** → prep 재실행.
> (EC2 대안도 지원: `FORCE_EC2=1`. 비-WSL이면 `00-ec2-prep.sh`(apt) 경로.)

## 1. 한 줄 부트스트랩 → G0
```bash
wsl -d Ubuntu
cd .../testbed-4g
bash bootstrap.sh        # 00-local-prep(sctp/tun) → 10-epc-up(빌드+EPC) → provision(UE1) → 20-ran-up(G0)
```
결과: EPC 코어 9서비스 + 가입자(UE1) + **UAV UE attach**(`tun_srsue` IP) = **G0**.
최초 1회 이미지 빌드(open5gs/srsRAN 컴파일) 수~십분. `.env.4g` 는 10-epc-up 이 실측값으로 자동생성.

## 2. 멀티UE → G1 → G2 (검증된 순서)
```bash
bash scripts/30-add-ue.sh 2     # GCS UE  (multi-eNB: eNB+UE 쌍 추가, 브로커 불요)
bash scripts/30-add-ue.sh 3     # ROGUE UE (TM1 동거 3대)
bash scripts/40-g1-c2.sh        # G1: ArduPilot SITL(UAV netns) ↔ GCS, 양방향 MAVLink C2 over LTE
bash scripts/50-g2b-gps.sh      # G2: GPS=dahnet(비셀룰러) + C2=셀룰러, arm→takeoff→land 폐루프
```

## 3. 핵심 설계 (검증 결과)
- **멀티UE = multi-eNB**: srsRAN ZMQ는 1 eNB=1 UE. GNU Radio 브로커(최대 난점) 대신 **eNB를 UE 수만큼**
  띄워 각 쌍을 검증된 단일 UE 구성으로. 모두 같은 EPC(MME)에 S1AP. 같은 APN 풀 → **UE-to-UE 도달**(TM1/C2 전제).
- **GPS off-셀룰러**: SITL `SIM_GPS_DISABLE=1/GPS_TYPE=14`(외부GPS). serial0=C2(tun_srsue,셀룰러)·serial2=GPS(dahnet,비셀룰러).
  `gps_inject.py` 가 SIMSTATE+VFR_HUD → GPS_INPUT **@10Hz**(헬스 임계 245ms).
- **EPC 슬림**: `4g-volte-deploy.yaml` 의 코어 9개만 `--no-deps`(IMS/osmo 제외). MME sgsap 자동제거(10-epc-up).

## 4. 파일 맵
```
testbed-4g/
  bootstrap.sh                 # 환경→G0 일괄 (WSL/EC2 자동감지)
  .env.4g.example / .env.4g    # 템플릿 / 자동생성(런타임)
  scripts/
    00-local-prep.sh           # A1(로컬) WSL2+Docker Desktop: docker→sctp→tun
    00-ec2-prep.sh             # A1(EC2 대안) apt docker/sctp/tun
    10-epc-up.sh               # A2 clone(autocrlf=false)+빌드+슬림EPC+sgsap패치 → .env.4g
    provision.sh               # A3 가입자(UE1) 등록 (OPc 계산, webui dbctl)
    20-ran-up.sh               # G0 srsenb_zmq+srsue_zmq attach+ping (upstream 메커니즘)
    30-add-ue.sh <N>           # multi-eNB: (eNB+UE) 쌍 N 추가 + UE-to-UE 검증
    40-g1-c2.sh + g1_gcs.py    # G1 MAVLink C2-over-LTE (SITL↔GCS)
    50-g2b-gps.sh + gps_inject.py  # G2-B GPS off-셀룰러 (dahnet 주입)
    g2_flight.py               # G2-A 폐루프 비행 (arm→takeoff→land)
    60-viz-gazebo.sh           # (opt-in) G2 + Gazebo 3D 시각화 — 공격을 눈으로 관측
      + sitl_gazebo_launch.sh  #   컨테이너측: SITL(--model JSON)+Gazebo+noVNC (UAV netns)
      + tcp_relay.py           #   netns 안 noVNC(:6080)를 호스트로 노출(socat 부재 대체)
    udp_test.py                # UE-to-UE UDP(14550) 전송 점검 도구
    aws-resume.sh              # (EC2) stop→start 후 재기동 원스텝 (sctp/tun→EPC→G0)
    aws-idle-autostop.sh       # (EC2) 유휴 자동 stop — 비용 가드(cron 등록)
  docs/
    AWS_SETUP.md               # 공유 EC2 프로비저닝·운영 가이드(AMI/유형/SG/터널/비용)
  _deprecated/                 # multi-eNB 전환으로 대체된 옛 산출물(broker안 등) — 삭제가능
```

## 4-B. (opt-in) Gazebo 3D 시각화 — 공격을 "눈으로"
```bash
bash scripts/60-viz-gazebo.sh        # SITL 백엔드를 Gazebo FDM 으로 교체 + noVNC 노출
# 관측: 브라우저 → http://localhost:6080/vnc.html
# 비행: docker run -i --rm --network container:srsue_zmq2 dah-testbed-air python3 - < scripts/g2_flight.py
```
- **무엇이 바뀌나**: 기본 G1/G2 는 SITL 내장물리(`--model quad`)라 **공격 증명은 텔레메트리로 충분**(SIMSTATE truth vs EKF 발산). 60 은 그 위에 **시각 증거**를 더한다 — SITL 을 `--model JSON`(Gazebo FDM)로 교체해 GCS 지도엔 "정상"인데 3D 엔 스푸핑 표류/추락이 보이게.
- **채널분리 유지**: FDM(SITL↔Gazebo, 9002/9003)은 **같은 UAV-UE netns 의 localhost** → 셀룰러에 안 태움(GPS off-셀룰러와 같은 원리). C2 만 serial0(셀룰러), GPS 만 serial2(dahnet).
- **컨테이너 이름 동일**(`dah4g-sitl`/`dah4g-gps`) → 기존 비행·TM1/2/3·GPS 스푸핑 절차 **그대로 재사용**, 관측만 추가.
- **40/50 불변**: 60 은 별도 opt-in. 검증된 기본 경로는 건드리지 않는다.
- **첫 실행 확인점**: `--model JSON`에서도 `SIMSTATE` truth(lat/lng)가 나와 `gps_inject.py`가 GPS_INPUT 을 채우는지 — 루트 testbed 비행이 성립하므로 정상일 가능성이 높으나, 60 의 GPS fix 게이트가 이를 자동 검증한다(실패 시 즉시 die).

## 5. 정직한 한계
- **전이간극**: ZMQ는 결정론적 RF 시뮬 → 프로토콜·로직 증명, 실 무선 RTT/지터 아님.
- **자원 경합**: 3 eNB+3 UE+SITL+(기존 testbed 7) 동시 가동 시 RTT 변동. 본격 측정 시 기존 testbed 정지 권장.
- **Gazebo 시각화(60) 부하**: GPU 미통과 환경은 소프트웨어 GL 렌더 → CPU 부담↑·GUI 프레임↓(물리/FDM 은 헤드리스 서버라 영향 적음). 데모는 단일 UE 권장, RTT 측정과 동시 구동은 비권장.
- **검증 환경**: 1차 검증은 git-bash(Docker Desktop) — WSL-네이티브 재현은 integration 토글 후 권장.
- srsRAN_4G 유지보수 모드(LTE 동작은 정상).
