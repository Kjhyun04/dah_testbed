#!/usr/bin/env bash
# ============================================================================
# aws-idle-autostop — 공유 EC2 를 유휴 시 자동 stop 시켜 요금 폭주 방지.
#   "필요할 때만 기동" 정책의 안전망: 켜두고 깜빡해도 아무도 안 쓰면 알아서 내려간다.
#
#   유휴 판정(둘 다 만족해야 유휴):
#     1) 로그인 세션 없음        — who 가 비어 있음(활성 SSH 접속자 0)
#     2) 15분 부하평균 < 임계값   — loadavg[3] < IDLE_LOAD_MAX (기본 0.4)
#   연속 CHECKS_REQUIRED 회(기본 3회) 유휴면 → sudo shutdown -h now.
#     · EBS-backed 인스턴스의 기본 shutdown 동작 = stop(종료 아님) → 디스크/이미지 보존.
#       (안전하게 하려면: aws ec2 modify-instance-attribute
#           --instance-id <id> --instance-initiated-shutdown-behavior stop)
#
#   설치(5분 주기 cron, root):
#     sudo crontab -e
#       */5 * * * * /home/ubuntu/dah_testbed/testbed-4g/scripts/aws-idle-autostop.sh >> /var/log/dah-autostop.log 2>&1
#   비활성화:  해당 crontab 줄 삭제.  1회 점검(내리지 않음):  DRY_RUN=1 bash aws-idle-autostop.sh
# ============================================================================
set -euo pipefail

IDLE_LOAD_MAX="${IDLE_LOAD_MAX:-0.4}"       # 15분 loadavg 이 이 값 미만이면 '한산'
CHECKS_REQUIRED="${CHECKS_REQUIRED:-3}"     # 연속 유휴 횟수(×주기) 후 종료 — 5분×3=15분
STATE="${STATE:-/var/tmp/dah-idle-count}"
DRY_RUN="${DRY_RUN:-0}"
ts(){ date '+%F %T'; }                       # 로그 타임스탬프(런타임 값 — 저장 아님)

# ── 활성 여부 판정 ──────────────────────────────────────────────────────────
users_on="$(who | wc -l | tr -d ' ')"
load15="$(awk '{print $3}' /proc/loadavg)"
idle=1
[[ "$users_on" -gt 0 ]] && idle=0
awk "BEGIN{exit !($load15 < $IDLE_LOAD_MAX)}" || idle=0

if [[ "$idle" == 0 ]]; then
  echo "$(ts) active (users=$users_on load15=$load15) — 카운터 리셋"
  echo 0 > "$STATE" 2>/dev/null || true
  exit 0
fi

# ── 유휴: 카운터 증가 ───────────────────────────────────────────────────────
count=0; [[ -r "$STATE" ]] && count="$(cat "$STATE" 2>/dev/null || echo 0)"
count=$((count + 1))
echo "$count" > "$STATE" 2>/dev/null || true
echo "$(ts) idle (users=$users_on load15=$load15) — 연속 $count/$CHECKS_REQUIRED"

if [[ "$count" -ge "$CHECKS_REQUIRED" ]]; then
  echo "$(ts) 유휴 지속 → 인스턴스 stop(shutdown -h now)"
  echo 0 > "$STATE" 2>/dev/null || true
  if [[ "$DRY_RUN" == 1 ]]; then
    echo "$(ts) DRY_RUN=1 — 실제 종료는 생략."
  else
    sudo shutdown -h now
  fi
fi
