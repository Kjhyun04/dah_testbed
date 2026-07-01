# 4G/LTE UAV 셀룰러 C2 보안 — 프로젝트 현황 (2026-06-30)

> **다음 세션 시작점**: 이 문서를 먼저 읽고 이어갈 것. 셀룰러(4G) UAV C2 공격/방어 테스트베드 워크스트림.
> 기존 `testbed/PROJECT_STATUS.md`(브로드캐스트 MAVLink testbed)와 **별개의 새 워크스트림**.

---

## 0. TL;DR — 지금 어디까지 왔나
- **목표**: 방산 환경(셀룰러 연결 드론) 취약점을 **시나리오화 + 소프트웨어로 검증**. 실증근거 = **Operation Spiderweb**(실 4G 작전).
- **학술근거**: Sonaglio et al.(ITA + Northeastern) — *"Impact of 5G SA Logical Vulnerabilities on UAV Communications"* & *"When Connectivity Is Not Enough: Cross-Layer Attacks on UAV C2 over 5G"* (arXiv:2603.04662). **TM1/TM2/TM3 위협모델의 출처.** 논문 테스트베드는 5G/UERANSIM → 본 구현은 4G/srsRAN 적응(TM2는 SBI→PFCP 대체).
- **구현 타깃 = 4G/LTE** (5G 아님). Open5GS **EPC** + **srsRAN(ZMQ)** + MAVLink C2.
- **설계·문서 완료**, **실제 기동은 미착수**(셸 차단으로 로컬 불가 → **EC2에서 G0부터**).
- **★구현 환경 = 로컬 Docker 로 전환(2026-06-30)**: AWS EC2 아님. **WSL2 Ubuntu + Docker Desktop**.
  - 로컬 가능성 검증 완료: WSL2 커널(6.6.114.1)에 **sctp.ko 존재** → `modprobe sctp` 시 **컨테이너가 SCTP 인식**(MME S1AP 가능, busybox로 실증). `/dev/net/tun` ✅.
  - **★자원 실측 정정(2026-07-01)**: 이 장비는 **물리 4코어/8스레드 · 15.7GB RAM** (문서 초안의 "12 vCPU/15.4GB"는 오기). CPU는 이미 8스레드 전부 WSL 할당 → **증설 불가**. WSL 기본 RAM(50%≈7.7GB)이 캡에 근접해 불안정 → `~/.wslconfig` 로 **memory=12GB** 상향.
  - **운영 주의**: sctp 는 **WSL2 VM 재시작 시 휘발**(Docker Desktop 재시작이 VM 재시작 유발) → prep 재실행 필요. 순서=Docker Desktop 먼저↑ → sctp 로드 → EPC.
  - **선행 1회(GUI)**: Docker Desktop ▸ Resources ▸ WSL integration ▸ `Ubuntu` ON (사용자 토글).
- **★A(게이트0 환경) 자동화 완료**: `bootstrap.sh` 가 WSL 자동감지 → `00-local-prep.sh`(docker→sctp→tun)→A2(EPC+`.env.4g` 자동생성)→A3(가입자 등록).
- **★G0 통과(2026-07-01, 실측 검증)**: EPC(슬림 9서비스) + srsenb + srsue 단일 UE **attach 성공** — `tun_srsue=192.168.100.2`, MME `Attach complete`, 게이트웨이 ping OK. 전 체인(ZMQ라디오→S1AP→S6a→베어러) 실동작 확인.
  - 검증 중 발견·수정한 실버그 2개(스크립트 반영): ① Windows clone **CRLF**로 init `.sh` shebang 깨짐 → `core.autocrlf=false`+LF정규화+이미지재빌드. ② 슬림 EPC에서 MME가 없는 **osmomsc(SGsAP/VLR)에 30s 블로킹** → `mme.yaml` sgsap 블록 자동 제거.
  - 추가 발견: srsRAN **ZMQ는 eNB→UE 순서 깨끗한 기동 필수**(단편 재시작 시 desync) → `20-ran-up.sh`가 `--force-recreate`.
