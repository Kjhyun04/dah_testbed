#!/usr/bin/env bash
# ============================================================================
# G1+Gazebo — C2-over-LTE 를 유지한 채 SITL 물리를 Gazebo(--model JSON)로 교체하고
#             브라우저 링크(http://localhost:6080/vnc.html)로 비행을 시각화.
#
#   40-g1-c2.sh 의 Gazebo 변형. 바뀌는 것은 SITL 컨테이너 내부뿐:
#     - 물리 백엔드:  --model quad  →  --model JSON (Gazebo FDM, localhost 9002/9003)
#     - Gazebo 서버(headless) + GUI + noVNC(6080) 를 SITL 컨테이너에서 함께 기동
#     - --shm-size 1gb (Gazebo 렌더링 공유메모리)
#   바뀌지 않는 것(★확인 완료):
#     - C2 경로:  serial0 = udpclient:<GCS_UE>:14550 (셀룰러 베어러, tun_srsue) 그대로
#     - EPC / eNB / srsue 라디오·attach 설정, GCS 검증(g1_gcs.py), TM1/TM3 공격면 무변경
#     - 6080 노출은 업스트림 srsue_zmq.yaml 편집 없이 compose override 로만 추가
#
#   Gazebo 는 명령을 내리지 않는다: arm/takeoff 는 GCS(pymavlink)가 셀룰러 C2 로 보낸다.
#   Gazebo 는 물리(비행역학)+시각화만 담당하고 MAVLink 명령을 생성/주입하지 않는다.
#
#   사용:  bash 45-g1-gazebo.sh
#   전제:  pair1(srsue_zmq=UAV)+pair2(srsue_zmq2=GCS) attach 완료(30-add-ue.sh 2),
#          dah-testbed-air 이미지 존재(기존 testbed 빌드 — Gazebo 포함).
#   관측:  http://localhost:6080/vnc.html
# ============================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
log(){ printf '\033[1;36m[G1-GZ]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[G1-GZ!]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[G1-GZ✗]\033[0m %s\n' "$*" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

WORK="${WORK:-$HOME/docker_open5gs}"
ENB_YML="${ENB_YML:-srsenb_zmq.yaml}"           # pair1 eNB
UE_YML="${UE_YML:-srsue_zmq.yaml}"              # pair1 UE(=UAV)
OVERRIDE="${OVERRIDE:-$HERE/../gazebo/srsue_zmq.gazebo.override.yaml}"
UAV_UE="${UAV_UE:-srsue_zmq}"                    # pair1 = UAV
GCS_UE="${GCS_UE:-srsue_zmq2}"                   # pair2 = GCS
ENB_CT="${ENB_CT:-srsenb_zmq}"
AIR_IMG="${AIR_IMG:-dah-testbed-air}"
SITL="${SITL:-dah4g-sitl}"
GZ_HEADLESS="${GZ_HEADLESS:-0}"                  # 1이면 GUI/noVNC 생략(물리+FDM만)
HOME_LOC="${HOME_LOC:-37.5665,126.9780,30,0}"
WORLD="${WORLD:-/home/ardu/worlds/dah_world.sdf}"
ARDU=/home/ardu/ardupilot/build/sitl/bin/arducopter
DEFAULTS=/home/ardu/ardupilot/Tools/autotest/default_params/copter.parm,/home/ardu/ardupilot/Tools/autotest/default_params/gazebo-iris.parm

docker image inspect "$AIR_IMG" >/dev/null 2>&1 || die "$AIR_IMG 이미지 없음 — 기존 testbed(air, Gazebo 포함) 빌드 필요."
[[ -f "$OVERRIDE" ]] || die "override 미발견: $OVERRIDE"
docker inspect "$GCS_UE" >/dev/null 2>&1 || die "$GCS_UE(GCS) 미가동 — 30-add-ue.sh 2 먼저."

# ── 1. UAV-UE 에 6080 노출 (이미 노출돼 있으면 재생성 생략) ────────────────────
#   6080 publish 는 컨테이너 재생성이 필요. 재생성 시 ZMQ desync 방지를 위해
#   eNB→UE 순서로 '깨끗하게'(force-recreate) 다시 띄운다(20-ran-up 과 동일 원칙).
HAS_PORT="$(docker inspect "$UAV_UE" -f '{{json .NetworkSettings.Ports}}' 2>/dev/null | grep -c '6080/tcp' || true)"
if [[ "$HAS_PORT" == "0" ]]; then
  log "UAV-UE($UAV_UE) 에 6080 노출 — pair1 RAN 재생성(eNB→UE, override)"
  ( cd "$WORK" || die "$WORK 없음 — 10-epc-up.sh 먼저."
    docker compose -f "$ENB_YML" up -d --force-recreate "$ENB_CT"
    sleep 4
    docker compose -f "$UE_YML" -f "$OVERRIDE" up -d --force-recreate "$UAV_UE" )
  log "attach 대기(최대 60s): tun_srsue IP..."
  UAV_IP=""
  for i in $(seq 1 60); do
    UAV_IP="$(docker exec "$UAV_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1 || true)"
    [[ -n "$UAV_IP" ]] && break; sleep 1
  done
  [[ -n "$UAV_IP" ]] || { docker logs "$UAV_UE" 2>&1 | tail -20; die "UAV-UE 재attach 실패."; }
