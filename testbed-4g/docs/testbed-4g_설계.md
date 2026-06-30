# testbed-4g 설계 v0 — Open5GS EPC + srsRAN(ZMQ) 위 MAVLink C2

> 작성 2026-06-30 · **구현 타깃 = 4G/LTE (Spiderweb 충실)**. 5G는 "미래 확장(5G NTN)"으로 강등.
> 베이스 재사용: `herlesupreeth/docker_open5gs`(**EPC + srsRAN-ZMQ 포함**) → 5G-SA+UERANSIM 대신 **EPC+srsRAN** 스왑.
> 역할경계: **인프라/배선만 구축, 공격 실행은 사용자**. 앞 적대검증의 **B1·B2·B3 수정 반영**.

---

## 1. 4G 스택 & 5G→4G 매핑

| 5G(폐기) | **4G(채택)** | 비고 |
|---|---|---|
| UERANSIM(gNB/UE) | **srsRAN** (srsenb / srsue) | LTE RAN·UE |
| (시뮬 RF) | **ZMQ 가상 라디오** | HW/SDR 없이 srsue↔srsenb |
| Open5GS 5GC | **Open5GS EPC** | MME·SGW·PGW·HSS·PCRF |
| gNB | **eNB**(srsenb) | PDCP 종단 동일 |
| N3 GTP-U | **S1-U GTP-U** (UDP 2152) | 동일 프로토콜 |
| AMF | **MME** | S1AP **SCTP 36412**, Diameter S6a |
| UPF/SMF | **PGW-U/PGW-C(=UPF/SMF)** | Open5GS는 CUPS |
| N4 PFCP | **Sxa/Sxb PFCP** (UDP 8805) | CUPS → PFCP 존재(★TM2 함의) |
| 슬라이스/DNN | **APN** | 논리망 |

---

## 2. 목표 아키텍처

```
 GPS 채널 A  gnss/sdr ──GPS_INPUT(dahnet, 셀룰러 안 탐)──► ArduPilot SITL
                                                            │ MAVLink C2 (UDP, tun_srsue)
   [UAV측]  uav-ue(srsue, tun_srsue) ──ZMQ──► srsenb ──┐
                                          (GNU Radio broker로 멀티UE 합성)  │ S1-U GTP-U(2152)
                                              ┌─────────▼──────────┐
                                              │  Open5GS EPC       │
                                              │  SGW-U◄Sxa(PFCP)─SGW-C
                                              │  PGW-U/UPF◄Sxb(PFCP)─PGW-C/SMF
                                              │  MME(S1AP/S6a) · HSS · PCRF
                                              └─────────▲──────────┘
   [GCS측]  gcs-ue(srsue, tun_srsue) ──ZMQ──► srsenb ──┘
                ▲ netns 공유                              (TM3: eNB가 S1-U 평문 구간)
            gcs_cli(GCS)
   [공격]  rogue-ue(srsue) — TM1 동거 UE
```

---

## 3. 서비스 인벤토리

### 신규 — Open5GS EPC
`mongo` · `hss` · `pcrf` · `mme` · `sgwc` · `sgwu` · `smf` · `upf`  (SMF/UPF = PGW-C/PGW-U 역할. NRF 불필요 — 5GC 전용)

### 신규 — srsRAN(ZMQ)
`srsenb`(eNB) · `uav-ue`/`gcs-ue`/`rogue-ue`(srsue) · **`gr-broker`(GNU Radio, 멀티UE ZMQ 합성)**

### 유지(기존 testbed) — 무변경
`air`(SITL) · `gnss`/`sdr`(GPS A) · `payload`/`video`(C) · `tools`(gcs_cli) · `logviewer`

---

## 4. ★핵심 구현 이슈 (가장 큰 난점부터)

