#!/usr/bin/env bash
# ============================================================================
# multi-eNB — (eNB+UE) 쌍 N 추가 (브로커 없는 멀티UE). N=2(GCS), N=3(ROGUE)...
#   ★설계: srsRAN ZMQ는 1 eNB=1 UE. 멀티UE를 GNU Radio 브로커(취약) 대신
#     "eNB를 UE 수만큼" 띄워 해결. 각 쌍은 IP로 구분 → 포트 2000/2001 재사용 가능.
#     모두 같은 EPC(MME)에 S1AP 연결 → 같은 APN 풀 → UE-to-UE 도달(TM1/C2 전제).
#   ★검증된 단일 UE 구성(20-ran-up)을 그대로 복제하므로 안정적.
#
#   사용:  bash 30-add-ue.sh <N>        (N=2,3,...; pair1=기존 srsue_zmq)
#   생성:  srslte/{enb_zmq,rr_enb_zmq,sib_enb_zmq,rb_enb_zmq,ue_zmq}${N}.conf + pair${N}.yaml
#   결과:  srsenb_zmq${N} + srsue_zmq${N} attach, 가입자 등록, UE-to-UE ping 검증.
# ============================================================================
set -euo pipefail
log(){ printf '\033[1;36m[UE%s]\033[0m %s\n' "${N:-?}" "$*"; }
warn(){ printf '\033[1;33m[UE%s!]\033[0m %s\n' "${N:-?}" "$*"; }
die(){ printf '\033[1;31m[UE%s✗]\033[0m %s\n' "${N:-?}" "$*" >&2; exit 1; }

N="${1:?usage: 30-add-ue.sh <N>  (N=2,3,...)}"
[[ "$N" =~ ^[2-9]$ ]] || die "N 은 2~9 (pair1 은 기존 srsue_zmq)."
WORK="${WORK:-$HOME/docker_open5gs}"
SRS="$WORK/srslte"; WEBUI="${WEBUI:-webui}"
[[ -d "$SRS" ]] || die "$SRS 없음 — 먼저 10-epc-up.sh"
cd "$WORK"

# ── 식별자/주소 (쌍별 유니크) ───────────────────────────────────────────────
ENB_IP="172.22.0.$((50+2*N))"            # N=2→.54
UE_IP="172.22.0.$((51+2*N))"             # N=2→.55
ENB_ID="$(printf '0x%X' $((0x19B + N - 1)))"   # N=2→0x19C
PCI="$N"; CELL_ID="$(printf '0x%02X' "$N")"    # N=2→pci2/cell 0x02
getv(){ grep -E "^$1=" "$WORK/.env" | head -1 | cut -d= -f2; }
KI="$(getv UE1_KI)"; OP="$(getv UE1_OP)"
BASEIMSI="$(getv UE1_IMSI)"              # 001011234567895
IMSI="$(printf '%015d' $(( 10#$BASEIMSI + N - 1 )))"   # N=2→...896 (K/OP 공유, IMSI만 +)
log "ENB_IP=$ENB_IP UE_IP=$UE_IP enb_id=$ENB_ID pci=$PCI IMSI=$IMSI"

# ── 1. srsRAN 설정 생성 (pair1 템플릿 복제 + 식별자 치환) ────────────────────
log "srslte/*_enb_zmq${N}.conf + ue_zmq${N}.conf 생성"
sed -E "s/^enb_id\s*=.*/enb_id = ${ENB_ID}/" "$SRS/enb_zmq.conf" > "$SRS/enb_zmq${N}.conf"
sed -E "s/cell_id\s*=\s*0x[0-9A-Fa-f]+/cell_id = ${CELL_ID}/; s/pci\s*=\s*[0-9]+/pci = ${PCI}/" \
    "$SRS/rr_enb_zmq.conf" > "$SRS/rr_enb_zmq${N}.conf"
cp "$SRS/sib_enb_zmq.conf" "$SRS/sib_enb_zmq${N}.conf"
cp "$SRS/rb_enb_zmq.conf"  "$SRS/rb_enb_zmq${N}.conf"
# UE: IMSI 만 실값으로 박음(init 의 UE1_IMSI 치환을 무력화). K/OP 는 공유(UE1_OP/UE1_KI 유지).
sed -E "s/^imsi\s*=.*/imsi = ${IMSI}/" "$SRS/ue_zmq.conf" > "$SRS/ue_zmq${N}.conf"

