# GPS 채널 (GNSS 매질) 컨테이너 — gnss_medium.py 상시 가동
FROM python:3.12-slim
RUN pip install --no-cache-dir pymavlink
WORKDIR /app
COPY gnss_medium.py /app/
ENTRYPOINT ["python", "-u", "gnss_medium.py"]
# GPS 매질 가동: SIMSTATE(다운링크) → GPS_INPUT(업링크 브로드캐스트). 포트는 env(BCAST/UP_PORT).
CMD ["run"]
