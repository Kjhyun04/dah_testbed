# GPS 채널 (GNSS 매질) 컨테이너 — gnss_medium.py 상시 가동
FROM python:3.12-slim
RUN pip install --no-cache-dir pymavlink
WORKDIR /app
COPY gnss_medium.py /app/
ENTRYPOINT ["python", "-u", "gnss_medium.py"]
# 라우터의 GPS 전용 엔드포인트(14552)로 접속해 GPS_INPUT 주입
CMD ["run", "udpout:172.28.0.20:14552"]