else
  log "UAV-UE($UAV_UE) 이미 6080 노출됨 — RAN 재생성 생략"
  UAV_IP="$(docker exec "$UAV_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1 || true)"
fi

GCS_IP="$(docker exec "$GCS_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
[[ -n "$GCS_IP" && -n "$UAV_IP" ]] || die "UE tun 미확인 — pair1/pair2 attach 확인."
log "UAV-UE=$UAV_IP  GCS-UE=$GCS_IP"

# ── 2. Gazebo + SITL 기동 (UAV-UE netns, --model JSON, serial0→GCS:14550) ──────
#   기동 순서: Xvfb → (GUI: openbox+x11vnc+noVNC) → gz sim 서버(headless,stepping)
#             → FDM 준비대기 → (GUI: gz sim -g) → arducopter --model JSON.
#   서버는 항상 headless(-s -r)로: server+GUI 결합은 SW 렌더에서 물리스텝을 막아 FDM 끊김.
docker rm -f "$SITL" >/dev/null 2>&1 || true
log "Gazebo+SITL 기동 (--model JSON, shm 1gb, GZ_HEADLESS=$GZ_HEADLESS)"
docker run -d --name "$SITL" --network "container:$UAV_UE" --shm-size 1gb "$AIR_IMG" sh -c "
  set -e
  export DISPLAY=:1
  rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true
  Xvfb :1 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
  sleep 2
  if [ \"$GZ_HEADLESS\" != \"1\" ]; then
    openbox &
    x11vnc -display :1 -nopw -forever -shared -rfbport 5900 -quiet &
    websockify --web=/usr/share/novnc 6080 localhost:5900 &
  fi
  gz sim -v4 -s -r $WORLD &
  sleep 8
  if [ \"$GZ_HEADLESS\" != \"1\" ]; then gz sim -v4 -g & sleep 2; fi
  exec $ARDU --model JSON --home $HOME_LOC --defaults $DEFAULTS \
    --serial0 udpclient:$GCS_IP:14550 --speedup 1
"
# Gazebo 물리 초기화(SW 렌더)가 느리므로 quad 변형(12s)보다 넉넉히 대기.
sleep 20
docker ps --format '{{.Names}} {{.Status}}' | grep -q "$SITL" || { docker logs "$SITL" 2>&1 | tail; die "SITL 기동 실패"; }

# ── 3. GCS 검증 (GCS-UE netns, 다운링크+업링크 — 40-g1-c2 와 동일 경로) ────────
log "GCS 검증(다운링크 HEARTBEAT + 업링크 명령/ACK, 셀룰러 C2)"
set +e
docker run -i --rm --network "container:$GCS_UE" "$AIR_IMG" python3 - < "$HERE/g1_gcs.py"
RC=$?
set -e
echo
[[ $RC -eq 0 ]] && log "G1+Gazebo 통과 ✅ — MAVLink C2 는 셀룰러, 물리/시각화는 Gazebo." \
  || warn "G1 부분/실패(rc=$RC) — docker logs $SITL 확인(Gazebo FDM 지연 가능)."
if [[ "$GZ_HEADLESS" != "1" ]]; then
  log "관측 링크:  http://localhost:6080/vnc.html   (Gazebo GUI, 브라우저)"
fi
log "SITL '$SITL' 가동 유지(TM1/TM3 공격 대상). arm/takeoff 는 GCS 가 셀룰러로 명령."
log "폐루프 비행:  docker run -i --rm --network container:$GCS_UE $AIR_IMG python3 - < $HERE/g2_flight.py"
log "정리:  docker rm -f $SITL"
