#!/usr/bin/env bash
# ============================================================================
# A2 — docker_open5gs 이미지 빌드 + 슬림 EPC 기동 → testbed-4g/.env.4g 생성
#   ★검증(2026-07-01) 반영: upstream 실제 구조에 맞춤(4가지 불일치 수정).
#   1) 이미지는 pull 아님 → BUILD (base→docker_open5gs, srslte→docker_srslte)
#   2) 4G compose = '4g-volte-deploy.yaml' (epc-deploy.yaml 은 존재하지 않음)
#   3) IMS/VoLTE 체인(kamailio·pyhss·osmo) 회피 → --no-deps 로 EPC 코어 9개만 기동
#      (mme 가 osmomsc 에 depends → --no-deps 로 끊음. 데이터 베어러엔 불필요)
#   4) srsRAN 이미지명 = docker_srslte, 네트워크 docker_open5gs_default
#
#   사용:  bash 10-epc-up.sh
#   오버라이드: WORK=~/docker_open5gs EPC_COMPOSE=4g-volte-deploy.yaml bash 10-epc-up.sh
# ============================================================================
set -euo pipefail
log(){ printf '\033[1;36m[A2]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[A2!]\033[0m %s\n' "$*"; }
die(){ printf '\033[1;31m[A2✗]\033[0m %s\n' "$*" >&2; exit 1; }

HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${WORK:-$HOME/docker_open5gs}"
REPO="${REPO:-https://github.com/herlesupreeth/docker_open5gs}"
EPC_COMPOSE="${EPC_COMPOSE:-4g-volte-deploy.yaml}"     # ★정정
# EPC 코어만(IMS/osmo 제외). mme 의 osmomsc 의존은 --no-deps 로 끊는다.
EPC_SVCS="${EPC_SVCS:-mongo hss pcrf smf upf sgwc sgwu mme webui}"
ENV_OUT="$HERE/.env.4g"; ENV_TPL="$HERE/.env.4g.example"

command -v docker >/dev/null 2>&1 || die "docker 없음 — 먼저 00-local-prep.sh"
docker version >/dev/null 2>&1 || die "docker 데몬 연결 실패."

# ── 1. clone (★CRLF 방지: 컨테이너가 exec 하는 .sh 의 shebang 깨짐 방지) ─────
if [[ ! -d "$WORK/.git" ]]; then
  log "clone → $WORK (core.autocrlf=false)"
  git clone --depth 1 -c core.autocrlf=false -c core.eol=lf "$REPO" "$WORK"
else log "repo 존재 ($WORK)"; fi
cd "$WORK"
[[ -f "$EPC_COMPOSE" ]] || die "$EPC_COMPOSE 없음 — ls *deploy*.yaml 확인."
# Windows(autocrlf=true)로 이미 CRLF면 LF 정규화 — 안 하면 init 스크립트 'no such file'.
if find . -path ./.git -prune -o -name '*.sh' -print0 2>/dev/null | xargs -0 grep -lU $'\r' 2>/dev/null | grep -q .; then
  warn "CRLF 감지 → LF 정규화(.sh/.conf/.yaml/.yml) + 이미지 재빌드 필요"
  find . -path ./.git -prune -o -type f \( -name '*.sh' -o -name '*.conf' -o -name '*.yaml' -o -name '*.yml' \) -print0 \
    | xargs -0 sed -i 's/\r$//' 2>/dev/null || true
  docker image rm -f docker_open5gs docker_srslte >/dev/null 2>&1 || true   # CRLF 박힌 이미지 폐기→재빌드
fi

# ── 2. .env: DOCKER_HOST_IP 갱신(나머지 기본값 그대로) ──────────────────────
# hostname -I 는 Linux 전용(git-bash 미지원) → set -e 안전하게 가드.
HOST_IP="$( { hostname -I 2>/dev/null || true; } | awk '{print $1}' )" || true
HOST_IP="${HOST_IP:-127.0.0.1}"
sed -i -E "s|^DOCKER_HOST_IP=.*|DOCKER_HOST_IP=${HOST_IP}|" .env 2>/dev/null || true
log "DOCKER_HOST_IP=${HOST_IP}"

# ── 3. 이미지 빌드 (멱등: 있으면 skip). ★최장 단계(open5gs/srsRAN 컴파일) ───
if ! docker image inspect docker_open5gs >/dev/null 2>&1; then
  log "build docker_open5gs (./base) — 수~십분 소요..."; docker build -t docker_open5gs ./base
