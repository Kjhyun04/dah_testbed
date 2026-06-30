#!/usr/bin/env bash
# open5gs-dbctl 바이너리를 가진 컨테이너를 찾아 'docker exec <c> open5gs-dbctl' 를 stdout 으로 출력.
# 못 찾으면 비공백 출력 없이 exit 1. (bootstrap A3 가 RUN 으로 호출 — docker 그룹 컨텍스트 보장)
set -euo pipefail
for c in $(docker ps --format '{{.Names}}' | grep -iE 'dbctl|webui|hss|mme|mongo'); do
  if docker exec "$c" sh -c 'command -v open5gs-dbctl' >/dev/null 2>&1; then
    echo "docker exec $c open5gs-dbctl"
    exit 0
  fi
done
exit 1
