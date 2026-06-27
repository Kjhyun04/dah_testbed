#!/bin/bash
# ArduPilot SITL 기동 — serial0를 TCP 서버(0.0.0.0:5760)로 노출하여
# 다른 컨테이너(mavlink-router)가 접속할 수 있게 한다.
set -e

BIN=/home/ardu/ardupilot/build/sitl/bin/arducopter
DEFAULTS=/home/ardu/ardupilot/Tools/autotest/default_params/copter.parm,/home/ardu/params/m0-baseline.parm

# 기본 위치(예: 임의 비행장). 필요시 위경도 조정.
HOME_LOC="${HOME_LOC:-37.5665,126.9780,30,0}"

echo "[air] starting ArduCopter SITL, serial0=tcp:0.0.0.0:5760"
exec "$BIN" \
  --model "+" \
  --home "$HOME_LOC" \
  --defaults "$DEFAULTS" \
  --serial0 tcp:0.0.0.0:5760 \
  --speedup 1

# ── 대안 (위 --serial0 바인딩이 컨테이너 간 접속에 실패할 경우) ──
# sim_vehicle.py 사용 (PATH는 ~/.profile):
#   . ~/.profile
#   exec sim_vehicle.py -v ArduCopter --no-mavproxy \
#        -A "--serial0 tcp:0.0.0.0:5760" --speedup 1