- **★멀티UE + UE-to-UE 통과(2026-07-01, 실측)**: **multi-eNB 토폴로지로 브로커 회피 성공.** UE2(GCS, 별도 eNB enb_id=0x19C)가 같은 EPC에 attach(192.168.100.3). **UE-to-UE ping 양방향 0% loss**(.2↔.3, PGW hairpin) → **TM1(동거주입)·C2 전제 충족.** 스크립트 `30-add-ue.sh <N>`로 재현(쌍 N 추가).
  - 두 최대 리스크 동시 해소: ①멀티UE 브로커 → multi-eNB로 우회. ②UE-to-UE 도달성 → UPF 기본 허용(손질 불요).
  - RTT~60ms = ZMQ SW경로(전이간극, 실 RTT 아님).
- **★G1 통과(2026-07-01, 실측)**: ArduPilot SITL(arducopter --model quad, Gazebo 불요)을 UAV-UE netns에 띄워 MAVLink UDP를 GCS-UE로 송출. GCS(pymavlink, GCS-UE netns): **다운링크 HEARTBEAT(sysid=1 QUADROTOR ArduPilotMega) 수신 + 업링크 REQUEST_AUTOPILOT_CAPABILITIES→COMMAND_ACK** → **양방향 MAVLink C2-over-LTE 성립.** 재현: `40-g1-c2.sh`.
  - 192.168.100.0/24 라우팅이 tun_srsue 경유 → C2가 셀룰러 베어러로 흐름(점대점, 기존 testbed의 브로드캐스트 모델과 다름).
  - **공격 표면 실재화**: TM1(rogue UE→UAV-UE:14550 주입)·TM3(eNB GTP-U 내 MAVLink 변조) 대상 = 이 SITL.
- **★G2 완전 통과(2026-07-01, 실측) — 테스트베드 핵심 완성.**
  - **G2-A 폐루프**: GCS가 셀룰러 C2로 arm→takeoff(9.1m)→land→disarm 완주.
  - **G2-B GPS off-셀룰러**: GPS를 dahnet(비셀룰러) 주입기로 공급(fix_type=3, sats=14). uav-ue 멀티네트워크(EPC망+dahnet), SITL `SIM_GPS_DISABLE=1/GPS_TYPE=14`, serial0=C2(셀룰러)/serial2=GPS(dahnet). 재현 `50-g2b-gps.sh`+`gps_inject.py`.
  - **통합**: GPS=dahnet + C2=셀룰러 **동시**로 폐루프 비행 완주 ✅.
  - 발견: ArduPilot GPS 헬스 freshness 임계 245ms → GPS_INPUT **10Hz**(100ms) 주입 필요("GPS not healthy" 해소).
