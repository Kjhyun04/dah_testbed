#!/usr/bin/env bash
# tun_srsue 생성 대기 — SITL/gcs 브리지(G1)가 UE attach 후 뜨도록 순서 보장.
# 사용: wait-tun.sh <ue-container> [iface] [timeout]
#   예) wait-tun.sh dah4g-uav-ue tun_srsue 90
set -euo pipefail
UE="${1:?usage: wait-tun.sh <ue-container> [iface] [timeout]}"
IFACE="${2:-tun_srsue}"
TIMEOUT="${3:-90}"

echo "[*] $UE 의 $IFACE 대기 (최대 ${TIMEOUT}s — LTE attach + 기본 베어러)..."
for ((i=0; i<TIMEOUT; i++)); do
  if docker exec "$UE" ip -o -4 addr show "$IFACE" 2>/dev/null | grep -q inet; then
    IP=$(docker exec "$UE" ip -o -4 addr show "$IFACE" | awk '{print $4}')
    echo "[✓] $IFACE 준비됨: $IP"
    exit 0
  fi
  sleep 1
done
echo "[✗] ${TIMEOUT}s 내 $IFACE 미생성 — attach 실패 가능. 로그 확인:"
echo "    docker logs $UE --tail 50   (RRC/NAS attach·ZMQ 연결 여부)"
exit 1
