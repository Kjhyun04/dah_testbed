# DAH 웹 로그뷰어
FROM python:3.12-slim
RUN pip install --no-cache-dir pymavlink
WORKDIR /app
COPY server.py index.html /app/
EXPOSE 8080
CMD ["python", "-u", "server.py"]
