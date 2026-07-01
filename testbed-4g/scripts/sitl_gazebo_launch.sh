#!/bin/bash
# ============================================================================
# 4G-VIZ — ArduPilot SITL(--model JSON, Gazebo FDM) + noVNC, UAV-UE netns 내부 기동.
#   루트 air/start-sitl.sh 의 검증된 localhost FDM(127.0.0.1:9002/9003) 경로를 그대로
#   쓰되, serial 배선만 4G용으로 교체:
#     serial0 = udpclient:$GCS_IP:14550   (C2, tun_srsue=셀룰러)
#     serial2 = udpclient:$INJ_IP:14560   (GPS, dahnet=비셀룰러; gps_inject.py가 SIMSTATE→GPS_INPUT)
#   FDM 은 같은 netns localhost → 물리 백플레인은 셀룰러에 안 태움(채널분리 원칙 유지).
#   noVNC(:6080)는 0.0.0.0 바인드 → 호스트는 dahnet 릴레이(tcp_relay.py) 경유로 관측.
#   ★이 컨테이너의 PID1 은 최종 arducopter(exec) — 죽으면 컨테이너 종료(루트와 동일).
# ============================================================================
set -e
export DISPLAY=:1
CAM_HOST="${CAM_HOST:-127.0.0.1}"; CAM_PORT="${CAM_PORT:-5600}"
HOME_LOC="${HOME_LOC:-37.5665,126.9780,30,0}"
WORLD="${WORLD:-/home/ardu/worlds/dah_world.sdf}"
GZ_HEADLESS="${GZ_HEADLESS:-0}"
GCS_IP="${GCS_IP:?GCS_IP(셀룰러 C2 목적지) 필요}"
INJ_IP="${INJ_IP:?INJ_IP(dahnet GPS 주입기) 필요}"

# ── (1) 카메라 RTP 목적지 주입(선택) — 시각화엔 불요지만 모델 경고 억제 ──────────
MODEL=/home/ardu/ardupilot_gazebo/models/gimbal_small_3d/model.sdf
if [ -f "$MODEL" ]; then
  sed -i "s|<udp_host>[^<]*</udp_host>|<udp_host>${CAM_HOST}</udp_host>|g" "$MODEL"
  sed -i "s|<udp_port>[^<]*</udp_port>|<udp_port>${CAM_PORT}</udp_port>|g" "$MODEL"
fi

# ── (2) Xvfb(소프트웨어 GL) — 카메라 센서 렌더에 디스플레이 필요(헤드리스에서도) ───
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true
echo "[viz] Xvfb :1 (software GL)"
Xvfb :1 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
sleep 2

# ── (3) noVNC(:6080) — netns 안 0.0.0.0 바인드 → dahnet 릴레이가 호스트로 노출 ──────
if [ "$GZ_HEADLESS" != "1" ]; then
  echo "[viz] openbox + x11vnc + noVNC(:6080)"
  openbox &
  x11vnc -display :1 -nopw -forever -shared -rfbport 5900 -quiet &
  websockify --web=/usr/share/novnc 6080 localhost:5900 &
fi

# ── (4) Gazebo 서버(헤드리스 스텝) + GUI(별도 프로세스) — 루트와 동일 ──────────────
# 서버+GUI 결합 모드는 소프트웨어 렌더에서 물리 스텝을 막아 FDM 끊김 → 분리 기동.
echo "[viz] Gazebo server (headless, stepping) world=${WORLD}"
gz sim -v4 -s -r "$WORLD" &
sleep 8
if [ "$GZ_HEADLESS" != "1" ]; then
  echo "[viz] Gazebo GUI client (-g) for VNC"
  gz sim -v4 -g &
fi
sleep 2

# ── (5) SITL: --model JSON(localhost FDM) + 외부GPS + 이중 시리얼 ──────────────────
# 외부 GPS(GPS_TYPE=14) + SIM GPS 비활성 → GPS 는 gps_inject.py 가 dahnet 로 공급.
# gpsext.parm 를 맨 끝에 둬 gazebo-iris.parm 의 GPS 관련 기본값을 덮어쓴다(나중 파일 우선).
printf 'SIM_GPS_DISABLE 1\nGPS_TYPE 14\n' > /tmp/gpsext.parm
BIN=/home/ardu/ardupilot/build/sitl/bin/arducopter
DEFAULTS="/home/ardu/ardupilot/Tools/autotest/default_params/copter.parm,/home/ardu/ardupilot/Tools/autotest/default_params/gazebo-iris.parm,/tmp/gpsext.parm"
echo "[viz] SITL ↔ Gazebo(JSON 127.0.0.1:9002) | serial0→C2 ${GCS_IP}:14550 | serial2→GPS ${INJ_IP}:14560"
exec "$BIN" \
  --model JSON \
  --home "$HOME_LOC" \
  --defaults "$DEFAULTS" \
  -I0 --speedup 1 \
  --serial0 "udpclient:${GCS_IP}:14550" \
  --serial2 "udpclient:${INJ_IP}:14560"