- **검증 완료(전부 실측)**: G0 attach · multi-eNB 멀티UE · UE-to-UE(ICMP·UDP) · G1 C2-over-LTE · G2 폐루프+GPS off-셀룰러. **셀룰러 C2 드론 폐루프 = 동작.**
- **★fresh-clone 재현 통과(2026-07-01)**: 깨끗한 새 clone에서 수동편집 0, 스크립트만으로 **EPC + 3 UE(UAV .2/GCS .3/ROGUE .4)** 재현. CRLF 없음·sgsap 자동패치 확인. UE-to-UE 동거 메시 전부 도달(TM1 전제). → **스크립트 self-contained·재현성 입증.** (단 3eNB+3UE+기존7 동시 가동 시 RTT 자원경합 — 본격 측정 시 기존 testbed 정지.)
- **★로컬 재검증 + 실측 수정(2026-07-01, 2세션)**: 깨끗한 로컬 기동 중 실버그 3개 발견·영구수정, G0/G1 재검증 통과(UAV `.2`/GCS `.3`, UE-to-UE 0% loss, C2-over-LTE 양방향).
  - ① **air CRLF**: `air/start-sitl.sh` shebang 이 Windows 체크아웃(autocrlf)으로 CRLF → Docker COPY 후 `exec: no such file or directory` 크래시(Restarting 255). → **`.gitattributes`(eol=lf) + core.autocrlf=false** 로 영구방지.
  - ② **OPc auth 불일치**: EPC init 이 UE1(IMSI …895)을 `opc=raw-OP`(1111…)로 선등록 → srsUE 는 OP 로 OPc 유도 → attach 시 **`Network authentication failure`**(G0 미통과). → `provision.sh` 가 등록 전 **remove 선행**(유도 OPc 로 재등록) 영구수정. (pair2/3 은 `30-add-ue` 가 유도 OPc 등록이라 정상이었음 — pair1 만 init 선등록에 걸림.)
  - ③ **attach 오탐**: CPU 포화 시 attach 가 60s 초과 → `20-ran-up`/`30-add-ue` 대기 **60→120s**.
  - **★하드웨어 한계 = 동시 쌍 수 제한**: 4코어/8스레드에서 **3쌍(srsRAN 6프로세스)은 CPU 기아**로 NAS 트랜잭션 타임아웃(MME `Failure in transaction`) → attach bounce. **운용 규칙: 평상시 2쌍(UAV+GCS), ROGUE(pair3)는 TM1 때만 잠깐**. (`33` 항의 "3eNB+3UE 동시" 는 이 장비에선 불안정.)
  - **신규 산출물**: Gazebo 시각화(`gazebo/srsue_zmq.gazebo.override.yaml` + `scripts/45-g1-gazebo.sh`, noVNC `:6080`) · 공격 실습 가이드(`docs/testbed-4g_공격실습_가이드.html`, TM1/TM2/TM3 절차·컨테이너·명령·판정·원복).
- **다음(공격/방어 = 사용자 역할)**: TM1(rogue UE→UAV-UE:14550 주입) · TM3(eNB GTP-U 변조) · MAVLink v2 서명(방어) · GPS 스푸핑(주입기 좌표 조작). 인프라는 준비됨.

---

## 1. 목표 & 원칙 (불변)
- **방산 취약점 시나리오화 + SW 검증.** 단 **전이간극** 명시(아날로그 검증 ≠ 실물 취약 증명).
- **증거등급**: 실증🟢 / 원리🟡 / 가정🔴 / 조건부🟣.
- **역할경계(중요)**: 나(AI)는 **인프라/환경/배선만 구축**. **공격 실행은 사용자.** (Red/Blue 자동화 금지.)
- **GPS는 셀룰러에 안 태움**(직접 센서 입력). C2(+선택 페이로드)만 셀룰러.

---

## 2. 핵심 결정 이력 (왜 이렇게 왔나)
1. **버퍼오버플로우 → 폐기.** MAVLink 프레이밍은 LEN≤255 고정버퍼로 BOF 표면 사실상 없음. **옳은 표적 = 인증부재(CWE-306)·무결성부재**. (BOF는 저ROI.)
2. **"독자 프로토콜 RE AI 에이전트" → 거대 버전 폐기.** 그라운드트루스 역설·PHY 벽·오라클 문제. 살아남는 것 = 알려진 파서 퍼징 + 적응형 공격(감독자 LLM, RL 아님).
3. **Spiderweb 근거 발견.** Operation Spiderweb(Pavutyna, 2025-06-01): SBU가 **ArduPilot+RaspberryPi+LTE모뎀**으로 **적(러)의 셀룰러망**을 C2로 써 러 전략폭격기 타격. → "MAVLink C2를 적 셀룰러망 위로"는 실증된 군사 패턴. **공격자 위치 역전**: 망 소유자(방어자)가 자연히 TM1/2/3 위치.
4. **★4G 피벗.** Spiderweb=4G/LTE. 따라서 **구현 타깃을 5G→4G로 전환**. 5G는 미래 확장(5G NTN)으로 강등.
5. **★TM2 정정.** Open5GS EPC는 **CUPS** → Sxa/Sxb에 **PFCP 존재** → **PFCP 세션삭제는 4G에서도 가능**. 5G 전용은 **SBI/HTTP2 NF-크래시뿐**(EPC에 SBA 없음).

