# 지상 계층: mavlink-router (소스 빌드)
FROM ubuntu:22.04 AS build
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates meson ninja-build pkg-config gcc g++ \
      python3 python3-future libsystemd-dev systemd \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --recurse-submodules \
      https://github.com/mavlink-router/mavlink-router.git /src
WORKDIR /src
RUN meson setup build . \
 && ninja -C build \
 && ninja -C build install

FROM ubuntu:22.04
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libsystemd0 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/bin/mavlink-routerd /usr/bin/mavlink-routerd
EXPOSE 14550/udp 14551/udp
CMD ["mavlink-routerd", "-c", "/etc/mavlink-router/main.conf"]
