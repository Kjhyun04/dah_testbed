#!/bin/bash
# ArduPilot SITL ↔ Gazebo Harmonic 기동 (P-15/P-23/P-24/P-25)
#
# 순서: (1) 카메라 RTP 목적지 주입 → (2) 가상 디스플레이+VNC → (3) Gazebo 물리 →
#       (4) Gazebo FDM 준비 대기 → (5) SITL을 JSON FDM(localhost 9002/9003)으로 연결.
# serial0 는 기존과 동일하게 TCP 서버(0.0.0.0:5760)로 노출 → c2channel 이 접속.
set -e

export DISPLAY=:1
CAM_HOST="${CAM_HOST:-host.docker.internal}"   # 카메라 RTP 수신 측(지상/호스트)
CAM_PORT="${CAM_PORT:-5600}"
HOME_LOC="${HOME_LOC:-37.5665,126.9780,30,0}"
WORLD="${WORLD:-/home/ardu/worlds/dah_world.sdf}"
GZ_HEADLESS="${GZ_HEADLESS:-0}"                 # 1이면 GUI 없이 서버만(VNC 미사용)

# ── (1) P-25: 카메라(GstCameraPlugin) RTP 목적지를 모델 SDF에 주입 ──────────────
# iris_with_gimbal 은 gimbal_small_3d(name=gimbal)를 include하며 카메라 플러그인은
# 그 서브모델에 있다. 태그명은 snake_case(<udp_host>/<udp_port>), 기본 127.0.0.1:5600.
MODEL=/home/ardu/ardupilot_gazebo/models/gimbal_small_3d/model.sdf
if [ -f "$MODEL" ]; then
  sed -i "s|<udp_host>[^<]*</udp_host>|<udp_host>${CAM_HOST}</udp_host>|g" "$MODEL"
  sed -i "s|<udp_port>[^<]*</udp_port>|<udp_port>${CAM_PORT}</udp_port>|g" "$MODEL"
  echo "[air] camera RTP → ${CAM_HOST}:${CAM_PORT} (GstCameraPlugin, gimbal_small_3d)"
else
  echo "[air] WARN: gimbal_small_3d/model.sdf 미발견 — 카메라 목적지 주입 생략"
fi

# ── (2) 가상 프레임버퍼 — 항상 기동 ────────────────────────────────────────────
# 카메라 센서(GL 렌더링)는 헤드리스에서도 디스플레이가 필요하므로 Xvfb는 항상 띄운다.
# docker restart 시 /tmp 가 보존돼 이전 인스턴스의 X 락/소켓이 남으면 Xvfb가 :1 점유로
# 실패(XOpenDisplay failed → gz GUI abort)하므로, 먼저 잔존 락을 정리한다.
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true
echo "[air] starting Xvfb :1 (software GL)"
Xvfb :1 -screen 0 1280x720x24 -ac +extension GLX +render -noreset &
sleep 2

# ── P-23: 윈도우 매니저 + noVNC(브라우저 :6080) — GUI 모드에서만 ───────────────
if [ "$GZ_HEADLESS" != "1" ]; then
  echo "[air] starting openbox + x11vnc + noVNC(:6080)"
  openbox &
  x11vnc -display :1 -nopw -forever -shared -rfbport 5900 -quiet &
  # noVNC: 브라우저로 http://localhost:6080/vnc.html 접속
  websockify --web=/usr/share/novnc 6080 localhost:5900 &
fi

# ── (3) P-15: Gazebo 물리 시뮬 기동 ────────────────────────────────────────────
# 서버는 항상 헤드리스(-s -r)로 돌린다. server+GUI 결합 모드(gz sim -r)는 소프트웨어
# 렌더링에서 GUI 렌더 스레드가 물리 스텝을 막아 FDM이 끊긴다(SITL "No JSON sensor").
# GUI(-g)는 별도 프로세스로 띄워 VNC로 관측 — GUI가 느려도 물리/FDM은 영향 없음.
echo "[air] starting Gazebo server (headless, stepping) world=${WORLD}"
gz sim -v4 -s -r "$WORLD" &

# ── (4) Gazebo ArduPilotPlugin FDM 소켓(9002/9003) 준비 대기 ───────────────────
# 소프트웨어 렌더링 초기화가 느릴 수 있어 넉넉히 대기.
sleep 8

# GUI 클라이언트(별도 프로세스) — GZ_HEADLESS=0 일 때만, VNC(:6080)로 관측
if [ "$GZ_HEADLESS" != "1" ]; then
  echo "[air] starting Gazebo GUI client (-g) for VNC"
  gz sim -v4 -g &
fi
sleep 2

# ── (5) SITL을 JSON FDM 백엔드로 기동 → Gazebo와 localhost UDP 연동(P-24) ──────
BIN=/home/ardu/ardupilot/build/sitl/bin/arducopter
DEFAULTS=/home/ardu/ardupilot/Tools/autotest/default_params/copter.parm,\
/home/ardu/ardupilot/Tools/autotest/default_params/gazebo-iris.parm,\
/home/ardu/params/m0-baseline.parm

echo "[air] ArduCopter SITL ↔ Gazebo (JSON FDM 127.0.0.1:9002), serial0=tcp:0.0.0.0:5760"
exec "$BIN" \
  --model JSON \
  --home "$HOME_LOC" \
  --defaults "$DEFAULTS" \
  --serial0 tcp:0.0.0.0:5760 \
  --speedup 1
