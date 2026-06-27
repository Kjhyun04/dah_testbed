#!/bin/bash
# A2.2: I/Q 생성(좌표) → GNSS-SDR 디코드 → GPS_INPUT 공급(채널 가동)
set -e

LAT=${LAT:-37.5665}
LON=${LON:-126.9780}
ALT=${ALT:-30}
DUR=${DUR:-180}
CONN=${CONN:-udpout:172.28.0.20:14552}

cd /opt/gps-sdr-sim
EPH=$(ls brdc*.*n 2>/dev/null | head -1)
echo "[channel] I/Q 생성: $LAT,$LON,$ALT (${DUR}s, eph=$EPH)"
./gps-sdr-sim -e "$EPH" -l "$LAT,$LON,$ALT" -b 8 -d "$DUR" -o /data/gpssim.bin

echo "[channel] GNSS-SDR 디코드 → GPS_INPUT 공급 ($CONN)"
cd /data
exec python3 /opt/sdr_to_gps.py "$CONN"
