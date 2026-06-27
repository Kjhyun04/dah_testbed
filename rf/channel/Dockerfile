# C2 링크 채널 에뮬레이터
FROM python:3.12-slim
RUN pip install --no-cache-dir pymavlink
WORKDIR /app
COPY channel.py /app/
CMD ["python", "-u", "channel.py"]
