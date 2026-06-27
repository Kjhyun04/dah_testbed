#!/bin/bash
# 페이로드 영상 다운링크: H.264 RTP 테스트 스트림 → 지상(QGC video, UDP 5600)
DEST=${DEST:-host.docker.internal}
PORT=${PORT:-5600}
echo "[video] H.264 RTP → ${DEST}:${PORT}"
exec gst-launch-1.0 -v \
  videotestsrc pattern=ball is-live=true \
  ! video/x-raw,width=640,height=480,framerate=15/1 \
  ! x264enc tune=zerolatency bitrate=800 speed-preset=ultrafast key-int-max=15 \
  ! rtph264pay config-interval=1 pt=96 \
  ! udpsink host=${DEST} port=${PORT}
