# 페이로드 영상 스트림 (GStreamer RTP H.264)
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
      gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
 && rm -rf /var/lib/apt/lists/*
COPY run_video.sh /run_video.sh
RUN chmod +x /run_video.sh
CMD ["/run_video.sh"]
