#!/usr/bin/env bash
# ============================================================================
# A1 — EC2 호스트 준비 (게이트 0 전제조건)
#   docker / docker compose / git 설치, SCTP 모듈(S1AP), /dev/net/tun 확인.
#   멱등(idempotent): 이미 있으면 건너뜀. 재로그인 없이 sg docker 로 그룹 즉시반영 안내.
#
#   사용:  sudo bash 00-ec2-prep.sh
#   대상:  Ubuntu 22.04 (c5.2xlarge 권장) — 인바운드 SSH만.
# ============================================================================
set -euo pipefail

log(){ printf '\033[1;36m[A1]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[A1!]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[A1✗]\033[0m %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "root 로 실행: sudo bash $0"
. /etc/os-release 2>/dev/null || true
[[ "${ID:-}" == "ubuntu" ]] || warn "Ubuntu 외 OS(${ID:-unknown}) — 패키지명 다를 수 있음."

TARGET_USER="${SUDO_USER:-${USER:-ubuntu}}"

# ── 1. 패키지 (docker.io, compose v2 플러그인, git) ──────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  log "docker / git 설치..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y docker.io docker-compose-v2 git iproute2 tcpdump
else
  log "docker 이미 설치됨 ($(docker --version))"
fi
systemctl enable --now docker >/dev/null 2>&1 || warn "docker 서비스 enable 실패(수동확인)"

# compose v2 확인 (plugin 형태 'docker compose')
if docker compose version >/dev/null 2>&1; then
  log "compose: $(docker compose version | head -1)"
else
  warn "'docker compose' 미탐지 — docker-compose-v2 또는 compose 플러그인 설치 필요."
fi

# ── 2. docker 그룹 (sudo 없이 docker 실행) ──────────────────────────────────
if ! id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
  usermod -aG docker "$TARGET_USER"
  warn "$TARGET_USER 를 docker 그룹에 추가 — 새 세션부터 적용. 지금 바로면:  newgrp docker"
else
  log "$TARGET_USER 이미 docker 그룹"
fi

# ── 3. SCTP 모듈 (MME S1AP = SCTP 36412) ────────────────────────────────────
if modprobe sctp 2>/dev/null && lsmod | grep -q '^sctp'; then
  log "sctp 모듈 로드됨"
  # 재부팅 후에도 유지
  echo sctp > /etc/modules-load.d/sctp.conf
else
  warn "sctp 모듈 로드 실패 — 커널에 따라 'linux-modules-extra-$(uname -r)' 필요할 수 있음:"
  warn "    apt-get install -y linux-modules-extra-\$(uname -r) && modprobe sctp"
fi

# ── 4. /dev/net/tun (UE/UPF TUN 디바이스) ───────────────────────────────────
if [[ -c /dev/net/tun ]]; then
  log "/dev/net/tun OK"
else
  warn "/dev/net/tun 없음 — 생성 시도..."
  mkdir -p /dev/net
  mknod /dev/net/tun c 10 200 && chmod 600 /dev/net/tun && log "생성됨" \
    || die "/dev/net/tun 생성 실패 — UE 동작 불가."
fi

# ── 5. 자원 점검(경고만) ────────────────────────────────────────────────────
CPUS=$(nproc); MEMG=$(awk '/MemTotal/{printf "%.0f",$2/1024/1024}' /proc/meminfo)
log "자원: ${CPUS} vCPU / ${MEMG} GB RAM"
[[ "$CPUS" -ge 8 ]] || warn "vCPU<8 — EPC+srsenb+srsue×3+broker 는 c5.2xlarge(8vCPU) 권장."
[[ "$MEMG" -ge 14 ]] || warn "RAM<14GB — 풀스택엔 부족할 수 있음."

log "A1 완료. 다음:  bash 10-epc-up.sh   (sudo 불필요, docker 그룹 세션에서)"
