# syntax=docker/dockerfile:1
FROM python:3.12-alpine

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app

COPY app/main.py .
COPY app/healthcheck.py .

RUN mkdir -p /app/logs && chown -R appuser:appgroup /app

USER appuser

ENV MODE=stable \
    APP_VERSION=1.0.0 \
    APP_PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD python3 /app/healthcheck.py

CMD ["python3", "main.py"]
