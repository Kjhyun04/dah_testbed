#!/usr/bin/env bash
# ============================================================================
# G1 — MAVLink C2-over-LTE: ArduPilot SITL(UAV-UE netns) ↔ GCS(GCS-UE netns)
#   ★검증된 UE-to-UE UDP 경로 위에 실제 MAVLink C2 배선.
#   - SITL: dah-testbed-air 이미지의 arducopter(--model quad, Gazebo 불요)를
#     UAV-UE netns(network_mode: container:)에서 실행 → MAVLink UDP 를 GCS-UE 로.
#     (192.168.100.0/24 라우팅이 tun_srsue 경유 → 셀룰러 베어러)
#   - GCS: pymavlink(g1_gcs.py)로 다운링크 HEARTBEAT 수신 + 업링크 명령/ACK 확인.
#
#   사용:  bash 40-g1-c2.sh
#   전제:  pair1(srsue_zmq)+pair2(srsue_zmq2) attach 완료(30-add-ue.sh 2),
#          dah-testbed-air 이미지 존재(기존 testbed 빌드).
# ============================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
log(){ printf '\033[1;36m[G1]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[G1✗]\033[0m %s\n' "$*" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

UAV_UE="${UAV_UE:-srsue_zmq}"            # pair1 = UAV
GCS_UE="${GCS_UE:-srsue_zmq2}"           # pair2 = GCS
AIR_IMG="${AIR_IMG:-dah-testbed-air}"
SITL="${SITL:-dah4g-sitl}"
ARDU=/home/ardu/ardupilot/build/sitl/bin/arducopter
PARM=/home/ardu/ardupilot/Tools/autotest/default_params/copter.parm
HOME_LOC="${HOME_LOC:-37.5665,126.9780,30,0}"

docker image inspect "$AIR_IMG" >/dev/null 2>&1 || die "$AIR_IMG 이미지 없음 — 기존 testbed(air) 빌드 필요."
GCS_IP="$(docker exec "$GCS_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
UAV_IP="$(docker exec "$UAV_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
[[ -n "$GCS_IP" && -n "$UAV_IP" ]] || die "UE tun 미확인 — pair1/pair2 attach 먼저(30-add-ue.sh 2)."
log "UAV-UE=$UAV_IP  GCS-UE=$GCS_IP"

# ── SITL 기동 (UAV-UE netns, MAVLink UDP → GCS-UE:14550) ────────────────────
docker rm -f "$SITL" >/dev/null 2>&1 || true
log "SITL 기동(arducopter --model quad → udpclient:$GCS_IP:14550)"
docker run -d --name "$SITL" --network "container:$UAV_UE" "$AIR_IMG" \
  sh -c "cd /tmp && exec $ARDU --model quad --speedup 1 -I0 --defaults $PARM --home $HOME_LOC --serial0 udpclient:$GCS_IP:14550"
sleep 12
docker ps --format '{{.Names}} {{.Status}}' | grep -q "$SITL" || { docker logs "$SITL" 2>&1 | tail; die "SITL 기동 실패"; }

# ── GCS 검증 (GCS-UE netns, 다운링크+업링크) ────────────────────────────────
log "GCS 검증(다운링크 HEARTBEAT + 업링크 명령/ACK)"
docker run -i --rm --network "container:$GCS_UE" "$AIR_IMG" python3 - < "$HERE/g1_gcs.py"
RC=$?
echo
[[ $RC -eq 0 ]] && log "G1 통과 ✅ — 실제 MAVLink C2 가 셀룰러 위 양방향 동작." \
  || log "G1 부분/실패(rc=$RC) — 로그 확인."
log "SITL 컨테이너 '$SITL' 가동 유지(TM1/TM3 공격 대상). 정리: docker rm -f $SITL"