**[★최대 난점] srsRAN-ZMQ 멀티 UE = GNU Radio broker 필요.**
UERANSIM은 UE를 독립 프로세스로 무한정 띄웠지만, **srsRAN ZMQ는 단일 srsue↔srsenb 가상 RF가 기본**이다. UAV/GCS/ROGUE **3 UE를 한 eNB에** 붙이려면 **GNU Radio 기반 broker로 ZMQ 스트림을 합성/분배**해야 한다(샘플레이트·tx/rx 포트 정합 까다로움). → docker_open5gs의 srsRAN-ZMQ 멀티UE 예제(GNU Radio 브로커)를 차용·확인.
- 대안: TM3만 우선이면 UAV 1 + GCS 1(2 UE)로 최소화. TM1(동거)엔 3번째(rogue) 필요.

**[B1 수정] netns 공유는 `container:` 로.** `air`(기존 testbed compose)와 `uav-ue`(testbed-4g compose)는 다른 프로젝트 → `network_mode: "service:"` 불가. **`network_mode: "container:dah4g-uav-ue"`** 사용(또는 air를 4g compose로 합침).

**[B2 수정] srsue를 dahnet에도 연결.** GPS off-셀룰러가 성립하려면 `uav-ue`/`gcs-ue`가 **EPC망 + dahnet 둘 다**에 붙어야 함(멀티 네트워크). 그래야 air가 그 netns 공유 시 **C2=tun_srsue / GPS_INPUT=dahnet** 분리.

**[B3 수정] SITL의 UDP MAVLink 엔드포인트 명시.** SITL serial0(TCP 5760)만으론 주입 안 됨. **`--serial1=udpclient:<GCS_UE_IP>:14550`**(또는 UE netns에 mavlink-router)로 **tun_srsue 상의 UDP C2 엔드포인트**를 연다. GCS는 UAV-UE IP로, rogue도 동일 포트로 도달.

---

## 5. EPC 설정값 & 가입자

- **PLMN** `MCC 001 / MNC 01`(또는 999/70 테스트), **APN** `internet`(IPv4 풀 보통 10.45.0.0/16), **TAC** 7.
- srsenb: `mme_addr`(MME IP), `gtp_bind_addr`(S1-U), `s1c_bind_addr`, `enb_id`, mcc/mnc/tac, `device_name=zmq` + `device_args`(tx/rx ZMQ 포트).
- srsue ×3: `usim`(imsi/k/opc/imei), `rat.eutra`, `device_args=zmq`(broker 포트), `apn`.
- 가입자: **HSS(MongoDB)** 에 IMSI 3개 등록(`open5gs-dbctl` 또는 WebUI) — srsue `user_db.csv`/config와 key/opc 일치.

---

## 6. 검증 게이트 (G0~G2)

- **G0 — LTE 기질:** srsue 2개 `RRC connected`+`기본 EPS 베어러`+`tun_srsue` IP 할당 → `uav-ue → gcs-ue` **ping(셀룰러 경유)**. (srsenb S1-U GTP-U 2152 tcpdump 교차.)
- **G1 — C2-over-LTE:** SITL의 UDP C2가 tun_srsue로 GCS-UE IP 왕복(gcs_cli ACK). (B3 엔드포인트 동작 확인.)
- **G2 — 폐루프 + GPS off-셀룰러:** GPS_INPUT=dahnet, C2=LTE 동시 정상 + mode→arm→takeoff→land + EKF 추종.

---

## 7. ★공격 기법 — 4G 수행가능성 검증 (두 번째 핵심)