---

## 3. 산출물 맵 (전부 `dah/` 하위)
| 파일 | 내용 | 상태 |
|---|---|---|
| `5G_UAS_TS22125_쉬운설명.html` | 3GPP TS 22.125(셀룰러 UAS 요구사항) 쉬운 해설 | ✅ 에이전트 검증 |
| `5G_UAV_CrossLayer_논문참고분석.html` | 논문 2편(arXiv 2603.04662 v1/v4) 참고분석 + TM1/2/3 | ✅ 검증·4G라벨 정정 |
| `5G_UAV_CyberSec_Guide.html` | 핵심 가이드 — **4G/LTE로 전면 전환 완료** | ✅ (TM2 정정·SBI 제외 명시) |
| `testbed-5g_설계.md` + `testbed-5g/` | 5G 설계(UERANSIM+5GC) | 🟡 보존(피벗 전, 참조용) |
| `testbed-4g_설계.md` | **4G 설계 + 공격 4G 수행가능성 검증** | ✅ 현행 |
| `testbed-4g/` | **4G 실제 산출물**(compose·srsRAN·bridge·scripts) | ✅ v0(EC2 튜닝 전제) |
| `4G_UAV_프로젝트_현황.md` | ← 이 문서 | ✅ |

> 파일명이 `5G_`로 시작해도 가이드/논문분석은 **내용상 4G로 정정됨**(파일명만 잔존).

---

## 4. 4G 스택 & 공격 수행가능성 (검증됨)

**스택**: Open5GS EPC(MME·SGW·PGW·HSS·PCRF, CUPS) + srsRAN(srsenb/srsue) over **ZMQ** + GNU Radio broker(멀티UE). 베이스 = `herlesupreeth/docker_open5gs`.

**매핑**: gNB→**eNB** · N3→**S1-U** · N4→**Sxa/Sxb** · UPF→**PGW/SGW** · AMF→**MME** · 슬라이스/DNN→**APN**. (GTP-U·PDCP·PFCP는 4G·5G 동일.)

| 공격 | 4G | 형태 |
|---|---|---|
| **TM1** 동거 UE 주입 | ✅ | 같은 APN/PGW UE-to-UE → SysID 255 사칭 주입(CWE-306) |
| **TM2(a)** PFCP 세션삭제 | ✅ | EPC=CUPS → Sxa/Sxb PFCP(8805) → 베어러 철거 → failsafe |
| **TM2(b)** SBI NF-크래시 | 🔴 **제외** | EPC에 SBA 없음 → 4G 부재(혼란방지 위해 문서에서 제외 명시) |
| **TM3** 탈취 eNB GTP-U 변조 | ✅ **최충실** | eNB PDCP 종단 + S1-U GTP-U → Spiderweb 직결 |
| **MAVLink 전 시나리오·서명·GPS** | ✅ | 앱/센서 계층, 세대 무관 |
| (덤) MME/Diameter/GTP-C | 🟡 | 4G 신규 공격면(별도 분석 여지) |

---

## 5. 적대검증 발견 (B1/B2/B3) — 4G 설계에 반영 완료
- **B1**: 크로스-compose netns는 `service:` 불가 → **`network_mode: "container:dah4g-uav-ue"`**.
- **B2**: srsue를 **EPC망 + dahnet 멀티네트워크** → GPS_INPUT(dahnet)/C2(tun_srsue) 분리.
- **B3**: SITL serial0(TCP5760)만으론 주입 불가 → **UDP MAVLink 엔드포인트**(`--serial1=udpclient:GCS_UE_IP:14550`) 명시.
- (공격) A1: SITL 주입은 위 B3 UDP 엔드포인트 전제. A2: REQUEST_DATA_STREAM은 "직렬포트"가 아니라 IP 대역 포화(정정됨).

