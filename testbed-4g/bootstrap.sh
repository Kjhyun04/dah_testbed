#!/usr/bin/env bash
# ============================================================================
# 일괄 부트스트랩 — A(환경)부터 G0(단일UE attach)까지 (로컬 WSL2 / EC2 공용)
#   A1 호스트준비(00) → A2 빌드+EPC기동+.env.4g(10) → A3 가입자등록(provision)
#   → G0 srsRAN 단일UE attach 검증(20-ran-up)
#   ★검증(2026-07-01) 반영: upstream docker_open5gs 실제 구조에 맞춤(4 불일치 수정).
#
#   사용:  bash bootstrap.sh        (WSL2 Ubuntu 안에서 / 또는 EC2)
#   결과:  EPC 코어 기동 + 가입자(UE1) 등록 + srsUE attach(tun_srsue IP) = G0.
#   참고:  최초 1회 이미지 빌드(open5gs/srsRAN 컴파일)로 수~십분 소요.
#
#   ⚠️ 실제 공격 실행은 사용자. 이 스크립트는 인프라/배선만 세운다.
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
S="$HERE/scripts"
log(){ printf '\033[1;32m[A]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[A!]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[A✗]\033[0m %s\n' "$*" >&2; exit 1; }

# ── 환경 감지: 로컬(WSL2/Docker Desktop) vs EC2(apt) ────────────────────────
#   WSL2(/proc/version 에 microsoft) → 로컬. 강제: FORCE_LOCAL=1 / FORCE_EC2=1
IS_LOCAL=0
grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null && IS_LOCAL=1
[[ "${FORCE_LOCAL:-0}" == 1 ]] && IS_LOCAL=1
[[ "${FORCE_EC2:-0}" == 1 ]] && IS_LOCAL=0

# ── A1: 호스트 준비 ─────────────────────────────────────────────────────────
if [[ "$IS_LOCAL" == 1 ]]; then
  log "A1 — 로컬(WSL2/Docker Desktop) 호스트 준비"
  bash "$S/00-local-prep.sh"
else
  log "A1 — EC2(apt) 호스트 준비 (docker/sctp/tun)"
  if command -v docker >/dev/null 2>&1 && docker ps >/dev/null 2>&1 \
     && lsmod 2>/dev/null | grep -q '^sctp' && [[ -c /dev/net/tun ]]; then
    log "A1 전제 이미 충족 — 건너뜀"
  else
    sudo bash "$S/00-ec2-prep.sh"
  fi
fi

# docker 그룹이 현재 셸에 반영됐는지: 아니면 sg docker 로 나머지 실행
DOCKER_OK=1; docker ps >/dev/null 2>&1 || DOCKER_OK=0
RUN(){ if [[ "$DOCKER_OK" -eq 1 ]]; then bash -c "$1"; else sg docker -c "$1"; fi; }

# ── A2: 빌드 + 슬림 EPC 기동 + .env.4g 생성 ─────────────────────────────────
log "A2 — docker_open5gs 빌드 + EPC 기동 → .env.4g (최초 빌드 수~십분)"
RUN "bash '$S/10-epc-up.sh'"
[[ -f "$HERE/.env.4g" ]] || die ".env.4g 미생성 — 10-epc-up.sh 로그 확인."

# ── A3: 가입자 등록 (UE1, OPc 계산해 정합) ──────────────────────────────────
log "A3 — HSS 가입자 등록 (UE1, srsUE 정합)"
RUN "bash '$S/provision.sh'" \
  || warn "가입자 등록 실패 — WebUI(http://<host>:9999, admin/1423) 확인."

# ── G0: srsRAN 단일 UE attach 검증 (--no-g0 로 생략 가능) ────────────────────
if [[ "${SKIP_G0:-0}" != 1 ]]; then
  log "G0 — srsRAN 단일 UE attach 검증"
  RUN "bash '$S/20-ran-up.sh'" || warn "G0 검증 미통과 — 20-ran-up.sh 로그 확인."
else
  log "G0 생략(SKIP_G0=1)"
fi

# ── 요약 ────────────────────────────────────────────────────────────────────
echo
log "════════ 부트스트랩 완료 ════════"
log ".env.4g:"; grep -vE '^\s*#|^\s*$' "$HERE/.env.4g" | sed 's/^/     /'
cat <<EOF

상태: EPC(슬림) + 가입자(UE1) + srsUE 단일 attach(UAV) = G0.
다음 단계(검증 완료, 스크립트로 재현):
  • 멀티UE = multi-eNB:  bash scripts/30-add-ue.sh 2   # GCS (필요시 3=ROGUE)
  • G1 C2-over-LTE:      bash scripts/40-g1-c2.sh       # ArduPilot SITL ↔ GCS
  • G2 폐루프+GPS분리:   bash scripts/50-g2b-gps.sh      # GPS=dahnet, C2=셀룰러

⚠️ 공격(TM1/TM3) 실행은 사용자. 본 스크립트는 인프라/배선만.
EOF
