# _deprecated — multi-eNB 전환으로 대체된 산출물 (2026-07-01)

검증 과정에서 **multi-eNB 토폴로지**(브로커 회피)와 **upstream docker_open5gs 메커니즘 재사용**으로
구현이 바뀌면서 아래 파일들이 대체됨. 보존만 하며 working 파이프라인에서 미참조. 안전히 삭제 가능.

| 파일 | 무엇이었나 | 무엇으로 대체됨 |
|---|---|---|
| `docker-compose.4g.yml` | 옛 멀티UE = **1 eNB + gr-broker**(GNU Radio) 안 | **multi-eNB**: `scripts/30-add-ue.sh N` (eNB+UE 쌍 N개, 브로커 불요) + upstream `srsenb_zmq.yaml`/`srsue_zmq.yaml` |
| `bridge.4g.yml` | 옛 SITL↔UE netns 브리지(B1/B2/B3 설계) | `scripts/40-g1-c2.sh` (`docker run --network container:srsue_zmq`) + `scripts/50-g2b-gps.sh` (GPS off-셀룰러) |
| `srsran/enb.conf` | 손수 짠 srsenb ZMQ 설정(발산본) | upstream `srslte/enb_zmq.conf` + `srslte_init.sh`(COMPONENT_NAME) |
| `srsran/ue.conf.template` | 손수 짠 srsue 템플릿 | upstream `srslte/ue_zmq.conf` (+ 30-add-ue.sh 가 N별 생성) |
| `srsran/user_db.csv` | 옛 가입자 3명(IMSI 001010000000001~3, K=465B…) | `provision.sh`(UE1 from .env, OPc 계산) + `30-add-ue.sh`(UE_N) |
| `scripts/_detect-dbctl.sh` | bootstrap 의 open5gs-dbctl 컨테이너 자동탐지 | `provision.sh` 가 webui 컨테이너 dbctl 직접 사용 |
| `scripts/wait-tun.sh` | tun_srsue 생성 대기 헬퍼(브리지 순서용) | `20-ran-up.sh`/`30-add-ue.sh` 가 자체 attach 폴링 |
| `gps-external.parm` | SIM_GPS_DISABLE/GPS_TYPE 오버레이(파일) | `50-g2b-gps.sh` 가 SITL 기동 시 인라인 작성 |

> 핵심 교훈: 멀티UE를 GNU Radio 브로커(최대 난점)로 풀려던 초기안 → **eNB를 UE 수만큼**(multi-eNB)으로
> 우회. 각 쌍은 검증된 단일 UE 구성이라 안정적. 상세: 상위 `dah/4G_UAV_프로젝트_현황.md`.