---

## 6. 현재 상태
- **설계·문서·v0 산출물 = 완료.** **실기동 = 0%**(로컬 셸 차단, docker 없음 → EC2 필요).
- 기존 `testbed/`(브로드캐스트 MAVLink, ArduPilot SITL+Gazebo+서명)는 **git push 완료**(`github.com/Kjhyun04/dah_testbed`, main). **4G/5G와 무관**(셀룰러 모델 아님).
- `testbed-4g/`·`testbed-5g/`·HTML·현황문서는 **git 밖**(`dah/testbed/` 저장소 외) → 필요 시 별도 버전관리.

---

## 7. 다음 단계 (EC2에서)
**A(1~3단계)는 `bash bootstrap.sh` 한 줄로 자동화됨**(아래는 그 내부 단계 = 수동 등가):
1. **EC2**(c5.2xlarge/Ubuntu, SSH-only) → `scripts/00-ec2-prep.sh`(docker+`modprobe sctp`+`/dev/net/tun`).
2. `scripts/10-epc-up.sh`: `git clone herlesupreeth/docker_open5gs` → **EPC 기동** → 네트워크명·**MME IP**·이미지·ENB_IP 자동탐지 → `.env.4g` 자동생성.
3. `scripts/provision.sh`(DBCTL 자동탐지) → HSS에 IMSI 3개(001010000000001~3) 등록.
4. **3-A 단일 UE**(broker 불필요)로 **G0**: `srsue` attach + `tun_srsue` IP + **UAV-UE→GCS-UE ping**(셀룰러 경유). ← **4G 기질 게이트**. (A 이후 첫 수동 검증 지점.)
5. 통과 후 **3-B 멀티UE**(GNU Radio broker) → `bridge.4g.yml`로 **G1**(C2-over-LTE) → **G2**(폐루프 + GPS off-셀룰러).
6. EC2 실측값(네트워크명·MME IP·이미지 태그·broker 동작)으로 config·broker·bridge 정밀화.

---

## 8. 미결 / 리스크 (정직)
- **★멀티UE ZMQ broker** = 최대 난점. 단일 UE는 쉬움. 3 UE(TM1 동거)는 GNU Radio 정합 튜닝 필요. docker_open5gs 예제 확인.
- srsRAN config·ZMQ 포트·IP·이미지 태그 = **EC2에서 확정**(현재 플레이스홀더).
- srsRAN 4G는 유지보수 모드(버전 확인). ZMQ=RF 시뮬(deterministic).
- 자원: 풀스택은 **c5.2xlarge** 권장. 5G 실험·Gazebo는 5G 트랙 폐기로 불요(C2 검증엔 SITL만).

---

## 9. 환경 메모 (다음 세션 운영)
- **로컬 셸/외부파일/웹**: auto 모드 분류기가 **간헐 차단**(fail-closed). `dah/` 안 파일 쓰기는 허용. 셸 필요 시 사용자가 `! <cmd>` 또는 Shift+Tab/`/permissions`.
- 권한: `dah/.claude/settings.local.json`에 git·docker·python·web allow 규칙 추가됨(사용자).
- **OS=Windows**(로컬). 테스트베드 = **로컬 Docker(WSL2 Ubuntu + Docker Desktop)** 로 확정(EC2 폐기, 스크립트는 fallback 보존). Docker Desktop client v29.5.2 설치됨.
- **WSL integration(Ubuntu) 토글 ON** 이 선행조건(미설정 시 Ubuntu 셸에서 docker 데몬 연결 불가 — 실측 확인).
- 역할경계 재확인: **인프라만, 공격은 사용자.**
