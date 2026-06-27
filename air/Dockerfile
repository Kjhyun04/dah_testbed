# 공중 계층: ArduPilot SITL (소스 빌드)
# 주의: install-prereqs + waf 빌드라 최초 빌드에 수십 분 소요될 수 있음.
#       install-prereqs-ubuntu.sh 는 root 실행을 거부하므로 비root 사용자로 빌드한다.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends \
      git sudo lsb-release tzdata ca-certificates \
      python3 python3-pip python3-dev \
 && rm -rf /var/lib/apt/lists/*

# 비root 사용자 (install-prereqs 가 root 거부) + sudo NOPASSWD
RUN useradd -m -s /bin/bash ardu \
 && echo 'ardu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ardu \
 && chmod 0440 /etc/sudoers.d/ardu
USER ardu
WORKDIR /home/ardu

# ArduCopter 안정 태그 (UGV는 Rover-* + 아래 ./waf rover)
ARG ARDUPILOT_TAG=Copter-4.5
RUN git clone --depth 1 --branch ${ARDUPILOT_TAG} --recurse-submodules \
      https://github.com/ArduPilot/ardupilot.git
WORKDIR /home/ardu/ardupilot

# 빌드 사전 의존성 설치 (~/.profile 에 PATH 추가됨). sudo 로 apt 수행.
RUN USER=ardu SKIP_AP_EXT_ENV=1 Tools/environment_install/install-prereqs-ubuntu.sh -y

# SITL 바이너리 빌드
RUN bash -c ". ~/.profile && ./waf configure --board sitl && ./waf copter"
# UGV의 경우: RUN bash -c ". ~/.profile && ./waf rover"

COPY --chown=ardu:ardu params/ /home/ardu/params/
COPY --chown=ardu:ardu start-sitl.sh /home/ardu/start-sitl.sh
RUN chmod +x /home/ardu/start-sitl.sh

EXPOSE 5760
CMD ["/home/ardu/start-sitl.sh"]