else log "docker_open5gs 이미지 존재"; fi
if ! docker image inspect docker_srslte >/dev/null 2>&1; then
  log "build docker_srslte (./srslte) — srsRAN_4G 컴파일..."; docker build -t docker_srslte ./srslte
else log "docker_srslte 이미지 존재"; fi

# ── 3.5. 슬림 EPC 보정: MME의 SGsAP(osmomsc/VLR) 비활성화 ────────────────────
# osmomsc 를 --no-deps 로 뺐는데 mme.yaml 의 sgsap 가 남아 있으면 MME 가 없는 VLR
# 연결에 30s 블로킹 → S1 Setup 처리 지연 → eNB 'S1setup failed'. → sgsap 블록 제거(멱등).
if grep -q '^    sgsap:' "$WORK/mme/mme.yaml" 2>/dev/null; then
  log "MME sgsap 블록 제거(슬림 EPC 보정)"
  sed -i '/^    sgsap:/,/^    gummei:/{/^    gummei:/!d;}' "$WORK/mme/mme.yaml"
fi

# ── 4. 슬림 EPC 기동 (--no-deps 로 IMS/osmo 체인 차단) ──────────────────────
log "EPC 기동(mongo 먼저): $EPC_SVCS"
docker compose -f "$EPC_COMPOSE" up -d --no-deps mongo
sleep 5
docker compose -f "$EPC_COMPOSE" up -d --no-deps $EPC_SVCS
sleep 6
log "기동된 컨테이너:"; docker compose -f "$EPC_COMPOSE" ps --format '   {{.Name}}\t{{.State}}' 2>/dev/null | grep -E 'mongo|hss|pcrf|smf|upf|sgw|mme|webui' || true

# ── 5. 값 확정(대부분 .env 기지값, 그래도 검증) ─────────────────────────────
SRC_ENV="$WORK/.env"
getv(){ grep -E "^$1=" "$SRC_ENV" | head -1 | cut -d= -f2; }
EPC_NET="${EPC_NET:-docker_open5gs_default}"
MME_IP="${MME_IP:-$(getv MME_IP)}";          MME_IP="${MME_IP:-172.22.0.9}"
SRS_ENB_IP="${SRS_ENB_IP:-$(getv SRS_ENB_IP)}"; SRS_ENB_IP="${SRS_ENB_IP:-172.22.0.22}"
SRS_UE_IP="${SRS_UE_IP:-$(getv SRS_UE_IP)}";  SRS_UE_IP="${SRS_UE_IP:-172.22.0.34}"
SRSRAN_IMAGE="${SRSRAN_IMAGE:-docker_srslte}"
DAHNET="${DAHNET:-$(docker network ls --format '{{.Name}}' | grep -i dahnet | head -1)}"; DAHNET="${DAHNET:-testbed_dahnet}"
# 실제 MME 컨테이너 IP 교차검증
MME_CT="$(docker ps --format '{{.Names}}' | grep -iE '(^|_)mme$|mme' | head -1 || true)"
if [[ -n "$MME_CT" ]]; then
  RT="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$MME_CT" 2>/dev/null | awk '{print $1}')"
  [[ -n "$RT" && "$RT" != "$MME_IP" ]] && { warn "MME 실IP($RT) ≠ .env($MME_IP) → 실IP 채택"; MME_IP="$RT"; }
fi

# ── 6. .env.4g 생성 ─────────────────────────────────────────────────────────
[[ -f "$ENV_TPL" ]] || die "템플릿 없음: $ENV_TPL"
cp "$ENV_TPL" "$ENV_OUT"
set_kv(){ sed -i -E "s|^($1=)[^[:space:]#]*|\1$2|" "$ENV_OUT"; }
set_kv EPC_NET "$EPC_NET"; set_kv MME_IP "$MME_IP"; set_kv ENB_IP "$SRS_ENB_IP"
set_kv SRSRAN_IMAGE "$SRSRAN_IMAGE"; set_kv DAHNET "$DAHNET"
{ echo "SRS_ENB_IP=$SRS_ENB_IP"; echo "SRS_UE_IP=$SRS_UE_IP"; echo "WORK=$WORK"; echo "EPC_COMPOSE=$EPC_COMPOSE"; } >> "$ENV_OUT"

log "→ $ENV_OUT"; printf '   %-13s %s\n' EPC_NET "$EPC_NET" MME_IP "$MME_IP" SRS_ENB_IP "$SRS_ENB_IP" SRS_UE_IP "$SRS_UE_IP" SRSRAN_IMAGE "$SRSRAN_IMAGE"
log "A2 완료. 다음:  bash provision.sh  →  bash 20-ran-up.sh"
