# 페이로드 컴포넌트 (카메라/짐벌 MAVLink + KLV)
FROM python:3.12-slim
RUN pip install --no-cache-dir pymavlink
WORKDIR /app
COPY payload.py /app/
CMD ["python", "-u", "payload.py"]
