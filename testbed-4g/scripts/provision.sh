#!/usr/bin/env bash
# ============================================================================
# A3 — HSS 가입자 등록 (srsUE 와 정합) — webui 컨테이너의 open5gs-dbctl 사용
#   ★검증(2026-07-01): srsUE 는 .env 의 UE1_OP(=OP) 사용, dbctl 은 OPC 요구.
#     → OPc = OP XOR AES128(K=UE1_KI, OP=UE1_OP) 를 계산해 등록(미일치 시 attach 실패).
#   등록식:  docker exec webui misc/db/open5gs-dbctl add_ue_with_apn IMSI KI OPC internet
#
#   사용:  bash provision.sh        (WORK=~/docker_open5gs 자동)
# ============================================================================
set -euo pipefail
log(){ printf '\033[1;36m[A3]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[A3!]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[A3✗]\033[0m %s\n' "$*" >&2; exit 1; }

WORK="${WORK:-$HOME/docker_open5gs}"
WEBUI="${WEBUI:-webui}"
APN="${APN:-internet}"
SRC_ENV="$WORK/.env"
[[ -f "$SRC_ENV" ]] || die "$SRC_ENV 없음 — 먼저 10-epc-up.sh"
getv(){ grep -E "^$1=" "$SRC_ENV" | head -1 | cut -d= -f2; }

IMSI="${UE1_IMSI:-$(getv UE1_IMSI)}"
KI="${UE1_KI:-$(getv UE1_KI)}"
OP="${UE1_OP:-$(getv UE1_OP)}"
[[ -n "$IMSI" && -n "$KI" && -n "$OP" ]] || die "UE1_IMSI/KI/OP 파싱 실패 (.env 확인)."

# ── OPc = OP XOR AES128-ECB(K=KI, OP) ───────────────────────────────────────
compute_opc(){
  local k="$1" op="$2" c
  c=$(printf "%s" "$op" | xxd -r -p | openssl enc -aes-128-ecb -K "$k" -nopad 2>/dev/null | xxd -p | tr -d '\n')
  [[ -n "$c" ]] || return 1
  python3 -c "print(bytes(a^b for a,b in zip(bytes.fromhex('$op'),bytes.fromhex('$c'))).hex())" 2>/dev/null \
    || python -c "print(bytes(a^b for a,b in zip(bytes.fromhex('$op'),bytes.fromhex('$c'))).hex())"
}
OPC="${UE1_OPC:-$(compute_opc "$KI" "$OP" || true)}"
[[ -n "$OPC" ]] || die "OPc 계산 실패 — openssl/python 확인. (수동: UE1_OPC=<opc> 지정)"
log "가입자: IMSI=$IMSI  KI=$KI"
log "        OP=$OP → OPC=$OPC (계산)"

# ── webui 컨테이너 존재 확인 후 등록 ────────────────────────────────────────
docker ps --format '{{.Names}}' | grep -qx "$WEBUI" || {
  WEBUI="$(docker ps --format '{{.Names}}' | grep -iE 'webui' | head -1 || true)"
  [[ -n "$WEBUI" ]] || die "webui 컨테이너 없음 — EPC 기동 확인(10-epc-up.sh)."
}
log "dbctl(@$WEBUI) add_ue_with_apn ..."
if docker exec "$WEBUI" misc/db/open5gs-dbctl add_ue_with_apn "$IMSI" "$KI" "$OPC" "$APN" 2>&1; then
  log "등록 성공"
else
  warn "add_ue_with_apn 실패 — 이미 등록됐거나 dbctl 경로 상이. 현재 가입자 목록:"
  docker exec "$WEBUI" misc/db/open5gs-dbctl showpgw 2>/dev/null || docker exec "$WEBUI" misc/db/open5gs-dbctl showall 2>/dev/null || true
fi
log "A3 완료. (WebUI 확인: http://<host>:9999  admin/1423)  다음: bash 20-ran-up.sh"