# ── 2. compose 생성 (enb${N}+ue${N}, IP/COMPONENT override) ─────────────────
cat > "$WORK/pair${N}.yaml" <<YAML
services:
  srsenb_zmq${N}:
    image: docker_srslte
    container_name: srsenb_zmq${N}
    stdin_open: true
    tty: true
    privileged: true
    volumes: [ "./srslte:/mnt/srslte", "/etc/localtime:/etc/localtime:ro" ]
    env_file: [ .env ]
    environment: [ "COMPONENT_NAME=enb_zmq${N}", "SRS_ENB_IP=${ENB_IP}", "SRS_UE_IP=${UE_IP}" ]
    networks: { default: { ipv4_address: ${ENB_IP} } }
  srsue_zmq${N}:
    image: docker_srslte
    container_name: srsue_zmq${N}
    stdin_open: true
    tty: true
    cap_add: [ NET_ADMIN ]
    privileged: true
    volumes: [ "./srslte:/mnt/srslte", "/etc/localtime:/etc/localtime:ro" ]
    env_file: [ .env ]
    environment: [ "COMPONENT_NAME=ue_zmq${N}", "SRS_ENB_IP=${ENB_IP}", "SRS_UE_IP=${UE_IP}" ]
    networks: { default: { ipv4_address: ${UE_IP} } }
networks:
  default: { external: true, name: docker_open5gs_default }
YAML

# ── 3. 가입자 등록 (IMSI_N, OPc 계산) ───────────────────────────────────────
C=$(printf "%s" "$OP" | xxd -r -p | openssl enc -aes-128-ecb -K "$KI" -nopad 2>/dev/null | xxd -p | tr -d '\n')
OPC=$( { python3 -c "print(bytes(a^b for a,b in zip(bytes.fromhex('$OP'),bytes.fromhex('$C'))).hex())" 2>/dev/null \
        || python -c "print(bytes(a^b for a,b in zip(bytes.fromhex('$OP'),bytes.fromhex('$C'))).hex())"; } )
log "가입자 등록 IMSI=$IMSI OPC=$OPC"
docker exec "$WEBUI" misc/db/open5gs-dbctl add_ue_with_apn "$IMSI" "$KI" "$OPC" internet 2>&1 | tail -2 \
  || warn "등록 실패(이미 있음?) — 계속."

# ── 4. 기동 (eNB→UE 순서, ZMQ 동기화 위해 force-recreate) ───────────────────
log "srsenb_zmq${N} 기동"; docker compose -f "pair${N}.yaml" up -d --force-recreate "srsenb_zmq${N}"
sleep 4
log "srsue_zmq${N} 기동"; docker compose -f "pair${N}.yaml" up -d --force-recreate "srsue_zmq${N}"

# ── 5. attach 검증 ──────────────────────────────────────────────────────────
log "attach 대기(최대 120s)..."   # 다중 UE/CPU 포화 시 attach 가 60s 초과 가능(오탐 방지)
IP2=""
for i in $(seq 1 120); do
  IP2="$(docker exec "srsue_zmq${N}" ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1 || true)"
  [[ -n "$IP2" ]] && break; sleep 1
done
[[ -n "$IP2" ]] || { warn "tun 미생성. 로그:"; docker logs "srsue_zmq${N}" 2>&1 | tail -20; die "UE${N} attach 실패"; }
log "✓ srsue_zmq${N} attach: tun_srsue=$IP2"

# ── 6. ★UE-to-UE 도달성 (TM1/C2 전제) — pair1 UE 와 상호 ping ───────────────
IP1="$(docker exec srsue_zmq ip -o -4 addr show tun_srsue 2>/dev/null | awk '{print $4}' | cut -d/ -f1 || true)"
if [[ -n "$IP1" ]]; then
  log "★UE-to-UE 검증: UE${N}($IP2) → UE1($IP1) ping (PGW hairpin)"
  if docker exec "srsue_zmq${N}" ping -I tun_srsue -c3 -W2 "$IP1" >/dev/null 2>&1; then
    log "✓✓ UE-to-UE 도달 — TM1/C2 전제 성립 ✅"
  else
    warn "✗ UE-to-UE 불통 — UPF가 UE간 hairpin 미허용. (각 UE 개별 attach 는 OK)"
    warn "  → 다음: UPF ip_forward / APN 라우팅 손질 필요."
  fi
else warn "UE1 tun 미확인 — pair1(srsue_zmq) 가동 중인지 확인."; fi
log "UE${N} 완료. (멀티UE = pair1 + pair${N})"
