#!/usr/bin/env bash
# ============================================================================
# aws-resume — 공유 EC2 를 stop→start 로 다시 켠 뒤 테스트베드를 재기동하는 원스텝.
#
#   왜 필요한가:
#     • 이미지/가입자DB 는 EBS 에 남아 rebuild/재-provision 불필요(빠른 재개).
#     • 그러나 stop→start 후 (1) 호스트 커널 상태(sctp/tun) 와 (2) srsRAN 라디오
#       attach 는 살아나지 않는다 → EPC 컨테이너를 되살리고 RAN 을 재수립해야 G0.
#
#   이 스크립트가 하는 일 (멱등):
#     A) 호스트 준비 재확인: sctp 모듈 / /dev/net/tun / docker 데몬  (부족하면 00-ec2-prep)
#     B) EPC 코어(mongo/hss/pcrf/smf/upf/sgw/mme/webui) 되살리기(docker start)
#     C) G0 재수립: 20-ran-up.sh (srsenb/srsue force-recreate → attach 대기)
#     D) 다음 게이트(G1/G2/viz) 재실행 안내 — 실험 재개는 사용자 몫(역할경계)
#
#   사용:  bash scripts/aws-resume.sh            # 기본: A→B→C(G0 까지)
#          RAN=0 bash scripts/aws-resume.sh      # RAN 재수립 생략(EPC 만 되살림)
#   대상:  Ubuntu EC2 (WSL 로컬에선 00-local-prep.sh 를 쓰세요 — 여긴 EC2 재개 전용)
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
S="$HERE"
log(){  printf '\033[1;36m[resume]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[resume!]\033[0m %s\n' "$*"; }
die(){  printf '\033[1;31m[resume✗]\033[0m %s\n' "$*" >&2; exit 1; }

WORK="${WORK:-$HOME/docker_open5gs}"                     # 10-epc-up 과 동일 기본값
EPC_COMPOSE="${EPC_COMPOSE:-4g-volte-deploy.yaml}"
EPC_SVCS="${EPC_SVCS:-mongo hss pcrf smf upf sgw mme webui}"

# WSL 에서 잘못 부른 경우 가드(치명적이진 않으나 의도와 다름)
if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
  warn "WSL2 감지 — 이 스크립트는 EC2 재개 전용입니다. 로컬은 bootstrap.sh(00-local-prep) 사용."
fi

# ── A) 호스트 준비 재확인 (sctp / tun / docker) ─────────────────────────────
need_prep=0
lsmod 2>/dev/null | grep -q '^sctp' || { warn "sctp 미로드"; need_prep=1; }
[[ -c /dev/net/tun ]]              || { warn "/dev/net/tun 없음"; need_prep=1; }
docker ps >/dev/null 2>&1          || { warn "docker 데몬 미가동/권한없음"; need_prep=1; }
if [[ "$need_prep" == 1 ]]; then
  log "A — 호스트 준비 재실행(00-ec2-prep.sh)"
  sudo bash "$S/00-ec2-prep.sh"
  # docker 그룹이 현재 셸에 아직 반영 안 됐을 수 있음
  docker ps >/dev/null 2>&1 || { warn "docker 그룹 미반영 — 'newgrp docker' 후 재실행하세요."; exit 1; }
else
  log "A — 호스트 준비 OK (sctp/tun/docker 정상)"
fi

# ── B) EPC 코어 되살리기 ────────────────────────────────────────────────────
log "B — EPC 코어 재기동"
started=0; missing=0
for svc in $EPC_SVCS; do
  if docker ps -aq -f "name=^${svc}$" | grep -q .; then
    docker start "$svc" >/dev/null 2>&1 && started=$((started+1)) \
      || warn "  $svc start 실패"
  else
    missing=$((missing+1))
  fi
done
if [[ "$missing" -gt 0 && "$started" -eq 0 ]]; then
  die "EPC 컨테이너가 없습니다 — 최초 구축이 필요합니다:  bash bootstrap.sh"
fi
[[ "$missing" -gt 0 ]] && warn "일부 EPC 서비스 부재($missing개) — 필요 시 bash scripts/10-epc-up.sh"
log "  EPC 기동 상태:"
docker ps --format '   {{.Names}}\t{{.Status}}' | grep -E "$(echo "$EPC_SVCS" | tr ' ' '|')" || true

# ── C) G0 재수립 (RAN attach 은 stop 후 반드시 재수립) ──────────────────────
if [[ "${RAN:-1}" == 1 ]]; then
  log "C — G0 재수립(20-ran-up.sh: srsenb/srsue force-recreate + attach 대기)"
  bash "$S/20-ran-up.sh" || warn "G0 재수립 미통과 — 20-ran-up.sh 로그 확인."
else
  log "C — RAN 재수립 생략(RAN=0). 필요 시:  bash scripts/20-ran-up.sh"
fi

# ── D) 요약 & 다음 단계 안내 ────────────────────────────────────────────────
cat <<EOF

$(printf '\033[1;32m[resume]\033[0m') ════════ 재개 완료 ════════
 • 이미지/가입자DB 는 EBS 에 보존됨 → rebuild/재-provision 불필요.
 • 상위 게이트/시각화는 실험 재개 시 재실행(공격·비행 실행은 사용자):
     G1 C2-over-LTE :  bash scripts/40-g1-c2.sh
     G2 폐루프+GPS  :  bash scripts/50-g2b-gps.sh
     멀티UE 추가    :  bash scripts/30-add-ue.sh <N>
     Gazebo 시각화  :  bash scripts/60-viz-gazebo.sh   (noVNC 는 SSH 터널: ssh -L 6080:localhost:6080)
EOF
