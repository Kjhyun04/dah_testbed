#!/usr/bin/env bash
# ============================================================================
# 70-c2-aria — MAVLink C2 를 KCMVP 국산암호 ARIA-256 으로 암호화 (opt-in, 방어 배선)
#   G1 경로 위에 암호 프록시 한 쌍을 끼운다:
#     [SITL] -평문14550-> (uav프록시) -ARIA암호문14555(셀룰러)-> (gcs프록시) -평문-> [GCS]
#   기존 MAVLink v2 서명(무결성·인증)과 상보 = 서명(위조방지) + ARIA(기밀성·도청방지).
#   셀룰러 링크(tun_srsue)엔 암호문(14555)만 흐른다 → 도청해도 MAVLink 내용 불가시.
#
#   전제:  pair1(srsue_zmq)+pair2(srsue_zmq2) attach 완료(30-add-ue.sh 2),
#          dah-testbed-air 이미지 존재, mav_aria_proxy.py 동일 폴더.
#   사용:  bash scripts/70-c2-aria.sh              # 키 자동생성
#          ARIA_KEY=<64hex> bash scripts/70-c2-aria.sh   # 키 고정(재현/공유)
#   정리:  docker rm -f dah4g-sitl dah4g-aria-uav dah4g-aria-gcs
#   ⚠️ 방어 배선(인프라)만. 복호·공격 시도는 사용자 몫(역할경계).
# ============================================================================
set -euo pipefail
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
HERE="$(cd "$(dirname "$0")" && pwd)"
log(){ printf '\033[1;35m[ARIA]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[ARIA✗]\033[0m %s\n' "$*" >&2; exit 1; }

UAV_UE="${UAV_UE:-srsue_zmq}"; GCS_UE="${GCS_UE:-srsue_zmq2}"
AIR_IMG="${AIR_IMG:-dah-testbed-air}"
SITL="${SITL:-dah4g-sitl}"
A_UAV=dah4g-aria-uav; A_GCS=dah4g-aria-gcs
PLAIN=14550; RELAYPLAIN=14556; CIPHER=14555            # 평문 / GCS측 평문릴레이 / 암호문(셀룰러)
ARDU=/home/ardu/ardupilot/build/sitl/bin/arducopter
PARM=/home/ardu/ardupilot/Tools/autotest/default_params/copter.parm
HOME_LOC="${HOME_LOC:-37.5665,126.9780,30,0}"
PROXY="$HERE/mav_aria_proxy.py"

[[ -f "$PROXY" ]] || die "mav_aria_proxy.py 없음 ($PROXY)"
docker image inspect "$AIR_IMG" >/dev/null 2>&1 \
  || die "$AIR_IMG 이미지 없음 — cd ~/dah_testbed && docker build -t dah-testbed-air ./air"

# ── 공유 키 (양 프록시 동일해야 함). ARIA_KEY 로 고정 가능 ────────────────────
KEY="${ARIA_KEY:-$(openssl rand -hex 32)}"
[[ "${#KEY}" -eq 64 ]] || die "ARIA_KEY 는 64 hex(32바이트) 여야 함"
log "공유 마스터키(앞8): ${KEY:0:8}…   (uav/gcs 프록시 동일 적용)"

# ── 0) 자가검증 게이트 — 컨테이너에서 ARIA KAT(openssl 교차검증 벡터) ─────────
log "0) ARIA 자가검증(KAT + 라운드트립 + 변조탐지)…"
docker run --rm -i "$AIR_IMG" python3 - --selftest < "$PROXY" \
  || die "ARIA 자가검증 실패 — 이미지의 libcrypto/ARIA 확인"

# ── UE tun IP ────────────────────────────────────────────────────────────────
GCS_IP="$(docker exec "$GCS_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
UAV_IP="$(docker exec "$UAV_UE" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"
[[ -n "$GCS_IP" && -n "$UAV_IP" ]] || die "UE tun 미확인 — pair1/pair2 attach 먼저(30-add-ue.sh 2)."
log "UAV-UE=$UAV_IP  GCS-UE=$GCS_IP  (암호문은 $CIPHER 로 tun_srsue=셀룰러 경유)"

# ── 프록시 기동 헬퍼 (create → cp 스크립트 → start; 60-viz 패턴) ─────────────
launch_proxy(){  # $1=컨테이너명  $2=netns-UE  나머지=프록시 인자
  local name="$1" ue="$2"; shift 2
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker create --name "$name" --network "container:$ue" "$AIR_IMG" \
    python3 /tmp/mav_aria_proxy.py "$@" --key-hex "$KEY" >/dev/null
  docker cp "$PROXY" "$name:/tmp/mav_aria_proxy.py"
  docker start "$name" >/dev/null
}

# ── 1) GCS 측 프록시 (암호문 14555 수신 → 복호 → GCS 평문 14550) ─────────────
log "1) GCS 프록시 기동 ($A_GCS @ gcs-ue)"
launch_proxy "$A_GCS" "$GCS_UE" \
  --plain-listen 127.0.0.1:$RELAYPLAIN --plain-peer 127.0.0.1:$PLAIN \
  --cipher-listen 0.0.0.0:$CIPHER

# ── 2) UAV 측 프록시 (SITL 평문 14550 → 암호화 → GCS_IP:14555 셀룰러) ────────
log "2) UAV 프록시 기동 ($A_UAV @ uav-ue)"
launch_proxy "$A_UAV" "$UAV_UE" \
  --plain-listen 127.0.0.1:$PLAIN \
  --cipher-listen 0.0.0.0:$CIPHER --cipher-peer "$GCS_IP:$CIPHER"
sleep 2

# ── 3) SITL 재기동 — 로컬 UAV 프록시(127.0.0.1:14550)로 송신 ─────────────────
log "3) SITL 재기동 → udpclient:127.0.0.1:$PLAIN (ARIA 암호채널 경유)"
docker rm -f "$SITL" >/dev/null 2>&1 || true
docker run -d --name "$SITL" --network "container:$UAV_UE" "$AIR_IMG" \
  sh -c "cd /tmp && exec $ARDU --model quad --speedup 1 -I0 --defaults $PARM --home $HOME_LOC --serial0 udpclient:127.0.0.1:$PLAIN"
sleep 12
docker ps --format '{{.Names}}' | grep -q "$SITL" || { docker logs "$SITL" 2>&1 | tail; die "SITL 기동 실패"; }

# ── 4) GCS 검증 — 암호채널 통과 확인(다운링크 HEARTBEAT + 업링크) ────────────
log "4) GCS 검증 (ARIA 암호채널 위 양방향 C2)"
docker run -i --rm --network "container:$GCS_UE" "$AIR_IMG" \
  python3 - "udpin:0.0.0.0:$PLAIN" < "$HERE/g1_gcs.py"
RC=$?
echo
[[ $RC -eq 0 ]] \
  && log "✅ ARIA-C2 통과 — C2 정상 + 셀룰러엔 암호문($CIPHER)만." \
  || log "부분/실패(rc=$RC) — 프록시 로그 확인: docker logs $A_UAV ; docker logs $A_GCS"

cat <<EOF

$(printf '\033[1;35m[ARIA]\033[0m') 관측(도청 대비):
  평문 없음 확인:  docker exec $UAV_UE tcpdump -nA -i any udp port $CIPHER   # ARIA 암호문만 보임
  (대조) 평문:     docker exec $UAV_UE tcpdump -nA -i any udp port $PLAIN    # 로컬 루프백엔 평문
정리:  docker rm -f $SITL $A_UAV $A_GCS
EOF
