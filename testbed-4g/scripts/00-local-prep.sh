#!/usr/bin/env bash
# ============================================================================
# A1(로컬) — WSL2 + Docker Desktop 호스트 준비 (EC2 대신 로컬 구현용)
#   EC2 판은 apt 로 docker 설치. 로컬 판은 Docker Desktop 사용 → 설치 대신:
#   ① docker 데몬 연결 확인(Docker Desktop + WSL integration)  ← 먼저(아래 ② 순서 중요)
#   ② sctp 커널모듈 로드(WSL2 공유커널, MME S1AP=SCTP)         ← VM 가동 후 로드해야 유지
#   ③ /dev/net/tun 확인
#
#   ★검증완료: WSL2 단일 공유커널 → 호스트 modprobe sctp 하면 컨테이너가 즉시 SCTP 인식.
#   ★주의:    sctp 는 WSL2 VM 재시작 시 휘발. Docker Desktop 재시작했다면 이 스크립트 재실행.
#
#   실행 위치:  반드시 WSL2 Ubuntu 안에서(= Docker Desktop WSL integration 켜진 배포판).
#              (git-bash/PowerShell 아님 — modprobe/sudo 불가)
#   사용:       bash 00-local-prep.sh
# ============================================================================
set -euo pipefail
log(){ printf '\033[1;36m[A1-local]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[A1-local!]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[A1-local✗]\033[0m %s\n' "$*" >&2; exit 1; }

# ── 0. 실행환경 가드 (Linux/WSL 안이어야 함) ────────────────────────────────
[[ "$(uname -s)" == "Linux" ]] || die "WSL2 Ubuntu 안에서 실행할 것(git-bash/PowerShell 불가)."
if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
  log "WSL2 감지 (배포판=${WSL_DISTRO_NAME:-?})"
else
  warn "WSL2 표식 없음 — 네이티브 Linux 로컬 Docker 로 간주(계속)."
fi

# ── 1. Docker 데몬 연결 먼저 (VM 가동 확인 → 이후 sctp 로드가 유지됨) ────────
command -v docker >/dev/null 2>&1 \
  || die "docker 명령 없음 — Docker Desktop ▸ Settings ▸ Resources ▸ WSL integration 에서 '${WSL_DISTRO_NAME:-이 배포판}' ON."
docker version >/dev/null 2>&1 \
  || die "docker 데몬 연결 실패 — Docker Desktop 을 먼저 실행(엔진 기동 대기 후 재실행)."
log "docker 데몬 OK ($(docker version -f '{{.Server.Version}}' 2>/dev/null))"

# ── 2. SCTP 커널모듈 (단일 공유커널 → 컨테이너에도 즉시 적용) ────────────────
if grep -qiE '^SCTP ' /proc/net/protocols 2>/dev/null; then
  log "SCTP 이미 로드됨"
else
  log "SCTP 로드(sudo modprobe sctp)..."
  sudo modprobe sctp 2>/dev/null && grep -qiE '^SCTP ' /proc/net/protocols \
    && log "SCTP 로드 완료" \
    || die "SCTP 로드 실패 — 'find /lib/modules -name sctp.ko' 로 모듈 존재 확인."
fi
# (선택) 컨테이너 가시성 즉석 검증 — busybox 있을 때만, 빠르게
if docker image inspect busybox >/dev/null 2>&1; then
  docker run --rm busybox sh -c 'grep -qi "^SCTP " /proc/net/protocols' \
    && log "컨테이너 SCTP 가시성 확인됨" \
    || warn "컨테이너에서 SCTP 미가시 — Docker Desktop 재시작 후 sctp 가 날아갔을 수 있음(재실행)."
fi

# ── 3. /dev/net/tun ─────────────────────────────────────────────────────────
[[ -c /dev/net/tun ]] && log "/dev/net/tun OK" || {
  warn "/dev/net/tun 없음 — 생성(sudo)..."
  sudo mkdir -p /dev/net && sudo mknod /dev/net/tun c 10 200 && sudo chmod 666 /dev/net/tun \
    && log "생성됨" || die "/dev/net/tun 생성 실패 — UE 동작 불가."
}

# ── 4. 자원 점검 ────────────────────────────────────────────────────────────
CPUS=$(nproc); MEMG=$(awk '/MemTotal/{printf "%.1f",$2/1024/1024}' /proc/meminfo)
log "자원: ${CPUS} vCPU / ${MEMG} GB RAM (WSL2 할당)"
awk "BEGIN{exit !($CPUS>=8)}"  || warn "vCPU<8 — %USERPROFILE%\\.wslconfig 의 [wsl2] processors 상향 권장."
awk "BEGIN{exit !($MEMG>=14)}" || warn "RAM<14GB — .wslconfig 의 [wsl2] memory 상향 권장(예: memory=16GB)."

log "A1(local) 완료. 다음:  bash 10-epc-up.sh"
