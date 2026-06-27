# GPS 실제 I/Q 파이프라인: gps-sdr-sim(신호 생성) + GNSS-SDR(소프트 수신기)
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      software-properties-common ca-certificates \
 && add-apt-repository -y universe \
 && apt-get update && apt-get install -y --no-install-recommends \
      gnss-sdr build-essential git python3 python3-pip \
 && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir pymavlink

# gps-sdr-sim (GPS L1 I/Q 신호 생성기) — C 파일 하나, 빠른 빌드.
# 리포에 샘플 방송궤도력 brdc3540.14n 포함 → 외부 다운로드 불필요.
RUN git clone --depth 1 https://github.com/osqzss/gps-sdr-sim.git /opt/gps-sdr-sim \
 && cd /opt/gps-sdr-sim && gcc gpssim.c -lm -O3 -o gps-sdr-sim

RUN mkdir -p /data
WORKDIR /opt
COPY gnss-sdr.conf /opt/gnss-sdr.conf
COPY run_decode.sh /opt/run_decode.sh
COPY run_channel.sh /opt/run_channel.sh
COPY sdr_to_gps.py /opt/sdr_to_gps.py
RUN chmod +x /opt/run_decode.sh /opt/run_channel.sh
# 기본: 채널 가동(디코드→GPS_INPUT). offline 디코드 테스트는 run_decode.sh 로 override.
CMD ["bash", "/opt/run_channel.sh"]
