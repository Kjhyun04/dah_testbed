# 지상 도구 컨테이너 — dahnet 브로드캐스트 세그먼트에서 진단/제어 스크립트 실행.
# router 제거 후, 점대점 host 접속 대신 컨테이너 내부에서 브로드캐스트로 동작한다.
#   docker compose exec tools python scripts/verify_all.py
#   docker compose exec tools python gcs_cli.py arm
FROM python:3.12-slim
RUN pip install --no-cache-dir pymavlink
WORKDIR /work
CMD ["sleep", "infinity"]
