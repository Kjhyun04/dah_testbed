# 공중 계층: ArduPilot SITL + Gazebo Harmonic (P-15 물리엔진 통합)
#
# 한 컨테이너에 SITL·Gazebo·VNC를 합친다(P-24 SITL↔Gazebo 레이턴시 최소화):
#   - ArduCopter SITL  : 비행제어 펌웨어 (JSON FDM 백엔드로 Gazebo와 localhost UDP 연동)
#   - Gazebo(gz-sim)   : 3D 물리/비행역학 + 카메라 센서 렌더링
#   - ardupilot_gazebo : SITL↔Gazebo를 잇는 ArduPilotPlugin + GstCameraPlugin
#   - VNC(noVNC)       : Gazebo GUI를 브라우저로 관측 (P-23, :6080)
#
# 주의: ArduPilot waf 빌드 + Gazebo 패키지 + ardupilot_gazebo 빌드라 최초 빌드에
#       수십 분·수 GB 소요. install-prereqs 는 root 거부 → 비root(ardu)로 빌드.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive TZ=UTC

# 1) 기본 도구 (ArduPilot prereq + apt 키 등록용 curl/gnupg)
RUN apt-get update && apt-get install -y --no-install-recommends \
      git sudo lsb-release tzdata ca-certificates curl gnupg \
      python3 python3-pip python3-dev \
 && rm -rf /var/lib/apt/lists/*

# 2) Gazebo Harmonic + ardupilot_gazebo 빌드 의존성 + GStreamer(카메라 RTP) +
#    소프트웨어 GL(GPU 미통과 환경) + VNC 스택(Xvfb/x11vnc/noVNC/openbox)
RUN curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
      -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
 && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable jammy main" \
      > /etc/apt/sources.list.d/gazebo-stable.list \
 && apt-get update && apt-get install -y --no-install-recommends \
      gz-harmonic \
      cmake build-essential libgz-sim8-dev rapidjson-dev libopencv-dev \
      libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
      gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
      gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
      gstreamer1.0-libav gstreamer1.0-gl gstreamer1.0-tools \
      libgl1-mesa-dri libgl1-mesa-glx mesa-utils \
      xvfb x11vnc novnc websockify openbox \
 && rm -rf /var/lib/apt/lists/*

# 비root 사용자 (install-prereqs 가 root 거부) + sudo NOPASSWD
RUN useradd -m -s /bin/bash ardu \
 && echo 'ardu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ardu \
 && chmod 0440 /etc/sudoers.d/ardu
USER ardu
WORKDIR /home/ardu

# 3) ArduCopter 안정 태그 (UGV는 Rover-* + 아래 ./waf rover)
ARG ARDUPILOT_TAG=Copter-4.5
RUN git clone --depth 1 --branch ${ARDUPILOT_TAG} --recurse-submodules \
      https://github.com/ArduPilot/ardupilot.git
WORKDIR /home/ardu/ardupilot
RUN USER=ardu SKIP_AP_EXT_ENV=1 Tools/environment_install/install-prereqs-ubuntu.sh -y
RUN bash -c ". ~/.profile && ./waf configure --board sitl && ./waf copter"
# UGV의 경우: RUN bash -c ". ~/.profile && ./waf rover"

# 4) ardupilot_gazebo 플러그인 빌드 (Harmonic 대상 main 브랜치)
WORKDIR /home/ardu
RUN git clone https://github.com/ArduPilot/ardupilot_gazebo.git \
 && bash -c "cd ardupilot_gazebo && mkdir build && cd build \
      && cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo \
      && make -j$(nproc)"

# 5) Gazebo 환경: 플러그인/모델/월드 탐색 경로 + 소프트웨어 렌더링
ENV GZ_VERSION=harmonic
ENV GZ_SIM_SYSTEM_PLUGIN_PATH=/home/ardu/ardupilot_gazebo/build
ENV GZ_SIM_RESOURCE_PATH=/home/ardu/ardupilot_gazebo/models:/home/ardu/ardupilot_gazebo/worlds:/home/ardu/worlds
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV QT_QPA_PLATFORM=xcb

COPY --chown=ardu:ardu params/ /home/ardu/params/
COPY --chown=ardu:ardu worlds/ /home/ardu/worlds/
COPY --chown=ardu:ardu start-sitl.sh /home/ardu/start-sitl.sh
RUN chmod +x /home/ardu/start-sitl.sh

EXPOSE 5760 6080
CMD ["/home/ardu/start-sitl.sh"]
