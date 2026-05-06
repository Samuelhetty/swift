FROM python:3.12-alpine

RUN addgroup -g 1000 -S appgroup && \
    adduser -u 1000 -S appuser -G appgroup

WORKDIR /app

COPY app/main.py .
COPY app/healthcheck.py .

RUN mkdir -p /app/logs && chown -R 1000:1000 /app

USER 1000

ENV MODE=stable \
    APP_VERSION=1.0.0 \
    APP_PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD python3 /app/healthcheck.py

CMD ["python3", "main.py"]
