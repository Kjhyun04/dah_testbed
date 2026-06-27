#!/bin/bash
# A2.0 offline 검증: gps-sdr-sim 신호 생성 → GNSS-SDR 디코드 → 위치 확인
set -e

LAT=${LAT:-37.5665}
LON=${LON:-126.9780}
ALT=${ALT:-30}
DUR=${DUR:-45}

echo "[sdr] 1) gps-sdr-sim: 좌표 $LAT,$LON,$ALT 의 GPS L1 I/Q 생성 (${DUR}s, 8-bit) ..."
cd /opt/gps-sdr-sim
EPH=$(ls brdc*.*n 2>/dev/null | head -1)
echo "[sdr] ephemeris: $EPH"
./gps-sdr-sim -e "$EPH" -l "$LAT,$LON,$ALT" -b 8 -d "$DUR" -o /data/gpssim.bin
ls -lh /data/gpssim.bin

echo "[sdr] 2) GNSS-SDR: I/Q 디코드 → 위치 계산 (전체 로그 /data/gnss.log) ..."
cd /data
gnss-sdr --config_file=/opt/gnss-sdr.conf > /data/gnss.log 2>&1 || true
echo "[sdr] PVT/위치 라인:"
grep -iE "Position at|is Lat|Lat = |Long = |Height|RTKLIB|fix" /data/gnss.log | tail -12 || echo "(위치 라인 없음)"
echo "[sdr] (gnss-sdr 마지막 12줄)"
tail -12 /data/gnss.log

echo ""
echo "[sdr] 3) NMEA 결과 (마지막 위치):"
if [ -f /data/gnss_sdr.nmea ]; then
    grep -E '\$G.GGA' /data/gnss_sdr.nmea | tail -3
    echo "[sdr] 입력 좌표 = $LAT,$LON / 위 GGA의 위경도와 비교"
else
    echo "(NMEA 파일 없음)"
fi
