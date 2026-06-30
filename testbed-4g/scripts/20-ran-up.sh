#!/usr/bin/env bash
# ============================================================================
# G0 — srsRAN(ZMQ) 단일 UE 기동 + attach 검증 (upstream 메커니즘 재사용)
#   ★검증 반영: srsenb/srsue 는 docker_open5gs 의 srsenb_zmq.yaml / srsue_zmq.yaml
#     (image=docker_srslte, COMPONENT_NAME, /mnt/srslte, .env 의 SRS_*_IP/UE1_*) 사용.
#     내 손으로 srsenb 직접호출하지 않음(불일치 #4 수정).
#
#   사용:  bash 20-ran-up.sh
#   전제:  10-epc-up.sh(EPC up) + provision.sh(가입자 등록) 완료.
# ============================================================================
set -euo pipefail
log(){ printf '\033[1;36m[G0]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[G0!]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[G0✗]\033[0m %s\n' "$*" >&2; exit 1; }

WORK="${WORK:-$HOME/docker_open5gs}"
ENB_YML="${ENB_YML:-srsenb_zmq.yaml}"
UE_YML="${UE_YML:-srsue_zmq.yaml}"
ENB_CT="${ENB_CT:-srsenb_zmq}"; UE_CT="${UE_CT:-srsue_zmq}"
cd "$WORK" || die "$WORK 없음 — 10-epc-up.sh 먼저."

# ── 1. eNB 기동 (MME 에 S1AP) ───────────────────────────────────────────────
# ★ZMQ 가상라디오는 eNB→(안정화)→UE 순서로 '깨끗하게' 떠야 UE 가 셀에 동기화된다.
#   단편적/동시 재시작은 ZMQ 샘플스트림 desync 로 UE 가 'Attaching...'에서 멈춤.
#   → --force-recreate 로 매 실행마다 새 시작 보장.
log "srsenb_zmq 기동(force-recreate)..."; docker compose -f "$ENB_YML" up -d --force-recreate
sleep 4
docker logs "$ENB_CT" 2>&1 | grep -iE 'connected|s1 setup|error|started' | tail -3 || true

# ── 2. UE 기동 (attach) ─────────────────────────────────────────────────────
log "srsue_zmq 기동(force-recreate)..."; docker compose -f "$UE_YML" up -d --force-recreate

# ── 3. tun_srsue + attach 대기 ──────────────────────────────────────────────
log "attach 대기(최대 60s): tun_srsue IP..."
IP=""
for i in $(seq 1 60); do
  IP="$(docker exec "$UE_CT" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1 || true)"
  [[ -n "$IP" ]] && break
  sleep 1
done
[[ -n "$IP" ]] || { warn "tun_srsue 미생성 — attach 실패 가능. UE 로그:"; docker logs "$UE_CT" 2>&1 | tail -25; die "G0 미통과"; }
log "✓ tun_srsue = $IP  (RRC+attach+기본 베어러 성립)"

# ── 4. 데이터 베어러 검증: UPF 게이트웨이 ping (셀룰러 경유) ─────────────────
GW="$(echo "$IP" | awk -F. '{print $1"."$2"."$3".1"}')"
log "ping(베어러 경유) GW=$GW ..."
if docker exec "$UE_CT" ping -I tun_srsue -c3 -W2 "$GW" >/dev/null 2>&1; then
  log "✓ ping OK — 데이터 베어러 동작 (G0 통과 ✅)"
else
  warn "GW ping 실패 — UPF/APN 라우팅 확인. (attach 자체는 성립: tun IP 할당됨)"
fi
echo; log "G0 요약: EPC + srsenb + srsue(단일=UAV) 동작. 다음 = 멀티UE(30-add-ue.sh, multi-eNB) → G1(40-g1-c2.sh)."
