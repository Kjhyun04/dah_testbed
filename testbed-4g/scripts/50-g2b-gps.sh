#!/usr/bin/env bash
# ============================================================================
# G2(B) — GPS off-셀룰러: GPS를 dahnet(비셀룰러) 경유로 SITL에 공급, C2는 셀룰러 유지.
#   ★설계 원칙: GPS는 셀룰러에 안 태움(직접 센서). C2(+페이로드)만 셀룰러.
#   배선:
#     - uav-ue(srsue_zmq) 를 dahnet 에도 연결(멀티네트워크).
#     - SITL: SIM_GPS_DISABLE=1/GPS_TYPE=14(외부GPS) +
#         serial0=udpclient:GCS_UE:14550 (C2, tun_srsue=셀룰러)
#         serial2=udpclient:<INJ>:14560   (GPS, dahnet=비셀룰러)
#     - gps_inject.py: dahnet 의 주입기 → SIMSTATE+VFR_HUD → GPS_INPUT @5Hz.
#   결과: GPS_RAW_INT fix_type=3 (GPS via dahnet), C2 는 셀룰러 유지 → 채널 분리.
#
#   사용:  bash 50-g2b-gps.sh
# ============================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
log(){ printf '\033[1;36m[G2B]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[G2B✗]\033[0m %s\n' "$*" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

UAV_UE=srsue_zmq; GCS_UE=srsue_zmq2; AIR_IMG=dah-testbed-air
DAHNET="${DAHNET:-dah-testbed_dahnet}"
INJ_IP="${INJ_IP:-172.28.0.160}"; SITL_DAH_IP="${SITL_DAH_IP:-172.28.0.161}"   # 기존 .10~.90 회피
SITL=dah4g-sitl; INJ=dah4g-gps
ARDU=/home/ardu/ardupilot/build/sitl/bin/arducopter
PARM=/home/ardu/ardupilot/Tools/autotest/default_params/copter.parm

docker network inspect "$DAHNET" >/dev/null 2>&1 || die "$DAHNET 네트워크 없음(기존 testbed up 필요)."
docker image inspect "$AIR_IMG" >/dev/null 2>&1 || die "$AIR_IMG 이미지 없음."
GCS_IP="$(docker exec "$GCS_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
[[ -n "$GCS_IP" ]] || die "GCS-UE tun 미확인."
log "GCS_UE(C2)=$GCS_IP  INJ(GPS,dahnet)=$INJ_IP  SITL_dahnet=$SITL_DAH_IP"

# 1) uav-ue 를 dahnet 에 연결 (GPS 채널 인터페이스 추가)
if ! docker inspect "$UAV_UE" -f '{{range $k,$v:=.NetworkSettings.Networks}}{{$k}} {{end}}' | grep -q "$DAHNET"; then
  log "uav-ue → dahnet 연결($SITL_DAH_IP)"; docker network connect --ip "$SITL_DAH_IP" "$DAHNET" "$UAV_UE"
else log "uav-ue 이미 dahnet 연결됨"; fi

# 2) SITL 재기동 (외부GPS + C2(셀룰러)/GPS(dahnet) 이중 시리얼)
docker rm -f "$SITL" >/dev/null 2>&1 || true
log "SITL 재기동 (외부GPS, serial0→C2 cellular, serial2→GPS dahnet)"
docker run -d --name "$SITL" --network "container:$UAV_UE" "$AIR_IMG" sh -c "
  printf 'SIM_GPS_DISABLE 1\nGPS_TYPE 14\n' > /tmp/gpsext.parm
  cd /tmp && exec $ARDU --model quad --speedup 1 -I0 \
    --defaults $PARM,/tmp/gpsext.parm --home 37.5665,126.9780,30,0 \
    --serial0 udpclient:$GCS_IP:14550 --serial2 udpclient:$INJ_IP:14560"
sleep 8

# 3) GPS 주입기 (dahnet, 고정 IP) — cp 로 스크립트 주입 후 start
docker rm -f "$INJ" >/dev/null 2>&1 || true
docker create --name "$INJ" --network "$DAHNET" --ip "$INJ_IP" "$AIR_IMG" python3 /tmp/gps_inject.py udpin:0.0.0.0:14560 >/dev/null
# docker cp 는 호스트경로 → MSYS_NO_PATHCONV 환경에서 /c/.. 가 안 먹으므로 Windows 경로로 변환
WINHERE="$(echo "$HERE" | sed -E 's|^/([a-zA-Z])/|\U\1:/|')"
docker cp "$WINHERE/gps_inject.py" "$INJ:/tmp/gps_inject.py" 2>/dev/null \
  || docker cp "$HERE/gps_inject.py" "$INJ:/tmp/gps_inject.py"
docker start "$INJ" >/dev/null
log "GPS 주입기 가동($INJ @ $INJ_IP:14560, dahnet)"

# 4) GPS fix 검증 (GCS-UE netns 에서 GPS_RAW_INT 관측 — 최대 60s)
log "GPS fix 대기(외부 GPS via dahnet, 최대 60s)..."
docker run -i --rm --network "container:$GCS_UE" "$AIR_IMG" python3 - <<'PYEOF'
import time
from pymavlink import mavutil
m=mavutil.mavlink_connection('udpin:0.0.0.0:14550'); m.wait_heartbeat(timeout=30)
m.mav.request_data_stream_send(m.target_system,m.target_component,mavutil.mavlink.MAV_DATA_STREAM_ALL,4,1)
t=time.time(); fix=0
while time.time()-t<60:
    m.mav.heartbeat_send(6,8,0,0,0)
    g=m.recv_match(type='GPS_RAW_INT',blocking=True,timeout=2)
    if g:
        fix=g.fix_type
        if fix>=3:
            print("[G2B] ✓ GPS fix_type=%d via dahnet (lat=%.5f sats=%d) — GPS off-셀룰러 성립 ✅"%(fix,g.lat/1e7,g.satellites_visible)); raise SystemExit(0)
print("[G2B] ✗ GPS fix 미획득 (last fix_type=%d) — 주입기/배선 확인"%fix); raise SystemExit(1)
PYEOF
RC=$?
# fix 직후가 아니라 10Hz 가 ~15s 지속돼야 GPS health(245ms freshness) 충족 → arm 가능.
[[ $RC -eq 0 ]] && { log "GPS health 안정화 대기(15s) — 이후 arm 가능"; sleep 15; }
echo
log "채널 분리: C2=tun_srsue(192.168.100/24, 셀룰러) · GPS=dahnet(172.28/16, 비셀룰러)"
[[ $RC -eq 0 ]] && log "G2-B 통과 ✅ — GPS가 셀룰러 밖(dahnet)에서 공급, C2는 셀룰러." \
  || log "G2-B 미완(rc=$RC) — docker logs $INJ / $SITL 확인."