| 공격 | 4G 수행? | 근거 / 4G에서의 형태 |
|---|---|---|
| **TM1** 동거 UE → MAVLink 주입 | ✅ **가능** | 같은 **APN/PGW** 풀 → UE-to-UE 도달(PGW hairpin) → SysID 255 사칭 주입. CWE-306은 앱 계층. (A1 엔드포인트·PGW UE-to-UE 허용 전제 — G0가 검증) |
| **TM2(a)** PFCP 세션삭제 | ✅ **가능** | **Open5GS EPC=CUPS → Sxa/Sxb가 PFCP(UDP 8805)**. 세션 삭제 flood → PDN 베어러 철거 → C2 두절 → failsafe. (논문① TM2가 4G로 전이) |
| **TM2(b)** SBI NF 크래시 | 🔴 **불가** | EPC엔 **SBA/NRF/SMF-HTTP2 없음** → 논문② TM2(NRF/SMF 크래시·CrashLoop)는 4G에 등가 없음 |
| **TM2(c)** 4G-native | 🟡 **다른 벡터** | **MME**(S1AP/SCTP malformed)·**Diameter S6a**(HSS)·**GTP-C(S11/S5)** 조작 — 가능하나 *다른* 취약점(별도 분석 필요) |
| **TM3** 탈취 eNB → GTP-U 변조 | ✅ **가능(최충실)** | **srsenb가 PDCP 종단** → 이후 **S1-U GTP-U(동일 프로토콜) 평문** → iptables NFQUEUE로 MAVLink 변조. Spiderweb(4G)에 *가장 직결* |
| **MAVLink 시나리오** (force-DISARM·RC·PARAM_SET·웨이포인트·DoS) | ✅ **가능** | 앱 계층, IP 위. 세대 무관(A1 엔드포인트 동일) |
| **GPS 스푸핑/재밍** | ✅ **가능** | 센서/물리 계층, 세대 무관 |
| **MAVLink 서명(방어)** | ✅ **동일** | 앱 계층 종단 무결성 — 4G에서도 유일 완전 방어 |

### 검증 결론
- **대부분의 공격이 4G에서 그대로 성립.** TM1·TM3·MAVLink 전부·서명방어 = ✅.
- **★중요 정정:** **TM2의 PFCP 세션삭제는 4G에서도 가능**하다 — Open5GS EPC가 **CUPS**라 Sxa/Sxb에 PFCP가 있기 때문. 내가 앞서 단 "**TM2 🔴 5G 전용**" 라벨은 **과했다** → 정확히는 *"PFCP 가용성 공격은 4G(CUPS-EPC) 가능 / **SBI HTTP2 NF-크래시만** 5G 전용"*.
- **4G가 오히려 TM3에 더 충실**(Spiderweb이 4G였으므로).
- **4G 신규 면**: MME/Diameter/GTP-C는 5G엔 없던 *추가* 공격면 → 4G 전환의 *덤*.

---

## 8. 미결 / 한계 (정직)

- **srsRAN-ZMQ 멀티UE(GNU Radio broker)** = 최대 구현 리스크. EC2에서 우선 검증(2 UE → 3 UE).
- srsenb/srsue config·ZMQ 포트·broker는 **EC2에서 docker_open5gs 예제 기반 튜닝**(여기선 설계).
- srsRAN 4G는 유지보수 모드(srsRAN Project는 5G) — LTE 테스트엔 여전히 동작하나 버전 확인.
- B1/B2/B3 수정은 설계에 반영, 실제 compose/config는 다음 산출물.
- 자원: EPC+srsenb+srsue×3+broker(+SITL) → **c5.2xlarge** 권장. **5G 트랙은 폐기**, Gazebo는 비행 시각화에만.

---

## 9. 다음 산출물
`testbed-4g/`: **docker-compose.4g.yml**(EPC+srsenb+srsue×3+gr-broker, B1/B2/B3 배선) · **srsenb/{enb,rr,sib,rb}.conf** · **srsue/ue-*.conf** · **user_db**(IMSI 3) · **bridge**(air↔uav-ue `container:` netns) · provision/wait 스크립트.
> 라벨 정정 필요: 기존 5G 문서들의 "TM2 🔴 5G 전용" → "**PFCP는 4G 가능 / SBI-크래시만 5G 전용**"으로 수정.
