#!/usr/bin/env bash
# ============================================================================
# 60 — VIZ: G2 + Gazebo 3D 시각화 (opt-in). 공격 성공을 "눈으로" 본다.
#   ★기본 G1/G2(40/50)는 안 건드림. 이 스크립트는 SITL 백엔드만 Gazebo 로 교체:
#     - SITL(--model JSON) + Gazebo 를 같은 UAV-UE netns 에 합침 → localhost FDM(검증된 경로)
#     - serial0=C2(tun_srsue, 셀룰러) · serial2=GPS(dahnet) → 채널분리 그대로
#     - GPS 주입기(gps_inject.py @ dahnet) — 50 과 동일
#     - noVNC 릴레이(:6080) — netns 안 noVNC 를 호스트로 노출(tcp_relay.py)
#   ★컨테이너 이름은 50 과 동일(dah4g-sitl/dah4g-gps) → 기존 비행/공격 절차 그대로 재사용.
#     관측만 추가됨: GCS 지도엔 "정상", Gazebo 3D 엔 스푸핑 표류/추락이 보인다.
#
#   사용:  bash 60-viz-gazebo.sh
#   이후:  docker run -i --rm --network container:srsue_zmq2 dah-testbed-air \
#            python3 - < g2_flight.py        # 비행(arm→takeoff→land) — 3D 로 관측
#          (TM1/2/3·GPS 스푸핑 실행 시 dah4g-sitl 이 그대로 대상)
#   전제:  30-add-ue.sh 2 (멀티UE), 기존 testbed up(dahnet), dah-testbed-air(Gazebo 포함).
# ============================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
log(){ printf '\033[1;35m[VIZ]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[VIZ✗]\033[0m %s\n' "$*" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

UAV_UE="${UAV_UE:-srsue_zmq}"; GCS_UE="${GCS_UE:-srsue_zmq2}"; AIR_IMG="${AIR_IMG:-dah-testbed-air}"
DAHNET="${DAHNET:-dah-testbed_dahnet}"
INJ_IP="${INJ_IP:-172.28.0.160}"; SITL_DAH_IP="${SITL_DAH_IP:-172.28.0.161}"
SITL=dah4g-sitl; INJ=dah4g-gps; RELAY=dah4g-viz-relay
VNC_PORT="${VNC_PORT:-6080}"; HOME_LOC="${HOME_LOC:-37.5665,126.9780,30,0}"
# 호스트경로 → docker cp 용 Windows 경로(MSYS_NO_PATHCONV 환경 대비; 50 과 동일 패턴)
WINHERE="$(echo "$HERE" | sed -E 's|^/([a-zA-Z])/|\U\1:/|')"
cpin(){ docker cp "$WINHERE/$1" "$2" 2>/dev/null || docker cp "$HERE/$1" "$2"; }

docker image inspect "$AIR_IMG" >/dev/null 2>&1 || die "$AIR_IMG 이미지 없음 — 기존 testbed(air) 빌드 필요(Gazebo 포함)."
docker network inspect "$DAHNET" >/dev/null 2>&1 || die "$DAHNET 없음 — 기존 testbed up 필요(GPS=dahnet)."
GCS_IP="$(docker exec "$GCS_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
[[ -n "$GCS_IP" ]] || die "GCS-UE tun 미확인 — 30-add-ue.sh 2 / attach 먼저."
log "GCS_UE(C2)=$GCS_IP  INJ(GPS,dahnet)=$INJ_IP  SITL_dahnet=$SITL_DAH_IP  noVNC=:$VNC_PORT"

# 1) uav-ue → dahnet (GPS 채널 + noVNC 릴레이 도달 경로)
if ! docker inspect "$UAV_UE" -f '{{range $k,$v:=.NetworkSettings.Networks}}{{$k}} {{end}}' | grep -q "$DAHNET"; then
  log "uav-ue → dahnet 연결($SITL_DAH_IP)"; docker network connect --ip "$SITL_DAH_IP" "$DAHNET" "$UAV_UE"
else log "uav-ue 이미 dahnet 연결됨"; fi

# 2) SITL+Gazebo (UAV-UE netns, --model JSON localhost FDM)
docker rm -f "$SITL" >/dev/null 2>&1 || true
log "SITL+Gazebo 기동 (--model JSON, localhost FDM; serial0→C2, serial2→GPS)"
docker create --name "$SITL" --network "container:$UAV_UE" --shm-size=1gb \
  -e GCS_IP="$GCS_IP" -e INJ_IP="$INJ_IP" -e HOME_LOC="$HOME_LOC" -e CAM_HOST=127.0.0.1 \
  "$AIR_IMG" bash /tmp/sitl_gazebo_launch.sh >/dev/null
cpin sitl_gazebo_launch.sh "$SITL:/tmp/sitl_gazebo_launch.sh"
docker start "$SITL" >/dev/null
log "SITL+Gazebo 초기화 대기(소프트웨어 렌더 — 25s)..."
sleep 25
docker ps --format '{{.Names}}' | grep -q "^$SITL$" || { docker logs "$SITL" 2>&1 | tail -30; die "SITL+Gazebo 기동 실패"; }

# 3) GPS 주입기 (dahnet) — 50 과 동일
docker rm -f "$INJ" >/dev/null 2>&1 || true
docker create --name "$INJ" --network "$DAHNET" --ip "$INJ_IP" "$AIR_IMG" python3 /tmp/gps_inject.py udpin:0.0.0.0:14560 >/dev/null
cpin gps_inject.py "$INJ:/tmp/gps_inject.py"
docker start "$INJ" >/dev/null
log "GPS 주입기 가동($INJ @ $INJ_IP:14560)"

# 4) noVNC 릴레이 — netns 안 noVNC(:6080)를 호스트 루프백으로 (socat 부재 → python TCP relay)
#    -p 127.0.0.1: 로 바인드 → 공유 EC2에서 외부 미노출. 접근은 SSH 터널(ssh -L 6080:localhost:6080).
docker rm -f "$RELAY" >/dev/null 2>&1 || true
docker create --name "$RELAY" --network "$DAHNET" -p "127.0.0.1:$VNC_PORT:$VNC_PORT" \
  "$AIR_IMG" python3 /tmp/tcp_relay.py "$VNC_PORT" "$SITL_DAH_IP" "$VNC_PORT" >/dev/null
cpin tcp_relay.py "$RELAY:/tmp/tcp_relay.py"
docker start "$RELAY" >/dev/null
log "noVNC 릴레이 가동(localhost:$VNC_PORT → $SITL_DAH_IP:$VNC_PORT)"

# 5) GPS fix 검증 (Gazebo FDM 의 SIMSTATE truth → GPS_INPUT 경로 확인; 50 과 동일 패턴)
log "GPS fix 대기(외부 GPS via dahnet, 최대 60s)..."
set +e
docker run -i --rm --network "container:$GCS_UE" "$AIR_IMG" python3 - <<'PYEOF'
import time
from pymavlink import mavutil
m=mavutil.mavlink_connection('udpin:0.0.0.0:14550'); m.wait_heartbeat(timeout=40)
m.mav.request_data_stream_send(m.target_system,m.target_component,mavutil.mavlink.MAV_DATA_STREAM_ALL,4,1)
t=time.time(); fix=0
while time.time()-t<60:
    m.mav.heartbeat_send(6,8,0,0,0)
    g=m.recv_match(type='GPS_RAW_INT',blocking=True,timeout=2)
    if g:
        fix=g.fix_type
        if fix>=3:
            print("[VIZ] ✓ GPS fix_type=%d via dahnet (lat=%.5f) — Gazebo FDM truth → GPS_INPUT 경로 정상"%(fix,g.lat/1e7)); raise SystemExit(0)
print("[VIZ] ✗ GPS fix 미획득(last=%d) — --model JSON에서 SIMSTATE truth 미공급 의심: docker logs dah4g-gps"%fix); raise SystemExit(1)
PYEOF
RC=$?
set -e
[[ $RC -eq 0 ]] && { log "GPS health 안정화 대기(15s)"; sleep 15; }
echo
log "────────────────────────────────────────────────────────────"
log "관측: 브라우저 → http://localhost:$VNC_PORT/vnc.html  (Gazebo 3D)"
log "채널: C2=tun_srsue(셀룰러) · GPS=dahnet(비셀룰러) · FDM=localhost(UAV netns)"
log "비행: docker run -i --rm --network container:$GCS_UE $AIR_IMG python3 - < $HERE/g2_flight.py"
log "공격: dah4g-sitl 이 그대로 TM1/2/3·GPS 스푸핑 대상 — 3D 에서 표류/추락 관측"
[[ $RC -eq 0 ]] && log "VIZ 준비 완료 ✅ (G2 + Gazebo)" \
  || die "GPS 미획득 — Gazebo FDM 의 SIMSTATE truth 공급 여부 확인 필요(README §정직한 한계)."
log "정리: docker rm -f $SITL $INJ $RELAY"
